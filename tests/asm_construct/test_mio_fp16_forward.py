import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# mio_pipe (MUFU) -> fp16_pipe forwarding calibration (SM120)
#
# Same as test_mio_int_fma_forward.py but the consumer is a packed-half
# HADD2 pass-through (HADD2 R20, R10, RZ preserves R10's bits: both 0.5f
# 0x3F000000 and 4.0f 0x40800000 have a zero low half, so the packed add
# keeps them exact):
#   poison (settled): MOV32I R10, 0x40800000 (4.0f)
#   producer (mio_pipe): MUFU.RCP R10, R1   (R1=2.0) -> R10 = 0.5f
#   consumer (fp16_pipe): HADD2 R20, R10, RZ
# Consumers read WITHOUT a scoreboard req (deliberate undershoot); the spec's
# catch-all MIO_CBU_OPS -> ALL_OPS = 2 is expected too optimistic (mio does
# not fast-forward, cf. mio->int/fmal = 8).
# See notes/sm90/arch/pipe_forward_survey.md.
# ---------------------------------------------------------------------------

POISON = 0x40800000          # 4.0f bits
FRESH  = 0x3F000000          # 0.5f bits = rcp(2.0)
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 2                    # MIO_CBU_OPS -> ALL_OPS catch-all


def build_kernel(stalls):
    lines = ["#fn fwd(out<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    MOV32I R1, 0x40000000;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    MOV32I R10, 0x40800000;[7:7:{}:5:1]")
        lines += ["    NOP;[7:7:{}:7:1]"] * 2
        if S != 0:
            lines.append("    MUFU.RCP R10, R1;[7:7:{}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append("    HADD2 R20, R10, RZ;[7:7:{}:5:1]")
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
    return "F" if v == FRESH else ("S" if v == POISON else "?")


try:
    run([8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("mio(MUFU)->fp16 forwarding calibration (SM120); "
      "poison=4.0f fresh=0.5f")
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
print(f"MUFU->HADD2  Lspec={SPEC_L} [{'det' if det else 'var'}]: {sweep}")
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
if minG is None or minG < 5:
    ok = False
    print("        FAIL: expected mio->fp16 to be slow (minG>=5, no fast "
          "forwarding from the scoreboard-class mio producer)")
if not det:
    print("        WARN: boundary not deterministic")

print("\n=== mio->fp16 forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
