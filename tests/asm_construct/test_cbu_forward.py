import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# cbu_pipe (BMOV) -> int_pipe / mio_pipe forwarding calibration (SM120)
#
# cbu_pipe's only GPR writer is BMOV Rd, Bn (reads a barrier's participating
# mask).  A kernel-start BSSY B0 pushes the full active mask, so BMOV R10, B0
# -> R10 = 0x1 (block=1, lane 0).  Same stale/fresh boundary method:
#   poison: MOV32I R10, 0x12345678 (settled)
#   producer (cbu_pipe): BMOV R10, B0  -> R10 = 0x1
#   consumers:
#     int  : IADD3 R20, R10, RZ, RZ   (reads R10 at operand-collect)
#     mio  : STG.E [..], R10           (reads store DATA late)
# Detection: fresh = 0x1, stale = poison.
#
# Spec sm120: BMOV is in the MIO_CBU_OPS catch-all -> ALL_OPS = 2 (validate).
# See notes/sm90/arch/pipe_forward_survey.md.
# ---------------------------------------------------------------------------

POISON = 0x12345678
BMASK  = 0x00000001           # BSSY-pushed mask, lane 0 (block=1)
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 2                    # MIO_CBU_OPS -> ALL_OPS catch-all


def build_kernel(cons, stalls):
    lines = ["#fn fwd(out<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    BSSY B0, #label(done);[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    MOV32I R10, 0x12345678;[7:7:{}:5:1]")
        for _ in range(4):
            lines.append("    NOP;[7:7:{}:7:1]")
        if S != 0:
            lines.append("    BMOV R10, B0;[7:7:{}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        if cons == "int":
            lines.append("    IADD3 R20, R10, RZ, RZ;[7:7:{}:5:1]")
            lines += ["    NOP;[7:7:{}:5:1]"] * 8
            lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{1,2}}:1:0]")
        else:   # mio: store data read late
            lines += ["    NOP;[7:7:{}:5:1]"] * 4
            lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R10;[0:1:{{1,2}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("    #def_label(done)")
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
    return "F" if v == BMASK else ("S" if v == POISON else "?")


try:
    run("int", [8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("cbu(BMOV)->int / ->mio(STG data) forwarding calibration (SM120); "
      "BMASK=0x%08X poison=0x%08X" % (BMASK, POISON))
print("stall  : " + " ".join(f"{s:3d}" for s in STALLS[SWEEP]))

ok = True
for cons, tag in (("int", "BMOV->IADD3"), ("mio", "BMOV->STG   ")):
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
    if not det:
        print("        WARN: boundary not deterministic")
    ok &= good

print("\n=== cbu->int/mio forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
