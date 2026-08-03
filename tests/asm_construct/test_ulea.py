import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# ULEA — uniform load effective address (udp_pipe; verified SM120, RTX 5090)
#
#   ULEA.HI URd, UPu, [-]URa, URb|imm32, URc, scaleU5
#     0x1291 noimm / 0x1891 imm (URIUR); .HI is MANDATORY on sm_120
#     (HIONLY_lea has only the HI value).
#
# SILICON BEHAVIOR (32-bit result):
#   noimm: URd = URb + (URc << scale)      -- URa is NOT used!
#   imm:   URd = imm32 + (URc << scale)    -- URa is NOT used!
# The FORMAT's URa slot is present but does not contribute to the result in
# the base form (verified: varying URa from 0..0x100 leaves the result
# unchanged).  scale = 0..31.
#
# OPEN QUESTION: setting the negate bit (e=[72] for -URa, or [63] for -URb)
# yields a stable but unexpected result (e.g. URc - (scale<<5) for the
# probed inputs) that doesn't match "subtract the negated operand"; both
# -URa and -URb produce identical values and rb drops out.  Needs more
# investigation (possibly a sm_120 quirk of the negated form).
#
# Fields: Rd [23:16], URa [31:24], URb [39:32], URc (Ra_URc) [71:64],
# scaleU5 [79:75], e (URa negate) [72], URb negate [63], UPu [83:81],
# hilo [80].
# ---------------------------------------------------------------------------

REF = [
    (0x0000000706047291, 0x000fca000f8f1008),  # ULEA.HI UR4, UPT, UR6, UR7, UR8, 2
    (0x0000040006047891, 0x000fca000f8f1008),  # ULEA.HI UR4, UPT, UR6, 0x400, UR8, 2
    (0x0000000706047291, 0x000fca000b8f1408),  # ULEA.HI.X UR4, UPT, -UR6, UR7, UR8, 2, UPT
    (0x8000000706047291, 0x000fca000b8f1408),  # ULEA.HI.X UR4, UPT, UR6, ~UR7, UR8, 2, UPT
]
flat = assemble_flat("""ULEA.HI UR4, UPT, UR6, UR7, UR8, 0x2;[7:7:{}:5:1]
ULEA.HI UR4, UPT, UR6, 0x400, UR8, 0x2;[7:7:{}:5:1]
ULEA.HI.X UR4, UPT, -UR6, UR7, UR8, 0x2, UPT;[7:7:{}:5:1]
ULEA.HI.X UR4, UPT, UR6, ~UR7, UR8, 0x2, UPT;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(imm=None, x=False):
    if imm is not None:
        ulea = f"ULEA.HI UR16, UPT, UR6, 0x{imm:X}, UR8, "
        loads = ["    LDCU UR6, #param(a);[2:7:{}:1:0]\n",
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"]
        reqs = "{2,4}"
    else:
        ulea = "ULEA.HI.X UR16, UPT, UR6, UR7, UR8, " if x else \
               "ULEA.HI UR16, UPT, UR6, UR7, UR8, "
        loads = ["    LDCU UR6, #param(a);[2:7:{}:1:0]\n",
                 "    LDCU UR7, #param(b);[3:7:{}:1:0]\n",
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n",
                 "    UMOV UR9, UR7;[7:7:{3}:5:1]\n"]
        reqs = "{2,3,4}"
    loads.append("    LDCU UR8, #param(c);[4:7:{}:1:0]\n")
    loads.append(f"    UMOV UR9, UR8;[7:7:{{4}}:5:1]\n")
    tail = ", UPT" if x else ""
    return f"""#fn t(a<8>, b<8>, c<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
{''.join(loads)}    {ulea}{{scale}}{tail};[7:7:{reqs}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(src, a, b, c, scale):
    src = src.replace("{scale}", str(scale))
    mod = build(src)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a, b, c, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


try:
    build(kernel().replace("{scale}", "2"))
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# noimm: URd = URb + (URc << scale), URa unused.
for a, b, c, s, lab in [
    (0x10, 0x2, 0x4, 3, "noimm base"),
    (0x100, 0x2, 0x4, 3, "URa=0x100 ignored"),
    (0x10, 0x10, 0x4, 3, "rb=0x10"),
    (0x10, 0x2, 0x10, 3, "rc=0x10"),
    (0x10, 0x2, 0x4, 0, "scale=0"),
    (0x10, 0x2, 0x4, 5, "scale=5"),
    (0x10, 0x1, 0x1, 3, "1 + 1<<3"),
]:
    v = run(kernel(), a, b, c, s)
    exp = (b + (c << s)) & 0xFFFFFFFF
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:20s} -> 0x{v:08X} (exp 0x{exp:08X})")

# imm: URd = imm + (URc << scale), URa unused.
for a, imm, c, s, lab in [
    (0x10, 0x2, 0x4, 3, "imm base"),
    (0x100, 0x2, 0x4, 3, "imm URa ignored"),
    (0x10, 0x100, 0x1, 0, "imm 0x100 s=0"),
    (0x10, 0x5, 0x6, 2, "imm 5 rc=6 s=2"),
]:
    v = run(kernel(imm=imm), a, 0, c, s)
    exp = (imm + (c << s)) & 0xFFFFFFFF
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:20s} -> 0x{v:08X} (exp 0x{exp:08X})")

# .X form base behaves like noimm base (+1 observed — see note).
v = run(kernel(x=True), 0x10, 0x2, 0x4, 3)
print(f"info .X base -> 0x{v:08X} (noimm 0x22; .X adds 1 on this probe)")

print("\n=== ULEA semantic verification: ALL OK ===" if ok else "\n=== ULEA FAILURES ===")
sys.exit(0 if ok else 1)
