import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# mbarrier (shared-memory barrier) semantic verification — hand-written SASS.
#
# All mbarrier PTX ops lower to SYNCS (see notes/sm90/instr/syncs.md):
#   init            SYNCS.EXCH.64 URZ, [UR], UR          (state = count<<1 |
#                                                        count<<11 encoding)
#   arrive          SYNCS.ARRIVE.TRANS64.A1T0  Rd, [UR], RZ
#   arrive.expect_tx SYNCS.ARRIVE.TRANS64       Rd, [UR], R  (A1TR default)
#   expect_tx       SYNCS.ARRIVE.TRANS64.RED.A0TR RZ, [UR], R  (tx += R)
#   complete_tx     SYNCS.ARRIVE.TRANS64.RED.A0TX RZ, [UR], R  (tx -= R)
#   try_wait.parity SYNCS.PHASECHK.TRANS64.TRYWAIT P, [UR], R
#   test_wait.parity SYNCS.PHASECHK.TRANS64      P, [UR], R
#   inval           SYNCS.CCTL.IV [UR]
#
# Empirically verified on sm_120 (RTX 5090, CUDA 13.0):
#   * the phase-parity operand of PHASECHK is bit 31 of Rb
#     (parity 0 -> 0x00000000, parity 1 -> 0x80000000); the instruction
#     returns TRUE iff the phase with that parity has completed.
#   * A0TR ADDS the register value to the pending-tx count (expect_tx);
#     A0TX SUBTRACTS it (complete_tx).  ptxas emits complete_tx as
#     A0TR(R0=0) + A0TX(R2=+count).
#   * mbarrier state is NOT reliably readable with plain LDS right after
#     init (reads 0); observe completion through PHASECHK / arrive tokens.
#   * boundaries: init(0) makes phase 0 immediately complete; a subsequent
#     arrive traps (719); a negative tx count traps (719).
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got} (exp {want})")

try:
    _ = CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
    HAVE_GPU = True
except RuntimeError:
    HAVE_GPU = False
    print("--- no CUDA device; GPU semantic checks SKIPPED ---")

if not HAVE_GPU:
    sys.exit(0)

HEAD = (
    "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]\n"
    "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]\n"
    "    UMOV UR6, 0x400;[1:7:{}:1:0]\n"          # barrier at shared 0x400
)

def init(count):
    return (
        f"    UMOV UR8, 0x{count:X};[1:7:{{}}:1:0]\n"
        "    UIADD3 UR8, UPT, UPT, -UR8, 0x100000, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR9, UR8, 0xb, URZ;[7:7:{1}:5:1]\n"
        "    USHF.L.U32 UR8, UR8, 0x1, URZ;[7:7:{1}:5:1]\n"
        "    SYNCS.EXCH.64 {URZ,URZ}, [UR6], UR8;[2:1:{1}:5:1]\n"
    )

def phasechk(parity, trywait=True, wr=1):
    mod = ".TRYWAIT" if trywait else ""
    return (
        f"    MOV32I R8, 0x{0x80000000 if parity else 0:08X};[7:7:{{}}:5:1]\n"
        f"    SYNCS.PHASECHK.TRANS64{mod} P0, [RZ+UR6], R8;[{wr}:7:{{2}}:1:0]\n"
        "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
        "    SEL R9, RZ, 0x1, !P0;[1:7:{1}:5:1]\n"
    )

def arrive():
    return "    SYNCS.ARRIVE.TRANS64.A1T0 {R0,R1}, [RZ+UR6], RZ;[2:7:{2}:5:1]\n"

def store(off, reg="R9"):
    return f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:X}], {reg};[0:1:{{1}}:1:0]\n"

# --- 1. init(2): phase completes after 2 arrives, parity flips -------------
body = HEAD + init(2) + arrive()
body += phasechk(0) + store(0x0)
body += arrive() + phasechk(0) + store(0x4)
body += phasechk(1) + store(0x8)
body += arrive() + arrive() + phasechk(1) + store(0xc)
body += phasechk(0) + store(0x10)
body += "    EXIT;[7:7:{}:5:0]\n"
src = "#fn k(out<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body + "}\n"
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(64)
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<5I", mod.device_read(d, 20))
check("init(2) 1/2 arrive: parity0 complete", v[0], 0)
check("init(2) 2/2 arrive: parity0 complete", v[1], 1)
check("init(2) 2/2 arrive: parity1 complete", v[2], 0)
check("init(2) 4/2 arrive: parity1 complete", v[3], 1)
check("init(2) 4/2 arrive: parity0 complete", v[4], 0)

# --- 2. test_wait (non-blocking single check) ------------------------------
body = HEAD + init(1) + phasechk(0, trywait=False) + store(0x0)
body += arrive() + phasechk(0, trywait=False) + store(0x4)
body += "    EXIT;[7:7:{}:5:0]\n"
src = "#fn k(out<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body + "}\n"
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(32)
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<2I", mod.device_read(d, 8))
check("test_wait before arrive", v[0], 0)
check("test_wait after arrive", v[1], 1)

# --- 3. expect_tx (A0TR adds) blocks completion; complete_tx (A0TX) drains -
body = HEAD + init(1)
body += "    MOV32I R2, 128;[7:7:{}:5:1]\n"
body += "    SYNCS.ARRIVE.TRANS64.RED.A0TR {RZ,RZ}, [RZ+UR6], R2;[1:7:{2}:5:1]\n"
body += arrive() + phasechk(0) + store(0x0)
body += "    MOV32I R2, 128;[7:7:{}:5:1]\n"
body += "    SYNCS.ARRIVE.TRANS64.RED.A0TX {RZ,RZ}, [RZ+UR6], R2;[1:7:{2}:5:1]\n"
body += phasechk(0) + store(0x4)
body += "    EXIT;[7:7:{}:5:0]\n"
src = "#fn k(out<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body + "}\n"
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(32)
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<2I", mod.device_read(d, 8))
check("expect_tx(128)+arrive: not complete", v[0], 0)
check("+complete_tx(128): complete", v[1], 1)

# --- 4. A0TR adds vs A0TX subtracts (decisive) -----------------------------
body = HEAD + init(1)
body += "    MOV32I R2, 128;[7:7:{}:5:1]\n"
body += "    SYNCS.ARRIVE.TRANS64.RED.A0TR {RZ,RZ}, [RZ+UR6], R2;[1:7:{2}:5:1]\n"
body += arrive()
body += "    MOV32I R2, 128;[7:7:{}:5:1]\n"
body += "    SYNCS.ARRIVE.TRANS64.RED.A0TR {RZ,RZ}, [RZ+UR6], R2;[1:7:{2}:5:1]\n"
body += phasechk(0) + store(0x0)
body += "    MOV32I R2, 256;[7:7:{}:5:1]\n"
body += "    SYNCS.ARRIVE.TRANS64.RED.A0TX {RZ,RZ}, [RZ+UR6], R2;[1:7:{2}:5:1]\n"
body += phasechk(0) + store(0x4)
body += "    EXIT;[7:7:{}:5:0]\n"
src = "#fn k(out<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body + "}\n"
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(32)
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<2I", mod.device_read(d, 8))
check("A0TR(128) after tx=128: adds (not complete)", v[0], 0)
check("A0TX(256) after tx=256: subtracts (complete)", v[1], 1)

# --- 5. inval: barrier stops completing ------------------------------------
body = HEAD + init(1)
body += "    SYNCS.CCTL.IV [RZ+UR6];[1:7:{2}:5:1]\n"
body += "    NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]  NOP;[7:7:{}:5:1]\n"
body += phasechk(0) + store(0x0)
body += "    EXIT;[7:7:{}:5:0]\n"
src = "#fn k(out<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body + "}\n"
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(32)
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<I", mod.device_read(d, 4))[0]
check("inval: phase no longer completes", v, 0)

# --- 6. init(0): phase immediately complete --------------------------------
body = HEAD + init(0) + phasechk(0) + store(0x0)
body += "    EXIT;[7:7:{}:5:0]\n"
src = "#fn k(out<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body + "}\n"
mod = CudaModule(assemble(src))
d = mod.devmem_alloc(32)
mod.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
mod.synchronize()
v = struct.unpack("<I", mod.device_read(d, 4))[0]
check("init(0): phase 0 immediately complete", v, 1)

# --- 7. behavior boundaries (expected traps) -------------------------------
def expect_launch_fault(name, body):
    """Launch a kernel that is expected to fault; PASS if it raises 719."""
    global ok
    src = "#fn k(out<8>) {\n    #pragma NUM_MBARRIERS(1)\n    #pragma SHARED(0x4000)\n" + body + "}\n"
    try:
        m = CudaModule(assemble(src))
        d = m.devmem_alloc(32)
        m.launch("k", grid=(1,), block=(1,), args=[d], shared_mem=0x4000)
        m.synchronize()
        got = "no fault"
    except RuntimeError as e:
        got = str(e)
    good = "719" in got
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {name:<46} {got}")

# negative tx count underflows the pending-tx field; a subsequent mbarrier op
# on the corrupted barrier traps
body = HEAD + init(1)
body += "    MOV32I R2, 64;[7:7:{}:5:1]\n"
body += "    SYNCS.ARRIVE.TRANS64.RED.A0TR {RZ,RZ}, [RZ+UR6], R2;[1:7:{2}:5:1]\n"
body += "    MOV32I R2, 0xFFFFFFC0;[7:7:{}:5:1]\n"
body += "    SYNCS.ARRIVE.TRANS64.RED.A0TX {RZ,RZ}, [RZ+UR6], R2;[1:7:{2}:5:1]\n"
body += "    MOV32I R8, 0x0;[7:7:{}:5:1]\n"
body += "    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR6], R8;[1:7:{2}:1:0]\n"
body += "    EXIT;[7:7:{}:5:0]\n"
expect_launch_fault("boundary: neg tx then phasechk traps", body)

# arrive on an init(0) barrier (phase already complete) -> trap
body = HEAD + init(0) + arrive()
body += "    EXIT;[7:7:{}:5:0]\n"
expect_launch_fault("boundary: arrive after init(0) traps", body)

print(f"\n=== MBARRIER semantics: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
