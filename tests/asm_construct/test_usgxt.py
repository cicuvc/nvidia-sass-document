import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# USGXT — uniform sign/zero-extend (udp_pipe; verified SM120, RTX 5090)
#
#   USGXT[.W][.U32] URd, URa, URb|imm32     (0x129a UUU / 0x189a imm)
#   Same semantics as SGXT (identical cw/fmt bit positions [75]/[73]):
#   extend the low N bits of URa to 32 bits, N = URb.
#     .U32 zero-extends, default .S32 sign-extends; N=0 -> 0.
#     .C (clamp): N >= 32 -> URa unchanged (N unmasked).
#     .W (wrap):  N mod 32 (N=32 -> 0, N=33 -> 1).
# ---------------------------------------------------------------------------

REF = [
    (0x000000080604729a, 0x000fca0008000200),  # USGXT UR4, UR6, UR8 (S32 C)
    (0x000000080604729a, 0x000fca0008000a00),  # .W
    (0x000000080604729a, 0x000fca0008000000),  # .U32
    (0x000000080604729a, 0x000fca0008000800),  # .W.U32
    (0x000000050604789a, 0x000fca0008000200),  # imm 0x5
]
flat = assemble_flat("""USGXT UR4, UR6, UR8;[7:7:{}:5:1]
USGXT.W UR4, UR6, UR8;[7:7:{}:5:1]
USGXT.U32 UR4, UR6, UR8;[7:7:{}:5:1]
USGXT.W.U32 UR4, UR6, UR8;[7:7:{}:5:1]
USGXT UR4, UR6, 0x5;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"
DUMS = "".join(f"    UMOV UR9, UR16;[7:7:{{}}:5:1]\n" for _ in range(4))


def kernel(inst):
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    LDCU UR8, #param(b);[3:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
    {inst}[7:7:{{2,3}}:5:1]
{DUMS}    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a, n):
    mod = build(kernel(inst))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[a & 0xFFFFFFFF, n & 0xFFFFFFFF, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


def sext(x, n):
    if n == 0:
        return 0
    if n >= 32:
        return x & 0xFFFFFFFF
    x &= (1 << n) - 1
    if (x >> (n - 1)) & 1:
        return x | (0xFFFFFFFF << n) & 0xFFFFFFFF
    return x


def zext(x, n):
    if n == 0:
        return 0
    if n >= 32:
        return x & 0xFFFFFFFF
    return x & ((1 << n) - 1)


try:
    run("USGXT UR16, UR6, UR8;", 0x0F, 4)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

cases = [
    ("USGXT UR16, UR6, UR8;", 0x0F, 4, sext(0x0F, 4), "clamp.s32 N=4"),
    ("USGXT.U32 UR16, UR6, UR8;", 0x0F, 4, zext(0x0F, 4), "clamp.u32 N=4"),
    ("USGXT UR16, UR6, UR8;", 0x0F, 0, 0, "N=0"),
    ("USGXT.W UR16, UR6, UR8;", 0x0F, 0, 0, "wrap N=0"),
    ("USGXT UR16, UR6, UR8;", 0x0F, 1, sext(0x0F, 1), "N=1"),
    ("USGXT.U32 UR16, UR6, UR8;", 0x0F, 1, zext(0x0F, 1), "N=1 u32"),
    ("USGXT UR16, UR6, UR8;", 0x0F, 31, sext(0x0F, 31), "N=31"),
    ("USGXT UR16, UR6, UR8;", 0x0F, 32, 0x0F, "clamp N=32 -> URa"),
    ("USGXT.W UR16, UR6, UR8;", 0x0F, 32, 0, "wrap N=32 -> 0"),
    ("USGXT UR16, UR6, UR8;", 0x0F, 33, 0x0F, "clamp N=33 -> URa"),
    ("USGXT.W UR16, UR6, UR8;", 0x0F, 33, sext(0x0F, 1), "wrap N=33 -> 1 bit"),
    ("USGXT.W.U32 UR16, UR6, UR8;", 0x0F, 33, zext(0x0F, 1), "wrap.u32 N=33"),
    ("USGXT UR16, UR6, UR8;", 0xFFFFFFFF, 33, 0xFFFFFFFF, "clamp N=33 huge"),
    ("USGXT UR16, UR6, UR8;", 0x80000000, 1, 0, "Ra=80000000 N=1"),
    ("USGXT UR16, UR6, UR8;", 0x8, 4, sext(0x8, 4), "Ra=8 N=4"),
    ("USGXT UR16, UR6, 0x5;", 0x0F, 0, sext(0x0F, 5), "imm N=5"),
]
for inst, a, n, exp, lab in cases:
    v = run(inst, a, n)
    good = v == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:20s} -> 0x{v:08X} (exp 0x{exp:08X})")

print("\n=== USGXT semantic verification: ALL OK ===" if ok else "\n=== USGXT FAILURES ===")
sys.exit(0 if ok else 1)
