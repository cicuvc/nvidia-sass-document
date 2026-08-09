import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
from assembler.runner import reset_context

# ---------------------------------------------------------------------------
# fmalighter_pipe -> mio_pipe (LDG address/AGU) forwarding calibration (SM120)
#
# Same as test_int_mio_forward.py but the address pair is produced by
# fmalighter FFMA pass-throughs instead of an int MOV.64:
#   poison : LDC.64 {R10,R11} = addrA (wr=SB0; buffer A holds marker MA)
#   producer (fmalighter): FFMA R10,R16,R12,RZ ; FFMA R11,R17,R12,RZ
#            (R12=1.0, R16:R17=addrB) -> {R10,R11} = addrB
#   consumer (mio_pipe): LDG.E R20 from {R10,R11}
# Stale -> loads marker MA from buffer A; fresh -> marker MB from buffer B.
#
# Spec sm120 TABLE_TRUE(GPR): FMAI_WITHOUT_IMAD -> MIO_FAST_OPS = 6.
# See notes/sm90/arch/pipe_forwarding.md.
# ---------------------------------------------------------------------------

MA = 0x11111111
MB = 0x22222222
STALLS = [0] + list(range(1, 17)) + [30]
SWEEP = slice(1, 1 + 16)
SPEC_L = 6                     # FMAI_WITHOUT_IMAD -> MIO_FAST_OPS


def build_kernel(stalls):
    lines = ["#fn fwd(out<8>, addrA<8>, addrB<8>) {",
             "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
             "    LDC.64 {R6, R7}, #param(out);[2:7:{}:1:0]",
             "    LDC.64 {R16, R17}, #param(addrB);[3:7:{}:2:0]",
             "    MOV32I R12, 0x3f800000;[7:7:{}:5:1]"]
    for i, S in enumerate(stalls):
        off = 4 * i
        lines.append("    LDC.64 {R10, R11}, #param(addrA);[0:7:{}:2:0]")
        if S == 0:                      # poison-only control (no producer)
            lines += ["    NOP;[7:7:{}:7:1]"] * 6
            lines.append("    MOV RZ, R10;[7:7:{0}:5:1]")
        else:
            lines.append("    FFMA R10, R16, R12, RZ;[7:7:{0}:1:1]")
            lines.append("    FFMA R11, R17, R12, RZ;[7:7:{}:1:1]")
            for _ in range(S - 1):
                lines.append("    NOP;[7:7:{}:1:1]")
        lines.append("    LDG.E R20, desc[{UR4,UR5}][{R10,R11}+0x0];[4:7:{1}:5:1]")
        lines += ["    NOP;[7:7:{}:5:1]"] * 4
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R20;[0:1:{{4,2,1}}:1:0]")
    lines.append("    EXIT;[7:7:{}:5:0]")
    lines.append("}")
    return "\n".join(lines)


def run(stalls):
    reset_context()
    cubin = assemble(build_kernel(stalls), check_deps=False)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    bufA = mod.devmem_alloc(64)
    bufB = mod.devmem_alloc(64)
    mod.device_write(bufA, struct.pack("<I", MA))
    mod.device_write(bufB, struct.pack("<I", MB))
    mod.launch("fwd", grid=(1,), block=(1,), args=[d, bufA, bufB])
    mod.synchronize()
    vals = struct.unpack("<%dI" % len(stalls), mod.device_read(d, len(stalls) * 4))
    for b in (bufA, bufB):
        mod.devmem_free(b)
    mod.devmem_free(d)
    return vals


def classify(v):
    return "F" if v == MB else ("S" if v == MA else "?")


try:
    run([8])
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0)

print("fmal->mio (LDG address/AGU) forwarding calibration (SM120); "
      "marker A=0x%08X marker B=0x%08X" % (MA, MB))
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
print(f"FFMA->LDG  Lspec={SPEC_L} [{'det' if det else 'var'}]: {sweep}")
if minG is not None:
    print(f"        minG stall={minG} (real gap ~{minG + 0.4:.1f}cyc), "
          f"overlap Lspec-minG={SPEC_L - minG}")
print("        raw:", [classify(v) for v in reps[0]])

ok = True
if maj[0] != "S":
    ok = False
    print("        FAIL: poison-only control should read stale (marker A)")
if maj[-1] != "F":
    ok = False
    print("        FAIL: huge-gap control (stall 30) should be fresh (marker B)")
if minG is None or minG < 1 or minG > 16:
    ok = False
    print("        FAIL: could not resolve minG in the sweep range")
if minG is None or minG >= SPEC_L:
    ok = False
    print(f"        FAIL: expected minG < L_table ({SPEC_L})")
if not det:
    print("        WARN: boundary not deterministic across reps")

print("\n=== fmal->mio forwarding calibration: "
      + ("ALL OK" if ok else "FAILURES") + " ===")
sys.exit(0 if ok else 1)
