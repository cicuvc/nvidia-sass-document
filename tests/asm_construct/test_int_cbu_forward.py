import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# int_pipe -> cbu_pipe forwarding calibration (SM120, RTX 5090)
#
# Same stale/fresh boundary method, with the cbu consumer's effect observed by
# TIMING: the cbu op is NANOSLEEP R10, which sleeps for its register operand.
#   poison (pre-producer value) = 100000  -> ~89k cycles of sleep
#   producer (int pipe) IADD3 R10,RZ,RZ,RZ -> R10 = 0 -> ~85 cycles of sleep
# A CS2R delta around the NANOSLEEP reads ~85 (fresh) or ~89k (stale).
#
# One kernel PER stall value S (a single NANOSLEEP): running several
# NANOSLEEPs in one kernel corrupts the CS2R clock reads (long sleeps leave
# garbage clock values and later instances store zeros), so a single-sleep
# kernel per S is required.
#
# Measured (3 reps, best-of, sm_120): S=0 (poison-only) -> stale (89k cyc);
# S>=1 (producer + gap) -> fresh (~85 cyc).  So minG = 1: the int write is
# visible to the NANOSLEEP operand read at the minimum schedulable gap
# (~1.4 cyc).  The cbu operand-collect reads late, so the effective forward
# latency appears even shorter than int->int (minG=2).
#
# Spec sm120 TABLE_TRUE(GPR): FXU_OPS -> BRU_OPS = 6.
# See notes/sm90/arch/pipe_forwarding.md.
# ---------------------------------------------------------------------------

POISON_SLEEP = 1000000
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 6                     # TABLE_TRUE(GPR) FXU_OPS -> BRU_OPS

FRESH_MAX = 1000
STALE_MIN = 10000


def build_kernel(S):
    lines = ["#fn fwd(out<8>, poison<4>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]"]
    if S == 0:                       # poison-only control (no producer)
        lines.append("    LDC R10, #param(poison);[0:7:{}:2:0]")
        lines += ["    NOP;[7:7:{}:7:1]"] * 6
        lines.append("    MOV RZ, R10;[7:7:{0}:5:1]")
    else:
        lines.append("    LDC R10, #param(poison);[0:7:{}:2:0]")
        lines.append("    IADD3 R10, RZ, RZ, RZ;[7:7:{0}:1:1]")
        for _ in range(S - 1):
            lines.append("    NOP;[7:7:{}:1:1]")
    lines += ["    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
              "    NOP;[7:7:{}:5:0]",
              "    NANOSLEEP R10;[7:7:{}:5:1]",
              "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
              "    NOP;[7:7:{}:5:0]",
              "    MOV R12, R30;[7:7:{}:5:1]",
              "    MOV R13, R31;[7:7:{}:5:1]",
              "    MOV R14, R26;[7:7:{}:5:1]",
              "    MOV R15, R27;[7:7:{}:5:1]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R12;[0:1:{1,2}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R13;[0:1:{1,2}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0x8], R14;[0:1:{1,2}:1:0]",
              "    STG.E desc[{UR4,UR5}][{R6,R7}+0xC], R15;[0:1:{1,2}:1:0]",
              "    EXIT;[7:7:{}:5:0]",
              "}"]
    return "\n".join(lines)


def run(S):
    reset_context()
    cubin = assemble(build_kernel(S), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(64)
    mod.device_write(d, bytes(64))
    mod.launch("fwd", grid=(1,), block=(1,), args=[d, POISON_SLEEP])
    mod.synchronize()
    w = struct.unpack("<4I", mod.device_read(d, 16))
    mod.devmem_free(d)
    s = (w[1] << 32) | w[0]
    e = (w[3] << 32) | w[2]
    return (e - s) & ((1 << 64) - 1)


def classify(delta):
    return "F" if delta < FRESH_MAX else ("S" if delta > STALE_MIN else "?")


try:
    run(8)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("int->cbu (NANOSLEEP) forwarding calibration (SM120); "
      "poison sleep=%d (~980k cyc), fresh sleep=0 (~85 cyc)" % POISON_SLEEP)
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

deltas = [min(run(S) for _ in range(3)) for S in STALLS]
sweep = "".join(classify(d) for d in deltas)[SWEEP]
minG = None
for j in range(len(sweep)):
    if all(c == "F" for c in sweep[j:]):
        minG = STALLS[SWEEP][j]
        break
print(f"int->cbu  Lspec={SPEC_L}: {sweep}")
if minG is not None:
    print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
          f"overlap Lspec-minG={SPEC_L - minG}")
print("        deltas:", [d for d in deltas])

ok = True
if classify(deltas[0]) != "S":
    ok = False
    print("FAIL: poison-only control (S=0) should read stale (long sleep)")
if classify(deltas[-1]) != "F":
    ok = False
    print("FAIL: huge-gap control (stall 30) should be fresh")
if minG is None or minG < 1 or minG > 16:
    ok = False
    print("FAIL: could not resolve minG in the sweep range")
if minG is None or minG >= SPEC_L:
    ok = False
    print(f"FAIL: expected minG < L_table ({SPEC_L})")

print("\n=== int->cbu forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
