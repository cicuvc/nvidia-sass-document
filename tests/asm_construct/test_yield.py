import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# YIELD — warp-scheduler yield hint; ITS spin-lock forward progress (SM120)
#
# Classic ITS vs SIMT-stack deadlock: on Volta+ a single warp splits into
# independent-PC groups (here {tid 0} = producer, {tid 1..31} = spin consumers).
# The consumers' TIGHT spin loop (LDG -> NOP -> ISETP -> @P1 BRA) monopolizes the
# warp's issue slots, so the producer group's instructions never issue -> the
# warp deadlocks. Inserting YIELD into the spin loop makes the spinning group
# relinquish the issue slot, the producer runs, sets the flag, and the spin exits.
#
# Verified (SM120, hand-built cubin, block=32):
#   spin loop body = NOP   -> DEADLOCK (kernel never completes; timeout)
#   spin loop body = YIELD -> COMPLETED (flag=0x1, result=0xDEADBEEF)
# The hand-built ELF matches ptxas, which auto-inserts YIELD into an empty
# `while (*flag == 0) {}` spin (see notes/sm90/instr/yield.md).
# ---------------------------------------------------------------------------

def spin_kernel(spin_body: str):
    lines = ["#fn k(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    ISETP.EQ.AND P0, PT, R2, 0x0, PT;[7:7:{0}:13:1]",   # P0 = tid==0
             "    @P0 BRA #label(producer);[7:7:{}:5:1]",
             "    #def_label(spin)",
             "    LDG.E R12, desc[{UR4,UR5}][{R6,R7}+0x0];[2:7:{0,1}:5:1]",   # load flag
             f"    {spin_body};[7:7:{{}}:5:1]",
             "    ISETP.EQ.AND P1, PT, R12, 0x0, PT;[7:7:{2}:13:1]",  # P1 = flag==0
             "    @P1 BRA #label(spin);[7:7:{}:5:1]",
             "    MOV32I R20, 0xDEADBEEF;[7:7:{}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R20;[0:1:{0,1}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "    #def_label(producer)",
             "    MOV32I R10, 0x1;[7:7:{}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R10;[0:1:{0,1}:1:0]",   # set flag
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))

def run(body, timeout_s=6):
    cubin = spin_kernel(body)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    flag = struct.unpack("<I", mod.device_read(d + 0, 4))[0]
    res = struct.unpack("<I", mod.device_read(d + 4, 4))[0]
    mod.devmem_free(d)
    return flag, res

ok = True

if __name__ == "__main__":
    # YIELD version completes.
    flag, res = run("YIELD")
    good = flag == 1 and res == 0xDEADBEEF
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} YIELD spin: COMPLETED flag=%#x result=%#x" % (flag, res))

    # NO-YIELD version deadlocks (kernel never completes).  Run in a subprocess
    # so the genuine deadlock is killed by a hard timeout instead of hanging
    # this test.  The child loads this module ONLY for `run`/`spin_kernel`; the
    # guard above keeps the child from re-spawning its own child (which would
    # leave a chain of orphaned deadlocked processes).
    import subprocess
    CHILD = r'''
import sys, struct
sys.path.insert(0, "__BASE__")
from assembler import assemble, CudaModule
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location("t", "__THIS__")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
flag, res = t.run("NOP", timeout_s=6)
print("COMPLETED", flag, res)
'''
    THIS = str(Path(__file__).resolve())
    py = (CHILD.replace("__BASE__", str(Path(__file__).resolve().parents[2]))
              .replace("__THIS__", THIS))
    try:
        r = subprocess.run([sys.executable, "-c", py], capture_output=True,
                           text=True, timeout=8)
        if r.stdout.strip().startswith("COMPLETED"):
            print("FAIL NOP spin: completed (no deadlock)")
            ok = False
        else:
            print(f"FAIL NOP spin: unexpected stdout={r.stdout[:60]!r} "
                  f"stderr={r.stderr[:200]!r}")
            ok = False
    except subprocess.TimeoutExpired:
        print("ok  NOP spin: DEADLOCK (as expected)")

    print(f"\n=== YIELD spin-lock forward progress: {'ALL PASS' if ok else 'FAILURES'} ===")
    sys.exit(0 if ok else 1)
