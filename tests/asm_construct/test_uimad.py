import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UIMAD — uniform integer multiply-add (udp_pipe; verified SM120, RTX 5090)
#
#   UIMAD[.LO|.HI|.WIDE] URd, UPu, URa, URb|imm32, URc|imm32   (0x12a4 LO /
#     0x12a6 HI / 0x12a5 WIDE; imm variants 0x18a4/0x14a4/...)
#
# NOTE: plain `UIMAD` (no modifier) matches the **HI** variant on sm_120
# (opposite of IMAD, where plain = LO).  All multiplies are SIGNED (S32):
#   LO:   URd = (signed(a) * signed(b) + URc) & 0xFFFFFFFF
#   HI:   URd = high32(signed64(a) * signed64(b)) + URc   (addend -> high!)
#   WIDE: {URd,URd+1} = signed64(a) * signed64(b) + signed64(c) (c = pair)
# ---------------------------------------------------------------------------

REF = [
    (0x00000007060472a4, 0x000fca000f8e0208),  # UIMAD.LO UR4, UR6, UR7, UR8
    (0x00000007060472a6, 0x000fca000f8e0208),  # UIMAD.HI UR4, UR6, UR7, UR8
    (0x12345678060478a6, 0x000fca000f8e0208),  # UIMAD.HI UR4, UR6, imm, UR8
    (0x12345678060474a4, 0x000fca000f8e0207),  # UIMAD.LO UR4, UR6, UR7, imm
    (0x00000007060472a5, 0x000fca000f8e0208),  # UIMAD.WIDE
]
flat = assemble_flat("""UIMAD.LO UR4, UR6, UR7, UR8;[7:7:{}:5:1]
UIMAD.HI UR4, UR6, UR7, UR8;[7:7:{}:5:1]
UIMAD.HI UR4, UR6, 0x12345678, UR8;[7:7:{}:5:1]
UIMAD.LO UR4, UR6, UR7, 0x12345678;[7:7:{}:5:1]
UIMAD.WIDE {UR4,UR5}, UR6, UR7, {UR8,UR9};[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def s32(x):
    return x - 0x100000000 if x & 0x80000000 else x


def kernel(inst, wide=False):
    if wide:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR7, #param(b);[3:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR7;[7:7:{3}:5:1]\n")
        reqs = "{2,3}"
        dst = "{UR16,UR17}"
    else:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR7, #param(b);[3:7:{}:1:0]\n"
                 "    LDCU UR8, #param(c);[4:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR7;[7:7:{3}:5:1]\n"
                 "    UMOV UR9, UR8;[7:7:{4}:5:1]\n")
        reqs = "{2,3,4}"
        dst = "UR17"
    dums = "".join(f"    UMOV UR9, UR16;[7:7:{{}}:5:1]\n" for _ in range(3))
    dums += "".join(f"    UMOV UR9, UR17;[7:7:{{}}:5:1]\n" for _ in range(3))
    if wide:
        rd = ("    UMOV UR14, UR16;[7:7:{}:5:1]\n    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{}:8:1]\n"
              "    UMOV UR14, UR17;[7:7:{}:5:1]\n    IADD3 R3, PT, PT, RZ, UR14, RZ;[7:7:{}:8:1]\n")
    else:
        rd = ("    UMOV UR14, UR17;[7:7:{}:5:1]\n    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{}:8:1]\n"
              "    UMOV UR14, UR16;[7:7:{}:5:1]\n    IADD3 R3, PT, PT, RZ, UR14, RZ;[7:7:{}:8:1]\n")
    return f"""#fn t(a<8>, b<8>, c<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
{loads}    {inst.replace('{dst}', dst)}[7:7:{reqs}:5:1]
{dums}{rd}
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a, b, c, wide=False):
    mod = build(kernel(inst, wide=wide))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,),
               args=[a & 0xFFFFFFFF, b & 0xFFFFFFFF, c & 0xFFFFFFFF, d])
    mod.synchronize()
    lo, hi = struct.unpack("<2I", mod.device_read(d, 8))
    mod.devmem_free(d)
    return lo, hi


try:
    run("UIMAD.LO UR17, UR6, UR7, UR8;", 5, 10, 100)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# LO: signed multiply-add, low 32.
lo_cases = [
    (5, 10, 100, 150),
    (0xFFFFFFFF, 0xFFFFFFFF, 0, 1),
    (0xFFFFFFFF, 2, 0, 0xFFFFFFFE),
    (0x12345678, 0x100, 1, (s32(0x12345678) * 0x100 + 1) & 0xFFFFFFFF),
]
for a, b, c, exp in lo_cases:
    lo, _ = run("UIMAD.LO UR17, UR6, UR7, UR8;", a, b, c)
    good = lo == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} LO {hex(a)}*{hex(b)}+{hex(c)} = 0x{lo:08X} (exp 0x{exp:08X})")

# HI: high32(signed product) + URc (addend to the high word).
hi_cases = [
    (0x10000, 0x10000, 5, 6),
    (0xFFFFFFFF, 0xFFFFFFFF, 0, 0),
    (0xFFFFFFFF, 2, 0, 0xFFFFFFFF),
    (5, 10, 100, 100),
]
for a, b, c, exp in hi_cases:
    lo, _ = run("UIMAD.HI UR17, UR6, UR7, UR8;", a, b, c)
    exp2 = ((s32(a) * s32(b)) >> 32) + c
    good = lo == (exp2 & 0xFFFFFFFF)
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} HI {hex(a)}*{hex(b)}+{hex(c)} = 0x{lo:08X} (exp 0x{exp2 & 0xFFFFFFFF:08X})")

# Plain UIMAD == HI (sm_120 default).
lo, _ = run("UIMAD UR17, UR6, UR7, UR8;", 0x10000, 0x10000, 5)
good = lo == 6
ok &= good
print(f"{'ok ' if good else 'FAIL'} plain UIMAD == HI: 0x{lo:08X} (exp 0x6)")

# WIDE: signed 64-bit product.
wide_cases = [
    (0xFFFFFFFF, 0xFFFFFFFF, 1),
    (0x12345678, 0x9ABCDEF0, (s32(0x12345678) * s32(0x9ABCDEF0)) & 0xFFFFFFFFFFFFFFFF),
    (0x00010000, 0x00020000, 0x200000000),
    (0x7FFFFFFF, 0x7FFFFFFF, 0x3FFFFFFF00000001),
]
for a, b, exp in wide_cases:
    lo, hi = run("UIMAD.WIDE {UR16,UR17}, UR6, UR7, {URZ,URZ};", a, b, 0, wide=True)
    got = (hi << 32) | lo
    good = got == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} WIDE {hex(a)}*{hex(b)} = 0x{got:016X} (exp 0x{exp:016X})")

# imm forms.
lo, _ = run("UIMAD.LO UR17, UR6, 0x12345678, UR8;", 5, 0, 100)
exp = (5 * 0x12345678 + 100) & 0xFFFFFFFF
good = lo == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} LO imm Sb = 0x{lo:08X} (exp 0x{exp:08X})")

print("\n=== UIMAD semantic verification: ALL OK ===" if ok else "\n=== UIMAD FAILURES ===")
sys.exit(0 if ok else 1)
