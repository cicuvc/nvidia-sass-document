import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# int_pipe / fmalighter_pipe / fp16_pipe -> fp16_pipe forwarding (SM120)
#
# Same stale/fresh boundary method.  Consumers are packed-half HADD2
# pass-throughs (HADD2 R20, R10, RZ = R10 + 0.0 packed).  Producers write
# R10 = TRUE = 0x3C003C00 (packed 1.0|1.0); poison 0x3A003A00 (0.5|0.5),
# both preserved bit-exactly by every pass-through.
#   producer int  : IADD3 R10, R11, RZ, RZ    (R10 = R11)
#   producer fmal : FADD  R10, R11, RZ        (R10 = R11 + 0.0)
#   producer fp16 : HADD2 R10, R11, RZ        (R10 = R11 + 0.0 packed)
#
# Spec sm120 TABLE_TRUE(GPR): FXU->FP16=6, FMAI->FP16=6, FP16->FP16=5.
# See notes/sm90/arch/pipe_forward_survey.md.
# ---------------------------------------------------------------------------

POISON = 0x3A003A00          # packed 0.5|0.5
TRUE   = 0x3C003C00          # packed 1.0|1.0
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)

SPEC_L = {
    ("IADD3", "HADD2"): 6, ("FADD", "HADD2"): 6, ("HADD2", "HADD2"): 5,
}
PROD = {
    "IADD3": "IADD3 R10, R11, RZ, RZ",
    "FADD":  "FADD R10, R11, RZ",
    "HADD2": "HADD2 R10, R11, RZ",
}
CONS = "HADD2 R20, R10, RZ"


def build_kernel(prod, stalls):
    prod_text = PROD[prod]
    lines = ["#fn fwd(out<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    MOV32I R11, 0x3c003c00;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    MOV32I R10, 0x3a003a00;[7:7:{}:5:1]")
        for _ in range(4):
            lines.append("    NOP;[7:7:{}:7:1]")
        if S != 0:
            lines.append(f"    {prod_text};[7:7:{{}}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append(f"    {CONS};[7:7:{{}}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 8
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(prod, stalls):
    reset_context()
    cubin = assemble(build_kernel(prod, stalls), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("fwd", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == TRUE else ("S" if v == POISON else "?")


try:
    run("IADD3", [8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("->fp16 (HADD2 packed) forwarding calibration (SM120); "
      "poison=0x%08X(0.5|0.5) true=0x%08X(1.0|1.0)" % (POISON, TRUE))
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

ok = True
for prod, cons in (("IADD3", "HADD2"), ("FADD", "HADD2"), ("HADD2", "HADD2")):
    reps = [run(prod, STALLS) for _ in range(3)]
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
    lspec = SPEC_L[(prod, cons)]
    print(f"{prod:6s}->{cons:6s} Lspec={lspec} "
          f"[{'det' if det else 'var'}]: {sweep}")
    if minG is not None:
        print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
              f"overlap Lspec-minG={lspec - minG}")
    good = True
    if maj[0] != "S":
        good = False
        print("        FAIL: poison-only control should read stale")
    if maj[-1] != "F":
        good = False
        print("        FAIL: huge-gap control (stall 30) should be fresh")
    if minG is None or minG < 1 or minG > 16:
        good = False
        print("        FAIL: could not resolve minG in the sweep range")
    if minG is None or minG >= lspec:
        good = False
        print(f"        FAIL: expected minG < L_table ({lspec})")
    if not det:
        print("        WARN: boundary not deterministic")
    ok &= good

print("\n=== ->fp16 forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
