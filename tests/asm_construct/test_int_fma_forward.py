import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# int_pipe / fmalighter_pipe GPR forwarding calibration (SM120, RTX 5090)
#
# Same method as test_udp_int_forward.py (stale/fresh boundary sweep), but in
# the GPR domain: a fixed-latency producer writes R10, a fixed-latency
# consumer reads it, separated by a swept stall gap S.  At small S the
# consumer reads the poison; at sufficient S it reads the producer's TRUE.
#
# Pipes / ops:
#   int_pipe     : IADD3 R10, R11, RZ, RZ   (R10 = R11, integer)
#   fmalighter   : FADD R10, R11, RZ        (R10 = R11 + 0.0)
#   consumer int : IADD3 R20, R10, RZ, RZ
#   consumer fmal: FADD R20, R10, RZ
# R11 = R12 = 0x3F800000 (1.0) so TRUE=1.0 bits for every config; poison =
# 0x40000000 (2.0) so even the fmal FADD pass-through preserves the poison
# bits exactly (both are normal fp32).
#
# Spec sm120 TABLE_TRUE(GPR) reference:
#   int->int      (FXU_OPS->FXU_OPS)           L = 6
#   fmal->fmal    (FMAI->FMAI)                 L = 4
#   int->fmal     (FXU_OPS->FMAI)              L = 6
#   fmal->int     (FMAI->FXU_OPS)              L = 5
# The sweep reports the measured minG stall per pair (usched_latency's
# usched_probe found sm90 int->int minG=4, i.e. overlap 2; fmal->fmal 4).
# See notes/sm90/arch/pipe_forwarding.md.
# ---------------------------------------------------------------------------

POISON = 0x40000000          # 2.0f bits - valid fp so fmal preserves it
TRUE   = 0x3F800000          # 1.0f bits
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)

# spec sm120 TABLE_TRUE(GPR) cells (parse_latencies.py lookup TRUE GPR ...)
SPEC_L = {("IADD3", "IADD3"): 6, ("FADD", "FADD"): 4,
          ("IADD3", "FADD"): 6, ("FADD", "IADD3"): 5}

PROD = {
    "IADD3": "IADD3 R10, R11, RZ, RZ",
    "FADD":  "FADD R10, R11, RZ",
}
CONS = {
    "IADD3": "IADD3 R20, R10, RZ, RZ",
    "FADD":  "FADD R20, R10, RZ",
}


def build_kernel(prod, cons, stalls):
    lines = ["#fn fwd(out<8>, poison<4>, a<4>, b<4>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    MOV32I R11, 0x3f800000;[7:7:{}:5:1]",
             "    MOV32I R12, 0x3f800000;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        if S == 0:                      # poison-only control
            lines.append("    LDC R10, #param(poison);[0:7:{}:2:0]")
            lines += ["    NOP;[7:7:{}:7:1]"] * 6
            # first read of a freshly-LDC'd register + scoreboard commit need
            # a req'd dummy read before the real one
            lines.append(f"    {CONS[cons].replace('R20', 'RZ')};[7:7:{{0}}:5:1]")
            lines.append(f"    {CONS[cons]};[7:7:{{}}:5:1]")
        else:
            lines.append("    LDC R10, #param(poison);[0:7:{}:2:0]")
            lines.append(f"    {PROD[prod]};[7:7:{{0}}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
            lines.append(f"    {CONS[cons]};[7:7:{{}}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 8
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(prod, cons, stalls):
    reset_context()
    cubin = assemble(build_kernel(prod, cons, stalls), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("fwd", grid=(1,), block=(1,),
               args=[d, POISON, TRUE, 0x3f800000])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == TRUE else ("S" if v == POISON else "?")


try:
    run("IADD3", "IADD3", [8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("int/fmalighter GPR forwarding calibration (SM120); "
      "poison=0x%08X(2.0f) true=0x%08X(1.0f)" % (POISON, TRUE))
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

ok = True
for prod, cons in [("IADD3", "IADD3"), ("FADD", "FADD"),
                   ("IADD3", "FADD"), ("FADD", "IADD3")]:
    reps = [run(prod, cons, STALLS) for _ in range(3)]
    maj = "".join("F" if sum(1 for r in reps if r[i] == TRUE) >= 2
                  else ("S" if sum(1 for r in reps if r[i] == POISON) >= 2
                        else "?")
                  for i in range(len(STALLS)))
    det = all(r == reps[0] for r in reps)
    lspec = SPEC_L[(prod, cons)]
    sweep = maj[SWEEP]
    minG = None
    for j in range(len(sweep)):
        if all(c == "F" for c in sweep[j:]):
            minG = STALLS[SWEEP][j]
            break
    print(f"{prod:6s}->{cons:6s} Lspec={lspec} "
          f"[{'det' if det else 'var'}]: {sweep}")
    if minG is not None:
        print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
              f"overlap Lspec-minG={lspec - minG}")

    good = True
    if maj[0] != "S":
        good = False
        print("        FAIL: poison-only control should read poison")
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
        print("        WARN: boundary not deterministic across reps (alignment zone)")
    ok &= good

print("\n=== int/fmalighter forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
