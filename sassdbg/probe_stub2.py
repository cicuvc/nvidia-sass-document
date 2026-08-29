"""M9 probe 2 — the FULL handler pattern with zero register reservation.

Extends probe_stub.py (which proved JMP-IMM patch -> devmem stub ->
RPCMOV Rpc-spill of R0/R1 -> per-lane absolute pool -> mini handler ->
replay -> RPCMOV restore) to the complete handler structure that
patch.py's M9 rewrite needs:

  stub (per-bp, shared across warps, borrows only R0/R1 via RPC):
    RPCMOV Rpc.LO, R0 / RPCMOV Rpc.HI, R1
    f = CTAID*(ctawarps*32) + TID          (baked K, S2R+IMAD+IADD3)
    {R0,R1} = pool + f*FRAME               (baked pool 64-bit imm)
    JMP handler_va                         (JMP preserves RPC)

  handler (shared):
    spill R2-R7 + PR + kernel R0/R1 (from RPC) into the frame
    hits[f]++ (STRONG.GPU, host-visible)
    spin on release[f] != baseline, NANOSLEEP 0x100 in the loop
    restore PR, R2-R7 (all LDGs chained on SB2)
    JMP thunk_va

  thunk (per-site, host-built):  replay ; JMP epi_va
    The replay instruction carries req {2} -> covers every restore LDG.

  epi (shared):
    LDG.E.64 {R0,R1}, [{R0,R1}+0x1C]   ; kernel R0/R1 self-restore
    MOV R1, R1  (req {2})              ; scoreboard-wait the restore so
                                       ; the kernel never reads a pending
                                       ; variable-latency R0/R1
    JMP site+0x10

  RPC ordering constraint: RPC holds kernel R0/R1 from the stub until
  the handler's entry stores them into the frame.  No RPC-writing
  instruction (NANOSLEEP/BSYNC/CALL/RET/BRX) may execute before that
  store; afterwards RPC is dead (the epi restores R0/R1 from the frame,
  not from RPC), so the spin's NANOSLEEP and an RPC-writing replayed
  site instruction are both safe.

  Verification: the kernel keeps known constants in R4-R7 and P1-P3
  across the breakpoint and folds them into out[1] at the end
  (0x100+0x200+0x300+0x400 = 0xA00) — any spill/restore corruption
  changes the sum.  out[0] = 70 proves 10 correct replays; hits = 10
  per lane proves the persistent-bp re-hit loop.

Run:  python3 sassdbg/probe_stub2.py
"""

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assembler import CudaModule, assemble, assemble_flat
from sassdbg.patch import Patcher

FRAME = 0x40
# frame offsets
F_R2, F_R7 = 0x00, 0x14        # R2..R7 spill (6 x 4B)
F_PR = 0x18                    # P2R PR snapshot
F_HITS = 0x1C                  # per-lane hit counter (host-observed)
F_R01 = 0x20                   # kernel R0/R1 (8B, one LDG.E.64 restores;
                               # MUST be 8B-aligned — 0x1C faulted 716)
F_RELEASE = 0x28               # per-lane release generation (host bumps)

K = """\
#fn k(out<8>) {
    LEPC {R8,R9};[7:7:{}:4:0]
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R4,R5}, #param(out);[1:7:{}:8:0]
    STG.E.64.STRONG.GPU [{R4,R5}+0x100], {R8,R9};[7:7:{1}:8:0]
#def_label(gate)
    LDG.E.STRONG.GPU R10, [{R4,R5}+0x108];[2:7:{}:8:0]
    ISETP.EQ.AND P0, PT, R10, RZ, PT;[7:7:{2}:13:1]
    @P0 BRA #label(gate);[7:7:{}:6:0]
    CCTL.I.IVALL;[7:7:{}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + """\
    CCTL.I.IVALL;[7:7:{}:4:0]
    MOV32I R4, 0x100;[7:7:{}:5:1]
    MOV32I R5, 0x200;[7:7:{}:5:1]
    MOV32I R6, 0x300;[7:7:{}:5:1]
    MOV32I R7, 0x400;[7:7:{}:5:1]
    ISETP.EQ.AND P1, PT, R4, 0x100, PT;[7:7:{}:13:1]
    ISETP.NE.AND P2, PT, R4, 0x100, PT;[7:7:{}:13:1]
    ISETP.GT.AND P3, PT, R5, 0x100, PT;[7:7:{}:13:1]
    MOV32I R2, 0x0;[7:7:{}:5:1]
    MOV32I R3, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]
    IADD3 R3, R3, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P0, PT, R3, 0xA, PT;[7:7:{}:13:1]
    @P0 BRA #label(loop);[7:7:{}:5:1]
    LDC.64 {R10,R11}, #param(out);[1:7:{}:8:0]
    MOV32I R8, 0x0;[7:7:{}:5:1]
    @P1 IADD3 R8, R8, R4, RZ;[7:7:{}:5:1]
    @P2 IADD3 R8, R8, 0xFFFF, RZ;[7:7:{}:5:1]
    @P3 IADD3 R8, R8, R5, RZ;[7:7:{}:5:1]
    IADD3 R8, R8, R6, RZ;[7:7:{}:5:1]
    IADD3 R8, R8, R7, RZ;[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R10,R11}], R2;[7:7:{1}:8:0]
    STG.E desc[{UR4,UR5}][{R10,R11}+0x4], R8;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

# hdr(4) + gate(3) + cctl(1) + NOPs(32) + cctl(1) + MOVI(4) + ISETP(3)
#   + MOVI(2) = 50
SITE_IDX = 50


def stub_src(pool: int, handler_va: int) -> str:
    return f"""\
    RPCMOV Rpc.LO, R0;[3:7:{{}}:9:0]
    RPCMOV Rpc.HI, R1;[4:7:{{}}:9:0]
    S2R R0, SR_CTAID.X;[5:7:{{}}:5:1]
    IMAD R0, R0, 0x20, RZ;[7:7:{{5}}:5:1]
    S2R R1, SR_TID.X;[5:7:{{}}:5:1]
    IADD3 R0, R0, R1, RZ;[7:7:{{5}}:5:1]
    MOV32I R1, 0x{pool & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    IMAD R0, R0, 0x{FRAME:x}, R1;[7:7:{{5}}:5:1]
    MOV32I R1, 0x{pool >> 32:08x};[7:7:{{}}:5:1]
    JMP 0x{handler_va:x};[7:7:{{}}:6:0]
"""


def handler_src(thunk_va: int) -> str:
    spills = "".join(
        f"    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_R2 + 4 * i:02x}], R{2 + i};"
        f"[7:7:{{}}:8:0]\n"
        for i in range(6))
    loads = "".join(
        f"    LDG.E.STRONG.GPU R{2 + i}, [{{R0,R1}}+0x{F_R2 + 4 * i:02x}];"
        f"[2:7:{{}}:8:0]\n"
        for i in range(6))
    return f"""\
{spills}    P2R R2, PR;[2:7:{{}}:6:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_PR:x}], R2;[7:7:{{2}}:8:0]
    RPCMOV R2, Rpc.LO;[2:7:{{}}:9:0]
    RPCMOV R3, Rpc.HI;[2:7:{{}}:9:0]
    STG.E.64.STRONG.GPU [{{R0,R1}}+0x{F_R01:x}], {{R2,R3}};[7:7:{{2}}:8:0]
    LDG.E.STRONG.GPU R7, [{{R0,R1}}+0x{F_RELEASE:x}];[2:7:{{}}:8:0]
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_HITS:x}];[3:7:{{}}:8:0]
    IADD3 R2, R2, 0x1, RZ;[7:7:{{3}}:5:1]
    STG.E.STRONG.GPU [{{R0,R1}}+0x{F_HITS:x}], R2;[7:7:{{}}:8:0]
#def_label(spin)
    NANOSLEEP 0x100;[7:7:{{2}}:5:1]
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_RELEASE:x}];[2:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R2, R7, PT;[7:7:{{2}}:13:1]
    @!P0 BRA #label(spin);[7:7:{{}}:6:0]
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x{F_PR:x}];[2:7:{{}}:8:0]
    R2P PR, R2, 0x7F;[7:7:{{2}}:13:1]
{loads}    JMP 0x{thunk_va:x};[7:7:{{}}:6:0]
"""


def main() -> None:
    mod = CudaModule(assemble(K, check_deps=True))
    patcher = Patcher()

    out = mod.devmem_alloc(0x200)
    mod.device_write(out, bytes(0x200))
    arena = mod.devmem_alloc(0x1000)      # code: stub/handler/thunk/epi
    pool = mod.devmem_alloc(0x1000)       # 32 lanes x FRAME
    stub_va = arena                # slots sized for the real code:
    handler_va = arena + 0x100     # handler ~45 insts = 0x2D0 bytes —
    thunk_va = arena + 0x400       # overlapping slots once made thunk/epi
    epi_va = arena + 0x480         # overwrite live handler code (the
                                   # "hit2 never arrives" bug)
    assert (pool & 0xFFFFFFFF) + 32 * FRAME < 0x100000000

    stream = CudaModule.stream_create()   # NON_BLOCKING: a synchronous
    mod.launch("k", grid=(1,), block=(32,), args=[out], stream=stream)
    t0 = time.time()                       # cuMemcpy would queue behind a
    while True:                            # default-stream spinner
        lepc = struct.unpack("<Q", mod.device_read(out + 0x100, 8))[0]
        if lepc:
            break
        assert time.time() - t0 < 10, "no LEPC report"
        time.sleep(0.001)
    site_va = lepc + SITE_IDX * 16
    print(f"lepc={lepc:#x}  site_va={site_va:#x}")

    stub_enc = assemble_flat(stub_src(pool, handler_va))
    hdl_enc = assemble_flat(handler_src(thunk_va))
    thunk_enc = assemble_flat(f"""\
    IADD3 R2, R2, 0x7, RZ;[7:7:{{2}}:5:1]
    JMP 0x{epi_va:x};[7:7:{{}}:6:0]
""")
    epi_enc = assemble_flat(f"""\
    LDG.E.64.STRONG.GPU {{R0,R1}}, [{{R0,R1}}+0x{F_R01:x}];[2:7:{{}}:8:0]
    MOV R1, R1;[7:7:{{2}}:5:1]
    JMP 0x{site_va + 0x10:x};[7:7:{{}}:6:0]
""")
    assert 0 < len(stub_enc) <= 0x100 // 16
    assert 0 < len(hdl_enc) <= (thunk_va - handler_va) // 16
    assert 0 < len(thunk_enc) <= (epi_va - thunk_va) // 16
    assert 0 < len(epi_enc) <= 8

    def put(va: int, enc: list) -> None:
        mod.device_write(va, b"".join(struct.pack("<QQ", *w) for w in enc))

    put(stub_va, stub_enc)
    put(handler_va, hdl_enc)
    put(thunk_va, thunk_enc)
    put(epi_va, epi_enc)
    mod.device_write(pool, bytes(0x1000))

    jmp = assemble_flat(f"    JMP 0x{stub_va:x};[7:7:{{}}:6:0]\n")
    patcher.patch(site_va, jmp[0])
    mod.device_write(out + 0x108, struct.pack("<I", 1))   # release gate

    # persistent bp: 10 hits, host releases each one
    hits_addr = pool + F_HITS
    rel_addrs = [pool + lane * FRAME + F_RELEASE for lane in range(32)]
    for i in range(1, 11):
        t0 = time.time()
        while struct.unpack("<I", mod.device_read(hits_addr, 4))[0] < i:
            if time.time() - t0 > 10:
                fr = struct.unpack("<16I", mod.device_read(pool, 0x40))
                print(f"TIMEOUT hit {i}: hits={fr[F_HITS//4]} "
                      f"rel={fr[F_RELEASE//4]} r2sp={fr[0]:#x} "
                      f"r3sp={fr[1]:#x} pr={fr[F_PR//4]:#x} "
                      f"r01={fr[F_R01//4]:#x},{fr[F_R01//4+1]:#x} "
                      f"out={struct.unpack('<II', mod.device_read(out, 8))}",
                      flush=True)
                raise SystemExit(1)
            time.sleep(0.0005)
        for ra in rel_addrs:
            mod.device_write(ra, struct.pack("<I", i))
    CudaModule.stream_sync(stream)
    got = struct.unpack("<II", mod.device_read(out, 8))
    print(f"out = {got[0]},{got[1]:#x}  (want 70, 0xa00)")
    hits = [struct.unpack("<I", mod.device_read(pool + l * FRAME + F_HITS, 4))[0]
            for l in range(32)]
    print("per-lane hits:", set(hits), "(want {10})")
    assert set(hits) == {10}
    print("== probe_stub2: OK ==")


if __name__ == "__main__":
    main()
