import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# USHF — uniform funnel shift (udp_pipe; verified SM120, RTX 5090)
#
#   USHF[.L|.R][.C|.W][.LO|.HI][.U32|.S32|.U64|.S64] URd, URa, URb|imm, URc
#   Funnel = {URc high, URa low} (same as SHF).
#
# SILICON QUIRK vs SHF (verified): the "outer" result words drop the
# cross-word funnel bits:
#   L.HI = (URc << n) | (URa >> (32-n))     full funnel high word
#   L.LO = URa << n                          URc's bits NOT shifted in!
#   R.HI = URc >> n                          URa's bits NOT shifted in!
#   R.LO = (URa >> n) | (URc << (32-n))      full funnel low word
# (Regular SHF includes the cross-word bits in all four; USHF does not.)
#   .C (clamp): n = min(k, 32); .W: n = k & 31; .S32 arithmetic sign-fill.
# ---------------------------------------------------------------------------

REF = [
    (0x0000000706047299, 0x000fca0008000608),  # USHF.L.U32 (LO default)
    (0x0000000706047299, 0x000fca0008010608),  # USHF.L.HI.U32
    (0x0000000706047299, 0x000fca0008001408),  # USHF.R.S32
    (0x0000000706047299, 0x000fca0008000e08),  # USHF.L.W.U32
    (0x0000000506047899, 0x000fca0008001608),  # USHF.R.U32 imm shift
]
flat = assemble_flat("""USHF.L.U32 UR4, UR6, UR7, UR8;[7:7:{}:5:1]
USHF.L.HI.U32 UR4, UR6, UR7, UR8;[7:7:{}:5:1]
USHF.R.S32 UR4, UR6, UR7, UR8;[7:7:{}:5:1]
USHF.L.W.U32 UR4, UR6, UR7, UR8;[7:7:{}:5:1]
USHF.R.U32 UR4, UR6, 0x5, UR8;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(inst, imm=False):
    if imm:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR8, #param(c);[4:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR8;[7:7:{4}:5:1]\n")
        reqs = "{2,4}"
    else:
        loads = ("    LDCU UR6, #param(a);[2:7:{}:1:0]\n"
                 "    LDCU UR7, #param(b);[3:7:{}:1:0]\n"
                 "    LDCU UR8, #param(c);[4:7:{}:1:0]\n"
                 "    UMOV UR9, UR6;[7:7:{2}:5:1]\n"
                 "    UMOV UR9, UR7;[7:7:{3}:5:1]\n"
                 "    UMOV UR9, UR8;[7:7:{4}:5:1]\n")
        reqs = "{2,3,4}"
    return f"""#fn t(a<8>, b<8>, c<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
{loads}    {inst}[7:7:{reqs}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a, k, c, imm=False):
    mod = build(kernel(inst, imm=imm))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,),
               args=[a & 0xFFFFFFFF, k & 0xFFFFFFFF, c & 0xFFFFFFFF, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


def ushf(a, c, d, hilo, k, cw="C", fmt="U32"):
    n = min(k, 32) if cw == "C" else (k & 31)
    if d == "L":
        if hilo == "HI":
            return ((c << n) | (a >> (32 - n))) & 0xFFFFFFFF if n < 32 else 0
        return (a << n) & 0xFFFFFFFF
    if hilo == "HI":
        return (c >> n) & 0xFFFFFFFF
    r = ((a >> n) | (c << (32 - n))) & 0xFFFFFFFF if n < 32 else c
    if fmt == "S32" and n and n < 32 and (a >> (n - 1)) & 1:
        # arithmetic sign-fill in the low word
        r |= (0xFFFFFFFF << (32 - n)) & 0xFFFFFFFF
    if fmt == "S32" and n == 32:
        r = 0xFFFFFFFF if (a >> 31) & 1 else 0
    return r


try:
    run("USHF.L.U32 UR16, UR6, UR7, UR8;", 0x12345678, 4, 0x9ABCDEF0)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

A, C = 0x12345678, 0x9ABCDEF0
for n in (0, 1, 4, 8, 31):
    for inst, d, hilo in [
        ("USHF.L.HI.U32 UR16, UR6, UR7, UR8;", "L", "HI"),
        ("USHF.L.U32 UR16, UR6, UR7, UR8;", "L", "LO"),
        ("USHF.R.HI.U32 UR16, UR6, UR7, UR8;", "R", "HI"),
        ("USHF.R.U32 UR16, UR6, UR7, UR8;", "R", "LO"),
    ]:
        v = run(inst, A, n, C)
        exp = ushf(A, C, d, hilo, n)
        good = v == exp
        ok &= good
        if not good:
            print(f"FAIL {d}.{hilo} n={n}: 0x{v:08X} (model 0x{exp:08X})")
print("ok  C-mode 4-combo battery (L/R x HI/LO, n=0/1/4/8/31)")

# Discriminator: cross-word bits dropped in L.LO / R.HI.
for c in (0xFFFFFFFF, 0x00000000, 0x80000000):
    v = run("USHF.L.U32 UR16, UR6, UR7, UR8;", 1, 4, c)
    good = v == 0x10
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} L.LO A=1 n=4 C=0x{c:08X} -> 0x{v:08X} (exp 0x10)")
for a in (0xFFFFFFFF, 0x80000000, 0x12345678):
    v = run("USHF.R.HI.U32 UR16, UR6, UR7, UR8;", a, 1, 0x00000001)
    good = v == 0
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} R.HI A=0x{a:08X} n=1 C=1 -> 0x{v:08X} (exp 0)")

# .W wrap and S32 arithmetic.
v = run("USHF.L.W.U32 UR16, UR6, UR7, UR8;", A, 33, C)
exp = ushf(A, C, "L", "LO", 33, cw="W")
good = v == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} L.W n=33 (wrap->1): 0x{v:08X} (exp 0x{exp:08X})")
v = run("USHF.R.S32 UR16, UR6, UR7, UR8;", 0x80000000, 8, C)
exp = ushf(0x80000000, C, "R", "LO", 8, fmt="S32")
good = v == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} R.S32 arith n=8: 0x{v:08X} (exp 0x{exp:08X})")

# imm shift form.
v = run("USHF.R.U32 UR16, UR6, 0x5, UR8;", A, 5, C, imm=True)
exp = ushf(A, C, "R", "LO", 5)
good = v == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} R imm shift 5: 0x{v:08X} (exp 0x{exp:08X})")

print("\n=== USHF semantic verification: ALL OK ===" if ok else "\n=== USHF FAILURES ===")
sys.exit(0 if ok else 1)
