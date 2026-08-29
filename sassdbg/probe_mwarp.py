"""probe mwarp: multi-warp breakpoint redesign (patch.py v3) primitives.

Design under test (see patch.py v3 plan):

  * Per-warp BLOB (1 MiB device memory).  R252/R253 = the warp's blob
    base.  The site patch word is the CONSTANT
    `CALL.ABS.NOINC PT, {R252,R253}, HANDLER_OFF` — same word for every
    site AND every warp; the per-warp data/handler is reached through
    registers only.
  * The prologue runs SETLMEMBASE {R252,R253} ONCE, permanently: the
    blob then doubles as the warp's local-memory backing, so the handler
    spills/restores kernel registers with plain STL/LDL at fixed local
    slots (RZ+uImm24 addressing — no scratch register needed to spill,
    no GETLMEMBASE/SETLMEMBASE dance inside the handler, LDL stays
    valid across the whole handler because LMB never moves).
  * Handler comms use DESC-LESS STG.E.STRONG.GPU / LDG.E.STRONG.GPU
    [{R252,R253}+COMMS+k] — frees UR60/UR61 (the default cdesc pair) if
    the hardware honors desc-less strong accesses to device memory.
    (REDG.E.ADD.STRONG.GPU desc-less is already proven in
    tests/asm_construct/test_atom.py.)
  * Blob layout (offsets from blob base):
      backing [0x00000, 0x20000)  local window: spill slots at local
                                  addr LMEMHIOFF+4k -> backing 128*k;
                                  kernel frame at LMEMHIOFF+0x1000 ->
                                  backing 0x20000
      comms   [0x40000, ...]      +0x00 u64 code-base report
                                  +0x08 u32 generation (host bumps)
                                  +0x10 u64 hit site VA (handler writes)
      handler [0x80000, ...]      handler code (CALL disp = 0x80000)

Experiments (each runs as its own process — a faulting kernel poisons
its context and a hung kernel deadlocks cuCtxDestroy):

  P0  S2R SR_LMEMHIOFF == 0x00fff9c0 (hardcoded spill-slot base).
  P1  CALL.ABS register form with NONZERO disp jumps to Ra+disp(bytes).
  P2  desc-less STG.E.STRONG.GPU / STG.E.64 / LDG.E to device memory.
  P3  full v3 handler flow, 1 warp: permanent SETLMEMBASE, magic in
      R248-R251 + P0, static CALL site, handler spills via STL, reports,
      parks on gen, host releases, kernel verifies registers/predicate/
      its own local frame (HIOFF+0x1000) all intact after resume.
  P4  TWO WARPS parked at the same static site simultaneously, released
      independently (the actual multi-warp payoff).
  P6a host-side: compose_ret_word(va) bit-surgery == assembler output
      for RET.ABS.NODEC PT, RZ, <va>  (assembler takes the BYTE address
      and does the SCALE-4 (/4) itself; self-modifying code must >>2).
  P6b GPU: handler constructs its own RET.ABS.NODEC RZ, imm word from
      the RPCMOV result, STG.E.128s it over its own last line, hardened
      IVALL, falls through into it.  (CALL.ABS imm faulted 700 in
      probe3 P4 — the RET imm form is UNPROVEN and this decides whether
      v3 can drop the R246/R247 reservation.)

  P3x INFORMATIONAL (no assert): LDL addressing-form matrix.
      ANOMALY (bisected via /tmp scripts): LDL of HOST-prefilled local
      backing shortly after SETLMEMBASE is flaky — lane-split reads
      (lane0 new LMB, others old) and outright 700s, sensitive to the
      distance from SETLMEMBASE.  Device-side STL->LDL round-trips are
      rock solid (P3/P4/P6b).  RULE for v3: SETLMEMBASE goes early in
      the prologue and the gate spin provides the settling distance;
      never let the first local access be a host-data read.

NOTE: the probe sites are STATIC CALLs (nothing is patched), so the
handlers RET to site+0x10 (skip the CALL); the real v3 handler RETs to
the site itself because resume restores the original word there.  For
the same reason the P3/P4 handler omits the IVALL hardening (P6b keeps
it — it must cover the self-modified RET line).

Run all:   python3 sassdbg/probe_mwarp.py
Run one:   python3 sassdbg/probe_mwarp.py <p0|p1|p2|p3|p4|p6a|p6b|p3x>
"""
import struct
import subprocess
import sys
import time
import faulthandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

faulthandler.dump_traceback_later(120, exit=True)

B = "[7:7:{}:5:1]"
BB = "[7:7:{}:8:1]"

LMEMHIOFF = 0x00fff9c0          # SR_LMEMHIOFF on sm_120 (silicon-verified)
BLOB_SZ = 0x100000              # per-warp blob size (1 MiB)
COMMS = 0x40000                 # comms region offset inside the blob
HANDLER_OFF = 0x80000           # handler code offset inside the blob
FRAME_LOCAL = LMEMHIOFF + 0x400     # kernel local frame (backing +0x8000)
# NOTE: the STL/LDL [RZ+uImm24] forms reach ONLY the low 0x640 dwords of
# the local window (LMEMHIOFF+0x640 crosses 2^24); anything deeper needs
# register-based local addressing.  Handler spill slots stay < 0x640.


def slot(k: int) -> str:
    """Local addr of spill slot k (RZ+uImm24 form)."""
    return f"[RZ+0x{LMEMHIOFF + 4 * k:x}]"


def heap_words(body: str) -> bytes:
    from assembler import assemble_flat
    enc = assemble_flat(body)
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in enc)


def run_simple(name, src, out_size=4096, expect=None, block=(32,)):
    """Launch-and-collect helper (no parking)."""
    from assembler import assemble, CudaModule
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(out_size)
    mod.device_write(out, bytes(out_size))
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=block, args=[out], stream=stream)
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 6:
            print(f"{name}: TIMEOUT", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    v = struct.unpack(f"<{out_size // 4}I", mod.device_read(out, out_size))
    tag = ""
    if expect is not None:
        tag = "  (match!)" if v[0] == expect else f"  (WANT {hex(expect)})"
    print(f"{name}: OK " + " ".join(f"w{i}={hex(v[i])}" for i in range(8))
          + tag, flush=True)
    return v


# ---------------------------------------------------------------------------
def exp_p0():
    src = f"""#fn k(out<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    S2R R8, SR_LMEMHIOFF;[5:7:{{}}:5:1]
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R8;[0:1:{{0,1,5}}:8:0]
    EXIT;{B}
}}"""
    v = run_simple("P0 SR_LMEMHIOFF value", src, expect=LMEMHIOFF)
    assert v[0] == LMEMHIOFF, f"LMEMHIOFF = {hex(v[0])}"


# ---------------------------------------------------------------------------
def exp_p1():
    """CALL.ABS reg-form disp: handler sits at heap+0x80 (4 NOPs pad).
    Handler clobbers R2 and RETs to RPC+0x10; out0 must be the handler's
    magic, proving the CALL landed at Ra+0x80 and returned."""
    handler = f"""\
    MOV32I R2, 0xCCCC;{B}
    RPCMOV.32 R10, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R11, Rpc.HI;[0:7:{{}}:13:1]
    RET.ABS.NODEC PT, {{R10,R11}}, 0x10;{BB}
"""
    pad = f"    NOP;{B}\n" * (0x80 // 16)
    from assembler import assemble, CudaModule
    boot = CudaModule(assemble(f"#fn boot(x<8>) {{\n    EXIT;{B}\n}}",
                               check_deps=False))
    heap = boot.devmem_alloc(4096)
    boot.device_write(heap, heap_words(pad + handler))
    src = f"""#fn k(out<8>, heap<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R252,R253}}, #param(heap);[2:7:{{}}:8:0]
    MOV32I R2, 0x1111;{B}
    CALL.ABS.NOINC PT, {{R252,R253}}, 0x80;[7:7:{{2}}:8:1]
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}], R2;[0:1:{{0,1,2}}:8:0]
    EXIT;{B}
}}"""
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(256)
    mod.device_write(out, bytes(256))
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(32,), args=[out, heap], stream=stream)
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 6:
            print("P1: TIMEOUT", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    v0 = struct.unpack("<I", mod.device_read(out, 4))[0]
    ok = v0 == 0xCCCC
    print(f"P1 CALL.ABS reg disp=0x80: out0={hex(v0)} "
          f"({'match!' if ok else 'WANT 0xcccc'})", flush=True)
    assert ok


# ---------------------------------------------------------------------------
def exp_p2():
    """Desc-less strong global access to plain device memory."""
    src = f"""#fn k(out<8>) {{
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    MOV32I R10, 0xDEADBEEF;{B}
    MOV32I R12, 0x12345678;{B}
    MOV32I R13, 0x9ABCDEF0;{B}
    STG.E.STRONG.GPU [{{R4,R5}}+0x40], R10;[7:7:{{1}}:8:0]
    STG.E.64.STRONG.GPU [{{R4,R5}}+0x48], {{R12,R13}};[7:7:{{1}}:8:0]
    LDG.E.STRONG.GPU R11, [{{R4,R5}}+0x40];[3:7:{{}}:8:0]
    LDG.E.64.STRONG.GPU {{R14,R15}}, [{{R4,R5}}+0x48];[4:7:{{}}:8:0]
    STG.E.STRONG.GPU [{{R4,R5}}], R11;[7:7:{{3}}:8:0]
    STG.E.64.STRONG.GPU [{{R4,R5}}+0x8], {{R14,R15}};[7:7:{{4}}:8:0]
    EXIT;{B}
}}"""
    v = run_simple("P2 desc-less STG/LDG.STRONG.GPU", src)
    assert v[0] == 0xDEADBEEF, hex(v[0])
    assert v[2] == 0x12345678 and v[3] == 0x9ABCDEF0, (hex(v[2]), hex(v[3]))


# ---------------------------------------------------------------------------
# v3-style handler: spill R248-R251 + PR to local slots, report site VA
# (desc-less), snapshot gen, spin, restore, RET via R246/R247.
# ---------------------------------------------------------------------------
HANDLER_V3 = f"""\
    STL {slot(0)}, R248;[7:7:{{}}:2:0]
    STL {slot(1)}, R249;[7:7:{{}}:2:0]
    STL {slot(2)}, R250;[7:7:{{}}:2:0]
    STL {slot(3)}, R251;[7:7:{{}}:2:0]
    P2R R248, PR;[7:7:{{}}:4:0]
    STL {slot(4)}, R248;[7:7:{{}}:2:0]
    RPCMOV.32 R246, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R247, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64.STRONG.GPU [{{R252,R253}}+0x{COMMS + 0x10:x}], {{R246,R247}};[7:7:{{0,1}}:8:0]
    IADD3 R246, P1, R246, 0x10, RZ;[7:7:{{0}}:5:1]
    IADD3.X R247, R247, RZ, RZ, P1, !PT;[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R250, [{{R252,R253}}+0x{COMMS + 0x8:x}];[3:7:{{}}:8:0]
#def_label(dbgspin)
    LDG.E.STRONG.GPU R248, [{{R252,R253}}+0x{COMMS + 0x8:x}];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R248, R250, PT;[7:7:{{3,5}}:13:1]
    @!P0 BRA #label(dbgspin);[7:7:{{}}:6:0]
    LDL R248, {slot(4)};[0:7:{{}}:4:0]
    R2P PR, R248;[7:7:{{0}}:13:1]
    LDL R248, {slot(0)};[0:7:{{}}:4:0]
    LDL R249, {slot(1)};[1:7:{{}}:4:0]
    LDL R250, {slot(2)};[2:7:{{}}:4:0]
    LDL R251, {slot(3)};[3:7:{{}}:4:0]
    RET.ABS.NODEC PT, {{R246,R247}}, 0x0;[7:7:{{0,1,2,3}}:8:1]
"""


def _write_handler(mod, blob_base: int) -> None:
    mod.device_write(blob_base + HANDLER_OFF, heap_words(HANDLER_V3))


def _parked(mod, blob_base: int, timeout=10.0) -> int:
    """Wait for the handler's hit report; returns the site VA."""
    t0 = time.time()
    while True:
        va = struct.unpack("<Q", mod.device_read(
            blob_base + COMMS + 0x10, 8))[0]
        if va:
            return va
        if time.time() - t0 > timeout:
            raise TimeoutError("handler did not report a hit")
        time.sleep(0.001)


def _release(mod, blob_base: int, gen: int) -> None:
    mod.device_write(blob_base + COMMS + 0x8, struct.pack("<I", gen))


def _open_gate(mod, blob_base: int) -> None:
    """Open the LMB-settle gate (gives SETLMEMBASE an unbounded settling
    window — a fixed NOP pad proved flaky)."""
    mod.device_write(blob_base + COMMS + 0xc, struct.pack("<I", 1))


def exp_p3():
    """Single warp: magic survives a park/resume; kernel local frame at
    LMEMHIOFF+0x1000 survives permanent SETLMEMBASE; P0 survives (PR
    spill/restore)."""
    from assembler import assemble, CudaModule
    src = f"""#fn k(out<8>, data<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R252,R253}}, #param(data);[2:7:{{}}:8:0]
    SETLMEMBASE {{R252,R253}};[7:7:{{2}}:5:1]
#def_label(lmbgate)
    LDG.E.STRONG.GPU R30, [{{R252,R253}}+0x{COMMS + 0xc:x}];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R30, 0x0, PT;[7:7:{{5}}:13:1]
    @!P0 BRA #label(lmbgate);[7:7:{{}}:6:0]
    MOV32I R20, 0xF00D1234;{B}
    STL [RZ+0x{FRAME_LOCAL:x}], R20;[7:7:{{}}:2:0]
    MOV32I R248, 0xAAAA0008;{B}
    MOV32I R249, 0xAAAA0009;{B}
    MOV32I R250, 0xAAAA000A;{B}
    MOV32I R251, 0xAAAA000B;{B}
    ISETP.EQ.AND P0, PT, R20, R20, PT;[7:7:{{}}:13:1]
    CALL.ABS.NOINC PT, {{R252,R253}}, 0x{HANDLER_OFF:x};{BB}
    LDL R21, [RZ+0x{FRAME_LOCAL:x}];[4:7:{{}}:4:0]
    S2R R25, SR_LANEID;[5:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R26,R27}}, R25, 0x4, {{R252,R253}};[7:7:{{2}}:13:1]
    LDG.E.STRONG.GPU R23, [{{R26,R27}}+0x{(FRAME_LOCAL - LMEMHIOFF) * 32:x}];[3:7:{{}}:8:0]
    STG.E.128 desc[{{UR4,UR5}}][{{R4,R5}}], {{R248,R249,R250,R251}};[7:7:{{0,1}}:8:0]
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}+0x10], R21;[7:7:{{0,1,4}}:8:0]
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}+0x18], R23;[7:7:{{0,1,3}}:8:0]
    MOV32I R22, 0x0;{B}
    @P0 MOV32I R22, 0x1;{B}
    STG.E desc[{{UR4,UR5}}][{{R4,R5}}+0x14], R22;[7:7:{{0,1}}:8:0]
    EXIT;{B}
}}"""
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(256)
    data = mod.devmem_alloc(BLOB_SZ)
    mod.device_write(out, bytes(256))
    mod.device_write(data, bytes(BLOB_SZ))
    _write_handler(mod, data)
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(32,), args=[out, data], stream=stream)
    _open_gate(mod, data)
    va = _parked(mod, data)
    print(f"P3: parked, site VA={hex(va)}", flush=True)
    _release(mod, data, 1)
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 6:
            print("P3: TIMEOUT after release", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    v = struct.unpack("<64I", mod.device_read(out, 256))
    want = [0xAAAA0008, 0xAAAA0009, 0xAAAA000A, 0xAAAA000B, 0xF00D1234, 1]
    got = [v[0], v[1], v[2], v[3], v[4], v[5]]
    ok = want == got
    frame_l2 = struct.unpack("<I", mod.device_read(
        data + (FRAME_LOCAL - LMEMHIOFF) * 32, 4))[0]
    print(f"P3 spill/frame/PR round-trip: got={[hex(x) for x in got]} "
          f"backing-LDG={hex(v[6])} frame-in-L2={hex(frame_l2)} "
          f"({'match!' if ok else f'WANT {[hex(x) for x in want]}'})",
          flush=True)
    assert ok


# ---------------------------------------------------------------------------
def exp_p4():
    """Two warps, same static site, per-warp blobs: both park, warp0 is
    released alone (warp1 must stay parked), then warp1."""
    from assembler import assemble, CudaModule
    src = f"""#fn k(out<8>, blob<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R252,R253}}, #param(blob);[2:7:{{}}:8:0]
    S2R R20, SR_TID.X;[5:7:{{}}:5:1]
    SHF.R.U32.HI R21, RZ, 0x5, R20;[7:7:{{5}}:5:1]
    IMAD.WIDE.U32 {{R252,R253}}, R21, 0x{BLOB_SZ:x}, {{R252,R253}};[7:7:{{2}}:13:1]
    SETLMEMBASE {{R252,R253}};[7:7:{{2}}:5:1]
#def_label(lmbgate)
    LDG.E.STRONG.GPU R30, [{{R252,R253}}+0x{COMMS + 0xc:x}];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R30, 0x0, PT;[7:7:{{5}}:13:1]
    @!P0 BRA #label(lmbgate);[7:7:{{}}:6:0]
    SHF.L.U32 R30, R21, 0xC, RZ;[7:7:{{}}:5:1]
    MOV32I R248, 0xAAAA0000;{B}
    IADD3 R248, R248, R30, RZ;[7:7:{{}}:5:1]
    MOV32I R249, 0xBBBB0000;{B}
    IADD3 R249, R249, R30, RZ;[7:7:{{}}:5:1]
    CALL.ABS.NOINC PT, {{R252,R253}}, 0x{HANDLER_OFF:x};{BB}
    IMAD.WIDE.U32 {{R22,R23}}, R21, 0x10, {{R4,R5}};[7:7:{{1}}:13:1]
    STG.E.64 desc[{{UR4,UR5}}][{{R22,R23}}], {{R248,R249}};[7:7:{{0,1}}:8:0]
    EXIT;{B}
}}"""
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(256)
    blob = mod.devmem_alloc(2 * BLOB_SZ)
    mod.device_write(out, bytes(256))
    mod.device_write(blob, bytes(2 * BLOB_SZ))
    _write_handler(mod, blob)
    _write_handler(mod, blob + BLOB_SZ)
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(64,), args=[out, blob], stream=stream)
    _open_gate(mod, blob)
    _open_gate(mod, blob + BLOB_SZ)
    va0 = _parked(mod, blob)
    va1 = _parked(mod, blob + BLOB_SZ)
    print(f"P4: warp0 parked site={hex(va0)}, warp1 parked site={hex(va1)}",
          flush=True)
    assert va0 == va1, "both warps must hit the SAME site"
    # release warp0 only
    _release(mod, blob, 1)
    time.sleep(0.1)
    w0 = struct.unpack("<2I", mod.device_read(out, 8))
    w1 = struct.unpack("<2I", mod.device_read(out + 0x10, 8))
    print(f"P4 after warp0 release: w0={[hex(x) for x in w0]} "
          f"w1={[hex(x) for x in w1]}", flush=True)
    assert w0 == (0xAAAA0000, 0xBBBB0000), "warp0 should have completed"
    assert w1 == (0, 0), "warp1 must still be parked"
    _release(mod, blob + BLOB_SZ, 1)
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 6:
            print("P4: TIMEOUT after warp1 release", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    w1 = struct.unpack("<2I", mod.device_read(out + 0x10, 8))
    ok = w1 == (0xAAAA1000, 0xBBBB1000)
    print(f"P4 two-warp independent park/resume: w1={[hex(x) for x in w1]} "
          f"({'match!' if ok else 'WANT 0xaaaa1000/0xbbbb1000'})", flush=True)
    assert ok


# ---------------------------------------------------------------------------
# P6: dynamically constructed RET.ABS.NODEC PT, RZ, imm (per-warp handler
# writes its return VA into the imm field of its own last line).  Frees the
# R246/R247 reservation -> v3 needs only R252/R253.
#
# RET sImm field (sm120.json ret__ABS): 56 bits at word [81:34]∥[23:16],
# SCALE 4: stored field = byte_disp / 4.  Mapping (field = va>>2):
#   field[ 7: 0] -> lo64[23:16]
#   field[37: 8] -> lo64[63:34]
#   field[55:38] -> hi64[17: 0]
# ---------------------------------------------------------------------------
def _ret_template() -> tuple[int, int]:
    from assembler import assemble_flat
    return assemble_flat(
        "    RET.ABS.NODEC PT, RZ, 0x0;[7:7:{}:8:1]\n")[0]


def compose_ret_word(va: int) -> tuple[int, int]:
    """(lo64, hi64) of `RET.ABS.NODEC PT, RZ, <va>` built by bit surgery.
    va is the BYTE return address (must be 16-aligned)."""
    assert va % 16 == 0
    t_lo, t_hi = _ret_template()
    f = va >> 2
    lo = t_lo | ((f & 0xFF) << 16) | (((f >> 8) & 0x3FFFFFFF) << 34)
    hi = t_hi | ((f >> 38) & 0x3FFFF)
    return lo, hi


def exp_p6a():
    from assembler import assemble_flat
    for va in (0x12345670, 0x7f8e4a200000, 0x00007ffffff000,
               0x0000ffffde30, 0x0000400000000000):
        want = assemble_flat(
            f"    RET.ABS.NODEC PT, RZ, 0x{va:x};[7:7:{{}}:8:1]\n")[0]
        got = compose_ret_word(va)
        ok = got == want
        print(f"P6a va={hex(va)}: {'match!' if ok else 'MISMATCH ' + ' vs '.join(f'{x:016x}' for x in (*got, *want))}",
              flush=True)
        assert ok, hex(va)
    print("P6a compose == assembler: all OK", flush=True)


def _handler_v3b() -> tuple[bytes, int]:
    """V3B handler: register spill to local, desc-less comms, and a
    SELF-CONSTRUCTED RET.ABS.NODEC RZ, imm as its last line (overwritten
    in-place via STG.E.128 before the spin; the tail IVALL re-fetches it).
    Returns (words, retline_blob_offset)."""
    t_lo, t_hi = _ret_template()
    t00, t01 = t_lo & 0xFFFFFFFF, t_lo >> 32
    t10, t11 = t_hi & 0xFFFFFFFF, t_hi >> 32
    assert t01 == 0, "template lo_hi expected 0"

    def build(retline: int) -> str:
        return f"""\
    STL {slot(0)}, R248;[7:7:{{}}:2:0]
    STL {slot(1)}, R249;[7:7:{{}}:2:0]
    STL {slot(2)}, R250;[7:7:{{}}:2:0]
    STL {slot(3)}, R251;[7:7:{{}}:2:0]
    P2R R248, PR;[7:7:{{}}:4:0]
    STL {slot(4)}, R248;[7:7:{{}}:2:0]
    RPCMOV.32 R246, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R247, Rpc.HI;[0:7:{{}}:13:1]
    STG.E.64.STRONG.GPU [{{R252,R253}}+0x{COMMS + 0x10:x}], {{R246,R247}};[7:7:{{0,1}}:8:0]
    IADD3 R246, P1, R246, 0x10, RZ;[7:7:{{0}}:5:1]
    IADD3.X R247, R247, RZ, RZ, P1, !PT;[7:7:{{}}:5:1]
    SHF.R.U32.HI R248, RZ, 0x2, R246;[7:7:{{}}:5:1]
    SHF.L.U32 R250, R247, 0x1E, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R250, R250, R248, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.R.U32.HI R251, RZ, 0x2, R247;[7:7:{{}}:5:1]
    SHF.L.U32 R248, R250, 0x10, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R248, R248, 0xFF0000, RZ, 0xC0;[7:7:{{}}:5:1]
    LOP3.LUT R248, R248, 0x{t00:08x}, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.R.U32.HI R249, RZ, 0x8, R250;[7:7:{{}}:5:1]
    SHF.L.U32 R246, R251, 0x18, RZ;[7:7:{{}}:5:1]
    LOP3.LUT R249, R249, R246, RZ, 0xFC;[7:7:{{}}:5:1]
    SHF.L.U32 R249, R249, 0x2, RZ;[7:7:{{}}:5:1]
    SHF.R.U32.HI R250, RZ, 0x6, R251;[7:7:{{}}:5:1]
    LOP3.LUT R250, R250, 0x{t10:08x}, RZ, 0xFC;[7:7:{{}}:5:1]
    MOV32I R251, 0x{t11:08x};[7:7:{{}}:5:1]
    STG.E.128.STRONG.GPU [{{R252,R253}}+0x{retline:x}], {{R248,R249,R250,R251}};[7:7:{{}}:8:0]
    LDG.E.STRONG.GPU R250, [{{R252,R253}}+0x{COMMS + 0x8:x}];[3:7:{{}}:8:0]
#def_label(dbgspin)
    LDG.E.STRONG.GPU R248, [{{R252,R253}}+0x{COMMS + 0x8:x}];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R248, R250, PT;[7:7:{{3,5}}:13:1]
    @!P0 BRA #label(dbgspin);[7:7:{{}}:6:0]
    LDL R248, {slot(4)};[0:7:{{}}:4:0]
    R2P PR, R248;[7:7:{{0}}:13:1]
    LDL R248, {slot(0)};[0:7:{{}}:4:0]
    LDL R249, {slot(1)};[1:7:{{}}:4:0]
    LDL R250, {slot(2)};[2:7:{{}}:4:0]
    LDL R251, {slot(3)};[3:7:{{}}:4:0]
    CCTL.I.IVALL;[7:7:{{}}:4:0]
""" + "    NOP;[7:7:{}:8:0]\n" * 32 + f"""    CCTL.I.IVALL;[7:7:{{}}:4:0]
    RET.ABS.NODEC PT, RZ, 0x0;[7:7:{{0,1,2,3}}:8:1]
"""

    from assembler import assemble_flat
    n = len(assemble_flat(build(0)))
    retline = HANDLER_OFF + (n - 1) * 16
    src = build(retline)
    assert len(assemble_flat(src)) == n
    return heap_words(src), retline


def exp_p6b():
    """GPU: self-constructed imm RET.  Same flow as P3 but the handler
    builds its return word from RPC.  Verifies resume AND bit surgery
    (host reads back the constructed line and compares)."""
    from assembler import assemble, CudaModule
    src = f"""#fn k(out<8>, data<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R252,R253}}, #param(data);[2:7:{{}}:8:0]
    SETLMEMBASE {{R252,R253}};[7:7:{{2}}:5:1]
#def_label(lmbgate)
    LDG.E.STRONG.GPU R30, [{{R252,R253}}+0x{COMMS + 0xc:x}];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R30, 0x0, PT;[7:7:{{5}}:13:1]
    @!P0 BRA #label(lmbgate);[7:7:{{}}:6:0]
    MOV32I R248, 0xAAAA0008;{B}
    MOV32I R249, 0xAAAA0009;{B}
    MOV32I R250, 0xAAAA000A;{B}
    MOV32I R251, 0xAAAA000B;{B}
    CALL.ABS.NOINC PT, {{R252,R253}}, 0x{HANDLER_OFF:x};{BB}
    STG.E.128 desc[{{UR4,UR5}}][{{R4,R5}}], {{R248,R249,R250,R251}};[7:7:{{0,1}}:8:0]
    EXIT;{B}
}}"""
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(256)
    data = mod.devmem_alloc(BLOB_SZ)
    mod.device_write(out, bytes(256))
    mod.device_write(data, bytes(BLOB_SZ))
    words, retline = _handler_v3b()
    mod.device_write(data + HANDLER_OFF, words)
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(32,), args=[out, data], stream=stream)
    _open_gate(mod, data)
    va = _parked(mod, data)
    word = struct.unpack("<QQ", mod.device_read(data + retline, 16))
    wc = compose_ret_word(va + 0x10)
    wok = word == wc
    print(f"P6b: parked, site VA={hex(va)} retline=+{hex(retline)} "
          f"constructed-word={'match!' if wok else f'MISMATCH got {word[0]:016x}/{word[1]:016x} want {wc[0]:016x}/{wc[1]:016x}'}",
          flush=True)
    _release(mod, data, 1)
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 6:
            got = struct.unpack("<QQ", mod.device_read(data + retline, 16))
            want = compose_ret_word(va + 0x10)
            print(f"P6b: TIMEOUT after release; constructed word "
                  f"{got[0]:016x}/{got[1]:016x} vs want "
                  f"{want[0]:016x}/{want[1]:016x}", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    v = struct.unpack("<64I", mod.device_read(out, 256))
    got = [v[0], v[1], v[2], v[3]]
    want = [0xAAAA0008, 0xAAAA0009, 0xAAAA000A, 0xAAAA000B]
    ok = got == want
    print(f"P6b self-constructed imm RET: regs={'match!' if ok else got} "
          f"retword={'match!' if wok else 'MISMATCH'}", flush=True)
    assert ok and wok


def exp_p3x():
    """Micro-probe: LDL addressing forms at the frame offset.
    Host pre-fills backing words; the kernel reads them back via:
      out[0]  LDL [RZ+imm]   at slot0  (LMEMHIOFF+0x00)
      out[1]  LDL [RZ+imm]   at frame  (LMEMHIOFF+0x400)
      out[2]  LDL [R14]      at frame  (register form)
      out[3]  LDL [R14+0x0]  at frame
    and STL [RZ+imm] at frame; host scans the blob for the magic."""
    from assembler import assemble, CudaModule
    src = f"""#fn k(out<8>, data<8>) {{
    LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R4,R5}}, #param(out);[1:7:{{}}:8:0]
    LDC.64 {{R252,R253}}, #param(data);[2:7:{{}}:8:0]
    SETLMEMBASE {{R252,R253}};[7:7:{{2}}:5:1]
#def_label(lmbgate)
    LDG.E.STRONG.GPU R30, [{{R252,R253}}+0x{COMMS + 0xc:x}];[5:7:{{}}:8:0]
    ISETP.NE.AND P0, PT, R30, 0x0, PT;[7:7:{{5}}:13:1]
    @!P0 BRA #label(lmbgate);[7:7:{{}}:6:0]
    MOV32I R14, 0x{FRAME_LOCAL:x};{B}
    LDL R20, [RZ+0x{LMEMHIOFF:x}];[0:7:{{}}:8:0]
    LDL R21, [RZ+0x{FRAME_LOCAL:x}];[1:7:{{}}:8:0]
    LDL R22, [R14];[2:7:{{}}:8:0]
    LDL R23, [R14+0x0];[3:7:{{}}:8:0]
    MOV32I R24, 0xF00D1234;{B}
    STL [RZ+0x{FRAME_LOCAL:x}], R24;[7:7:{{}}:2:0]
    IMAD.WIDE.U32 {{R26,R27}}, R8, 0x10, {{R4,R5}};[7:7:{{1}}:13:1]
    STG.E.128 desc[{{UR4,UR5}}][{{R26,R27}}], {{R20,R21,R22,R23}};[7:7:{{0,1,2,3}}:8:0]
    EXIT;{B}
}}"""
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(32 * 16)
    data = mod.devmem_alloc(BLOB_SZ)
    mod.device_write(out, bytes(32 * 16))
    mod.device_write(data, bytes(BLOB_SZ))
    frame_off = (FRAME_LOCAL - LMEMHIOFF) * 32
    for l in range(32):
        mod.device_write(data + l * 4, struct.pack("<I", 0xBEEF0000 + l))
        mod.device_write(data + frame_off + l * 4,
                         struct.pack("<I", 0xCAFE0000 + l))
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(1,), block=(32,), args=[out, data], stream=stream)
    _open_gate(mod, data)
    t0 = time.time()
    while not CudaModule.stream_query(stream):
        if time.time() - t0 > 6:
            print("P3x: TIMEOUT", flush=True)
            sys.exit(2)
        time.sleep(0.005)
    CudaModule.stream_sync(stream)
    v = struct.unpack("<128I", mod.device_read(out, 32 * 16))
    blob = mod.device_read(data, BLOB_SZ)
    hits = [off for off in range(0, BLOB_SZ - 4, 4)
            if blob[off:off + 4] == struct.pack("<I", 0xF00D1234)]
    bad = []
    for l in range(32):
        got = v[l * 4:l * 4 + 4]
        want = [0xBEEF0000 + l, 0xCAFE0000 + l, 0xCAFE0000 + l,
                0xCAFE0000 + l]
        if got != want:
            bad.append((l, [hex(x) for x in got]))
    stl_ok = (len(hits) == 32
              and hits == [frame_off + l * 4 for l in range(32)])
    print(f"P3x STL[RZ+imm] mapping: {'match!' if stl_ok else hits[:4]}",
          flush=True)
    if bad:
        print(f"P3x LDL MISMATCH lanes (informational — host-prefill "
              f"reads right after SETLMEMBASE are flaky, see header): "
              f"{bad[:6]}", flush=True)
    else:
        print("P3x LDL all forms/lanes: match!", flush=True)


EXPERIMENTS = {"p0": exp_p0, "p1": exp_p1, "p2": exp_p2,
               "p3": exp_p3, "p4": exp_p4, "p6a": exp_p6a, "p6b": exp_p6b,
               "p3x": exp_p3x}
if __name__ == "__main__":
    if len(sys.argv) > 1:
        EXPERIMENTS[sys.argv[1]]()
    else:
        for name in EXPERIMENTS:
            r = subprocess.run(
                [sys.executable, __file__, name],
                capture_output=True, text=True, timeout=60)
            print(r.stdout, end="")
            if r.returncode != 0:
                print(f"--- {name} rc={r.returncode} ---")
                print(r.stderr[-600:] if r.stderr else "")
