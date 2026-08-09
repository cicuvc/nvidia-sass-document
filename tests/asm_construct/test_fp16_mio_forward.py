import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# fp16_pipe -> mio_pipe forwarding calibration (SM120)
#
# A packed-half producer cannot construct a memory ADDRESS losslessly (the
# packed fp16 bits are not a valid address), so the mio consumer here is
# MUFU.RCP reading the fp16-produced value as an fp32 scalar:
#   poison (settled): MOV32I R10, 0x40000000   (2.0f)
#   producer (fp16_pipe): HADD2 R10, R11, RZ   = R11 + 0.0 packed
#            R11 = 0x3F800000 = (1.0, 0.0) packed == 1.0 as fp32 -> R10 = 1.0
#   consumer (mio_pipe): MUFU.RCP R20, R10
#            fresh R20 = rcp(1.0) = 1.0 (0x3F800000); stale = rcp(2.0)=0.5
# Spec sm120 TABLE_TRUE(GPR): FP16_OPS -> MIO_FAST_OPS = 6.
# See notes/sm90/arch/pipe_forward_survey.md.
# ---------------------------------------------------------------------------

STALE = 0x3F000000            # rcp(2.0) = 0.5
FRESH = 0x3F800000            # rcp(1.0) = 1.0
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 6                    # FP16_OPS -> MIO_FAST_OPS


def build_kernel(stalls):
    lines = ["#fn fwd(out<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    MOV32I R11, 0x3f800000;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    MOV32I R10, 0x40000000;[7:7:{}:5:1]")
        for _ in range(4):
            lines.append("    NOP;[7:7:{}:7:1]")
        if S != 0:
            lines.append("    HADD2 R10, R11, RZ;[7:7:{}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append("    MUFU.RCP R20, R10;[7:7:{}:5:1]")
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
    mod.launch("fwd", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == FRESH else ("S" if v == STALE else "?")


try:
    run([8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("fp16->mio (HADD2 -> MUFU.RCP) forwarding calibration (SM120); "
      "stale=rcp(2.0)=0x%08X fresh=rcp(1.0)=0x%08X" % (STALE, FRESH))
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
print(f"HADD2->MUFU  Lspec={SPEC_L} [{'det' if det else 'var'}]: {sweep}")
if minG is not None:
    print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
          f"overlap Lspec-minG={SPEC_L - minG}")
print("        raw:", [classify(v) for v in reps[0]])

ok = True
if maj[0] != "S":
    ok = False
    print("        FAIL: poison-only control should read stale")
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
    print("        WARN: boundary not deterministic")

print("\n=== fp16->mio forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
