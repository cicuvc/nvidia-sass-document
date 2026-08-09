import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# fp16_pipe -> int_pipe / fmalighter_pipe forwarding calibration (SM120)
#
# Same stale/fresh boundary method, GPR domain.  Producer is a packed-half
# HADD2 on the fp16 pipe:
#   poison (settled): MOV32I R10, 0x3A003A00   (packed 0.5|0.5)
#   producer (fp16_pipe): HADD2 R10, R11, RZ    = R11 + 0.0 packed -> R11
#            with R11 = 0x3C003C00 (packed 1.0|1.0), so R10 = TRUE
#   consumers read R10:
#     int  : IADD3 R20, R10, RZ, RZ
#     fmal : FADD  R20, R10, RZ   (0x3C003C00 / 0x3A003A00 are normal fp32)
# Both TRUE and poison are preserved bit-exactly by the pass-through.
#
# Spec sm120 TABLE_TRUE(GPR): FP16_OPS -> FXU_OPS = 5, -> FMAI = 5.
# See notes/sm90/arch/pipe_forwarding.md.
# ---------------------------------------------------------------------------

POISON = 0x3A003A00          # packed 0.5|0.5
TRUE   = 0x3C003C00          # packed 1.0|1.0
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 5                    # FP16_OPS -> FXU_OPS / FMAI_WITHOUT_IMAD

CONSUMERS = {
    "int":  "IADD3 R20, R10, RZ, RZ",
    "fmal": "FADD R20, R10, RZ",
}


def build_kernel(cons, stalls):
    cons_text = CONSUMERS[cons]
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
            lines.append("    HADD2 R10, R11, RZ;[7:7:{}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append(f"    {cons_text};[7:7:{{}}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 8
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(cons, stalls):
    reset_context()
    cubin = assemble(build_kernel(cons, stalls), check_deps=False)
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
    run("int", [8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("fp16->int/fmal (HADD2 packed) forwarding calibration (SM120); "
      "poison=0x%08X(0.5|0.5) true=0x%08X(1.0|1.0)" % (POISON, TRUE))
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

ok = True
for cons, tag in (("int", "HADD2->IADD3"), ("fmal", "HADD2->FADD ")):
    reps = [run(cons, STALLS) for _ in range(3)]
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
    print(f"{tag}  Lspec={SPEC_L} [{'det' if det else 'var'}]: {sweep}")
    if minG is not None:
        print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
              f"overlap Lspec-minG={SPEC_L - minG}")
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
    if minG is None or minG >= SPEC_L:
        good = False
        print(f"        FAIL: expected minG < L_table ({SPEC_L})")
    if not det:
        print("        WARN: boundary not deterministic")
    ok &= good

print("\n=== fp16->int/fmal forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
