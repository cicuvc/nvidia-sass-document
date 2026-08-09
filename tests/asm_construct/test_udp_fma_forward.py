import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# udp_pipe -> fmalighter_pipe forwarding calibration (SM120, RTX 5090)
#
# Same stale/fresh boundary method as test_udp_int_forward.py, but the int
# consumer is replaced by an fmalighter FFMA reading the uniform register via
# the ffma__RRU_RRU variant:
#   producer (udp_pipe)  UIADD3 UR10, UPT, UPT, UR11, UR12, URZ  (UR10 = TRUE)
#   consumer (fmalighter) FFMA R20, R11, RZ, UR10   = 1.0*0.0 + UR10 = UR10
# R11 = 1.0 (MOV32I at kernel start), TRUE = 0x3F800000 (1.0f), poison =
# 0x40000000 (2.0f) - both normal fp32 so the FFMA pass-through preserves bits.
#
# Spec sm120 UGPR TABLE_TRUE: UDP_subset -> MATH_OPS = 12.
# See notes/sm90/arch/pipe_forwarding.md.
# ---------------------------------------------------------------------------

POISON = 0x40000000          # 2.0f bits
TRUE   = 0x3F800000          # 1.0f bits
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 12                  # UDP_subset -> MATH_OPS


def build_kernel(stalls):
    lines = ["#fn fwd(out<8>, poison<4>, a<4>, b<4>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    LDCU UR11, #param(a);[0:7:{}:2:0]",
             "    LDCU UR12, #param(b);[0:7:{}:2:0]",
             "    MOV32I R11, 0x3f800000;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        if S == 0:                      # poison-only control
            lines.append("    LDCU UR10, #param(poison);[0:7:{}:2:0]")
            lines += ["    NOP;[7:7:{}:7:1]"] * 6
            lines.append("    MOV RZ, UR10;[7:7:{0}:5:1]")
        else:
            lines.append("    LDCU UR10, #param(poison);[0:7:{}:2:0]")
            lines.append("    UIADD3 UR10, UPT, UPT, UR11, UR12, URZ;[7:7:{0}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append("    FFMA R20, R11, RZ, UR10;[7:7:{}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 8
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(stalls):
    reset_context()
    cubin = assemble(build_kernel(stalls), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("fwd", grid=(1,), block=(1,),
               args=[d, POISON, TRUE, 0])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == TRUE else ("S" if v == POISON else "?")


try:
    run([8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("udp->fmalighter (FFMA RRU) forwarding calibration (SM120); "
      "poison=0x%08X(2.0f) true=0x%08X(1.0f)" % (POISON, TRUE))
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

reps = [run(STALLS) for _ in range(3)]
maj = "".join("F" if sum(1 for r in reps if classify(r[i]) == "F") >= 2
              else ("S" if sum(1 for r in reps if classify(r[i]) == "S") >= 2
                    else "?")
              for i in range(len(STALLS)))
det = all(r == reps[0] for r in reps)
sweep = maj[SWEEP]
minG = None
for j in range(len(sweep)):
    if all(c == "F" for c in sweep[j:]):
        minG = STALLS[SWEEP][j]
        break
print(f"UIADD3->FFMA  Lspec={SPEC_L} [{'det' if det else 'var'}]: {sweep}")
if minG is not None:
    print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
          f"overlap Lspec-minG={SPEC_L - minG}")

ok = True
if maj[0] != "S":
    ok = False
    print("        FAIL: poison-only control should read poison")
if maj[-1] != "F":
    ok = False
    print("        FAIL: huge-gap control (stall 30) should be fresh")
if minG is None or minG < 1 or minG > 16:
    ok = False
    print("        FAIL: could not resolve minG in the sweep range")
if minG is None or minG >= SPEC_L:
    ok = False
    print(f"        FAIL: expected minG < L_table ({SPEC_L})")
if not det:
    print("        WARN: boundary not deterministic across reps (alignment zone)")

print("\n=== udp->fmalighter forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
