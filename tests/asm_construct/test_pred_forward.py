import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# fp16_pipe (HSETP2) -> cbu_pipe (@P0 BRA) PREDICATE forwarding (SM120)
#
# Same as test_int_cbu_pred_forward.py but the P0=true producer is the fp16
# packed-half set-predicate HSETP2.EQ.AND P0, PT, RZ, RZ, PT (RZ==RZ per
# half -> true).  Poison = ISETP.F P0 (false, settled); consumer @P0 BRA
# branches to a true-marker or falls through to a stale-marker.
# Spec sm120 TABLE_TRUE(PRED): FP16_OPS -> BRU_OPS = 13.
# Both fine (many stall-1 NOPs) and coarse (few big-stall NOPs) gaps are swept
# (the ISETP->BRA test showed the two disagree: coarse == spec 13, fine opens
# a fragile bypass window).
# See notes/sm90/arch/pipe_forward_survey.md.
# ---------------------------------------------------------------------------

M_STALE = 0x5AA50000
M_TRUE  = 0x5AA50001
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 13                    # FP16_OPS -> BRU_OPS


def build_kernel(stalls, coarse):
    lines = ["#fn fwd(out<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    ISETP.F P0, RZ, RZ;[7:7:{}:13:1]")
        for _ in range(4):
            lines.append("    NOP;[7:7:{}:7:1]")
        if S != 0:
            lines.append("    HSETP2.EQ.AND P0, PT, RZ, RZ, PT;[7:7:{}:1:1]")
            rem = S - 1
            while rem > 0:
                if coarse:
                    lines.append(f"    NOP;[7:7:{{}}:{min(7, rem)}:1]")
                    rem -= min(7, rem)
                else:
                    lines.append("    NOP;[7:7:{}:1:1]")
                    rem -= 1
        t, d = f"tlbl{i}", f"dlbl{i}"
        lines.append(f"    @P0 BRA #label({t});[7:7:{{}}:5:1]")
        lines.append(f"    MOV32I R20, 0x{M_STALE:08x};[7:7:{{}}:5:1]")
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
        lines.append(f"    BRA #label({d});[7:7:{{}}:5:1]")
        lines.append(f"    #def_label({t})")
        lines.append(f"    MOV32I R20, 0x{M_TRUE:08x};[7:7:{{}}:5:1]")
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
        lines.append(f"    #def_label({d})")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(stalls, coarse):
    reset_context()
    cubin = assemble(build_kernel(stalls, coarse), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("fwd", grid=(1,), block=(1,), args=[d])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == M_TRUE else ("S" if v == M_STALE else "?")


def boundary(coarse):
    reps = [run(STALLS, coarse) for _ in range(3)]
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
    return maj, minG, det


try:
    run([8], coarse=False)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("fp16 predicate (HSETP2 P0 -> @P0 BRA) forwarding (SM120); "
      "poison P0=false, true P0=true")
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

res = {}
for coarse, tag in ((False, "fine  "), (True, "coarse")):
    maj, minG, det = boundary(coarse)
    res[coarse] = (maj, minG)
    print(f"HSETP2->BRA {tag} [{'det' if det else 'var'}]: {maj[SWEEP]}")
    if minG is not None:
        print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
              f"overlap Lspec-minG={SPEC_L - minG}")

maj_f, minG_f = res[False]
maj_c, minG_c = res[True]

ok = True
for tag, maj in (("fine", maj_f), ("coarse", maj_c)):
    if maj[0] != "S":
        ok = False
        print(f"FAIL [{tag}]: poison-only control should read stale")
    if maj[-1] != "F":
        ok = False
        print(f"FAIL [{tag}]: huge-gap control (stall 30) should be fresh")
if minG_f is None or minG_c is None:
    ok = False
    print("FAIL: could not resolve a boundary")
else:
    if not (1 <= minG_f <= 16 and 1 <= minG_c <= 16):
        ok = False
        print("FAIL: minG out of sweep range")
    # predicate path is genuinely slow (no fast bypass): coarse mode must be
    # at/near the spec 13, and fine mode must not beat the GPR forwarding floor
    if not (SPEC_L - 3 <= minG_c <= SPEC_L):
        ok = False
        print(f"FAIL: expected coarse-mode minG near L_table ({SPEC_L}), got {minG_c}")
    if minG_f < 3:
        ok = False
        print(f"FAIL: fine-mode minG={minG_f} too small for a non-forwarding predicate path")

print("\n=== fp16 predicate (HSETP2->BRA) forwarding: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
