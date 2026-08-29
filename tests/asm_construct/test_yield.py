import sys, struct, time
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
#
# The reverse-direction probe asks a separate question: after group A executes
# ONE YIELD and group B takes over, will A ever be scheduled again if B neither
# executes YIELD nor exits?  An atomic state machine makes completion possible
# only in the order A(pre-yield) -> B(state=1) -> A(CAS 1->2):
#
#   B spin body = YIELD -> COMPLETED (positive control)
#   B spin body = NANOSLEEP N -> COMPLETED for N=0,1,32,100 ns
#   B spin body = NOP   -> outcome under test (automatic group rescheduling?)
#
# Memory operations and the control-code yield bit do not cause intra-warp
# execution-group switches; only the explicit YIELD instruction is varied.
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


def reverse_kernel(spin_body: str):
    """A yields once to B; B waits for A without necessarily yielding back.

    state is buf[0], success is buf[1], and A's CAS old value is buf[2].
    The fall-through group A is lanes 1..31 (lane 1 performs the CAS); the
    branch-target group B is lane 0.  Completion proves the order A -> B -> A:
    if A reaches the CAS before B, it sees state=0 and cannot release B.
    """
    lines = ["#fn reverse(buf<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(buf);[1:7:{}:1:0]",
             "    S2R R2, SR_TID.X;[0:7:{}:5:1]",
             "    ISETP.EQ.AND P0, PT, R2, 0x0, PT;[7:7:{0}:13:1]",  # B = lane 0
             "    ISETP.EQ.AND P1, PT, R2, 0x1, PT;[7:7:{}:13:1]",   # A recorder = lane 1
             "    MOV32I R10, 0x1;[7:7:{}:5:1]",
             "    MOV32I R11, 0x2;[7:7:{}:5:1]",
             "    @P0 BRA #label(group_b);[7:7:{}:5:1]",
             # Group A: its only explicit handoff.  If it is automatically
             # selected again after B starts, lane 1 changes state 1 -> 2.
             "    YIELD;[7:7:{}:5:1]",
             "    @P1 ATOM.E.CAS.STRONG.GPU PT, R16, [{R6,R7}], R10, R11;[5:7:{0,1}:8:1]",
             "    @P1 STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R16;[0:1:{0,1,5}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             # Group B: publish state=1, then wait for A to change it to 2.
             # The loop's memory traffic/control codes are irrelevant to
             # intra-warp switching; spin_body is the explicit instruction.
             "    #def_label(group_b)",
             "    ATOM.E.EXCH.STRONG.GPU PT, R18, [{R6,R7}], R10;[5:7:{0,1}:8:1]",
             "    #def_label(wait_a)",
             "    LDG.E R12, desc[{UR4,UR5}][{R6,R7}];[2:7:{0,1,5}:5:1]",
             f"    {spin_body};[7:7:{{}}:5:1]",
             "    ISETP.NE.AND P2, PT, R12, 0x2, PT;[7:7:{2}:13:1]",
             "    @P2 BRA #label(wait_a);[7:7:{}:5:1]",
             "    MOV32I R20, 0xA2B2A;[7:7:{}:5:1]",
             "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R20;[0:1:{0,1}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))


def run_reverse(body):
    cubin = reverse_kernel(body)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("reverse", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    state, success, cas_old = struct.unpack("<3I", mod.device_read(d, 12))
    mod.devmem_free(d)
    return state, success, cas_old


def observe_reverse(body, delay_s=2.0):
    """Take a live snapshot without synchronizing a possibly infinite kernel."""
    cubin = reverse_kernel(body)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    stream = CudaModule.stream_create()
    mod.launch("reverse", grid=(1,), block=(32,), args=[d], stream=stream)
    time.sleep(delay_s)
    state, success, cas_old = struct.unpack("<3I", mod.device_read(d, 12))
    done = CudaModule.stream_query(stream)
    if done:
        CudaModule.stream_sync(stream)
        CudaModule.stream_destroy(stream)
        mod.devmem_free(d)
    # If not done, the caller must terminate its disposable process: freeing
    # memory or synchronizing here would block behind B's infinite spin.
    return done, state, success, cas_old

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

    # Reverse dependency, positive control: A yields once to B, then B's
    # explicit YIELD schedules A again.  The CAS old value of 1 proves B ran
    # between A's initial YIELD and A's resumption.
    state, success, cas_old = run_reverse("YIELD")
    good = state == 2 and success == 0xA2B2A and cas_old == 1
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} reverse/YIELD: COMPLETED "
          f"state={state:#x} success={success:#x} cas_old={cas_old:#x}")

    # Reverse dependency under test: B never executes YIELD and never exits
    # while state remains 1.  Run in a disposable child because a negative
    # result is a genuine infinite kernel.
    REVERSE_CHILD = r'''
import sys
import os
sys.path.insert(0, "__BASE__")
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location("t", "__THIS__")
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
done, state, success, cas_old = t.observe_reverse(__BODY__, __DELAY__)
print("SNAPSHOT", int(done), state, success, cas_old, flush=True)
# A running target cannot be synchronized or freed.  Process teardown destroys
# its CUDA context and is the deliberate cleanup mechanism for this probe.
os._exit(0)
'''
    def reverse_snapshot(body, delay_s):
        reverse_py = (REVERSE_CHILD
                      .replace("__BASE__", str(Path(__file__).resolve().parents[2]))
                      .replace("__THIS__", THIS)
                      .replace("__BODY__", repr(body))
                      .replace("__DELAY__", repr(delay_s)))
        r = subprocess.run([sys.executable, "-c", reverse_py],
                           capture_output=True, text=True, timeout=8)
        fields = r.stdout.strip().split()
        if len(fields) != 5 or fields[0] != "SNAPSHOT":
            raise RuntimeError(f"unexpected stdout={r.stdout[:80]!r} "
                               f"stderr={r.stderr[:200]!r}")
        return tuple(map(int, fields[1:]))

    try:
        done, state, success, cas_old = reverse_snapshot("NOP", 2.0)
        good = not done and state == 1 and success == 0
        print(f"{'ok ' if good else 'FAIL'} reverse/NOP: "
              f"{'COMPLETED' if done else 'STILL SPINNING'} "
              f"state={state:#x} success={success:#x} cas_old={cas_old:#x}")
        if not good:
            ok = False
    except (subprocess.TimeoutExpired, RuntimeError) as e:
        print(f"FAIL reverse/NOP: could not take a live snapshot: {e}")
        ok = False

    # NANOSLEEP is the timed intra-warp handoff primitive.  Sweep zero and
    # nonzero durations: even NANOSLEEP 0 must give B's execution slot back to
    # A, producing the same atomic order as explicit YIELD.
    for ns in (0, 1, 0x20, 0x64):
        try:
            done, state, success, cas_old = reverse_snapshot(
                f"NANOSLEEP 0x{ns:x}", 0.25)
            good = done and state == 2 and success == 0xA2B2A and cas_old == 1
            print(f"{'ok ' if good else 'FAIL'} reverse/NANOSLEEP {ns:#x}: "
                  f"{'COMPLETED' if done else 'STILL SPINNING'} "
                  f"state={state:#x} success={success:#x} cas_old={cas_old:#x}")
            if not good:
                ok = False
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            print(f"FAIL reverse/NANOSLEEP {ns:#x}: {e}")
            ok = False

    print("\n=== intra-warp YIELD/NANOSLEEP forward progress: "
          f"{'ALL PASS' if ok else 'FAILURES'} ===")
    sys.exit(0 if ok else 1)
