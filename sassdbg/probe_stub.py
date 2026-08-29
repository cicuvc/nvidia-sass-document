"""sassdbg M9 probe — register-less breakpoint stub (no R252/R253).

Validates the new patch scheme end to end:
  * patch word = JMP IMM (absolute VA, 0x94a UImm(57) SCALE 4) to a
    per-breakpoint STUB in a devmem arena — no register pair needed.
  * The stub spills the kernel's R0/R1 into RPC (RPCMOV Rpc.LO/HI
    write forms — JMP IMM does not write RPC, so RPC is dead here and
    serves as a 64-bit spill slot).
  * With R0/R1 free: S2R SR_LANEID + baked local-pool immediates give
    the per-lane spill address (IMAD lo32 + 4*lane, carry-free by
    construction); R2/R3 spill to the pool; a per-lane hit counter
    is bumped; then JMP to the SHARED handler.
  * The handler restores R2/R3, replays the patched-out instruction,
    pulls kernel R0/R1 back out of RPC, and JMP-IMM returns to
    site+0x10.

Expected: kernel result identical to unpatched (sum = 10*7 = 70), and
each lane's hit counter == 10 (the bp fires every loop iteration).
"""

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import assemble, assemble_flat, CudaModule      # noqa: E402
from sassdbg.patch import Patcher                             # noqa: E402

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
    MOV32I R2, 0x0;[7:7:{}:5:1]
    MOV32I R3, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R2, R2, 0x7, RZ;[7:7:{}:5:1]
    IADD3 R3, R3, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P0, PT, R3, 0xA, PT;[7:7:{}:13:1]
    @P0 BRA #label(loop);[7:7:{}:5:1]
    STG.E desc[{UR4,UR5}][{R4,R5}], R2;[0:1:{}:1:0]
    EXIT;[7:7:{}:5:0]
}
"""

# instruction index of the bp site (the loop-body IADD3 R2, R2, 0x7)
SITE_IDX = 4 + 3 + 1 + 32 + 1 + 2   # hdr + gate + cctl + NOPs + cctl + MOVs = 43


def main() -> None:
    print("step: assemble", flush=True)
    mod = CudaModule(assemble(K, check_deps=True))
    print("step: module loaded", flush=True)
    patcher = Patcher()
    print("step: patcher warm", flush=True)

    out = mod.devmem_alloc(0x200)
    mod.device_write(out, bytes(0x200))
    arena = mod.devmem_alloc(0x1000)      # [0,0x200): stub+handler code
    pool = arena + 0x400                  # per-lane spill/counters
    stub_va = arena
    handler_va = arena + 0x100
    assert (pool & 0xFFFFFFFF) + 0x240 + 124 < 0x100000000, \
        "pool lo32 carry — realign the allocation"

    # launch PARKED at the gate; learn the code base from the LEPC
    # report, patch the site while the warp is parked (the site line
    # is cold), then release — the hardened IVALL makes the patch
    # visible on first fetch (the M3 prologue pattern).
    print("step: launching", flush=True)
    stream = CudaModule.stream_create()   # NON_BLOCKING: sync cuMemcpy
                                          # would queue behind a default-
                                          # stream spinner and deadlock
    mod.launch("k", grid=(1,), block=(32,), args=[out], stream=stream)
    print("step: launched", flush=True)
    t0 = time.time()
    while True:
        lepc = struct.unpack("<Q", mod.device_read(out + 0x100, 8))[0]
        if lepc:
            break
        assert time.time() - t0 < 10, "no LEPC report"
        time.sleep(0.001)
    site_va = lepc + SITE_IDX * 16
    print(f"lepc={lepc:#x}  site_va={site_va:#x}")

    # ---- stub: RPCMOV-spill R0/R1, per-lane pool addr, spill R2/R3,
    # ---- bump hit counter, JMP to the shared handler
    stub = f"""\
    RPCMOV Rpc.LO, R0;[3:7:{{}}:9:0]
    RPCMOV Rpc.HI, R1;[4:7:{{}}:9:0]
    S2R R0, SR_LANEID;[5:7:{{}}:5:1]
    MOV32I R1, 0x{pool & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    IMAD R0, R0, 0x4, R1;[7:7:{{5}}:5:1]
    MOV32I R1, 0x{pool >> 32:08x};[7:7:{{}}:5:1]
    STG.E.STRONG.GPU [{{R0,R1}}], R2;[7:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R0,R1}}+0x80], R3;[7:7:{{}}:8:0]
    LDG.E.STRONG.GPU R2, [{{R0,R1}}+0x200];[2:7:{{}}:8:0]
    IADD3 R2, R2, 0x1, RZ;[7:7:{{2}}:5:1]
    STG.E.STRONG.GPU [{{R0,R1}}+0x200], R2;[7:7:{{}}:8:0]
    JMP 0x{handler_va:x};[7:7:{{}}:6:0]
"""
    # ---- handler: restore R2/R3, replay the patched instruction,
    # ---- recover kernel R0/R1 from RPC, JMP back past the site
    handler = f"""\
    LDG.E.STRONG.GPU R2, [{{R0,R1}}];[0:7:{{}}:8:0]
    LDG.E.STRONG.GPU R3, [{{R0,R1}}+0x80];[1:7:{{}}:8:0]
    IADD3 R2, R2, 0x7, RZ;[7:7:{{0,1}}:5:1]
    RPCMOV R0, Rpc.LO;[7:7:{{3}}:9:1]
    RPCMOV R1, Rpc.HI;[7:7:{{4}}:9:1]
    JMP 0x{site_va + 0x10:x};[7:7:{{}}:6:0]
"""
    stub_enc, handler_enc = assemble_flat(stub), assemble_flat(handler)
    assert 0 < len(handler_enc) and len(stub_enc) <= 16
    enc = stub_enc + [(0, 0)] * (16 - len(stub_enc)) + handler_enc
    words = b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc)
    assert handler_va == stub_va + 0x100, "handler offset drift"
    mod.device_write(stub_va, words)

    # ---- patch the site with JMP IMM stub_va (warp parked, site line
    # cold), zero state, release the gate
    jmp = assemble_flat(f"    JMP 0x{stub_va:x};[7:7:{{}}:6:0]\n")
    assert len(jmp) == 1
    patcher.patch(site_va, jmp[0])
    mod.device_write(out, bytes(0x100))     # keep the LEPC report
    mod.device_write(pool, bytes(0x240))
    print("step: release gate", flush=True)
    mod.device_write(out + 0x108, struct.pack("<I", 1))   # release gate
    for _ in range(100):
        if CudaModule.stream_query(stream):
            break
        time.sleep(0.05)
    else:
        hits = struct.unpack("<32I", mod.device_read(pool + 0x200, 128))
        r2 = struct.unpack("<32I", mod.device_read(pool, 128))
        r3 = struct.unpack("<32I", mod.device_read(pool + 0x80, 128))
        res = struct.unpack("<I", mod.device_read(out, 4))[0]
        print(f"TIMEOUT: hits[0]={hits[0]} r2[0]={r2[0]:#x} r3[0]={r3[0]:#x} "
              f"out={res}", flush=True)
        raise SystemExit(1)
    print("step: kernel exited", flush=True)

    v = struct.unpack("<I", mod.device_read(out, 4))[0]
    print(f"out = {v} (want 70)")
    assert v == 70, "kernel result wrong — replay/restore broken"
    hits = struct.unpack("<32I", mod.device_read(pool + 0x200, 0x80))
    print(f"per-lane hits: {set(hits)} (want {{10}})")
    if not all(h == 10 for h in hits):
        dump = struct.unpack("<144I", mod.device_read(pool, 0x240))
        nz = [(hex(i * 4), hex(x)) for i, x in enumerate(dump) if x]
        print("pool nonzero:", nz[:24])
    assert all(h == 10 for h in hits)
    print("== probe_stub: OK ==")


if __name__ == "__main__":
    main()
