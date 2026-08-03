import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UIADD3 — uniform three-input integer add (udp_pipe; verified SM120, RTX 5090)
#
#   UIADD3 URd, UPu, UPv, [-]URa, [-]URb, [-]URc     (0x1290)
#   UIADD3 URd, UPu, UPv, [-]URa, imm32, [-]URc      (0x1890)
#   UIADD3.X ... , [!]UPp, [!]UPq                     (.X carry-chain form)
#
#   URd = URa + URb + URc (mod 2^32); [-] negates the operand.
#   UPu = carry of the FIRST stage (URa+URb >= 2^32);
#   UPv = carry of the SECOND stage ((URa+URb mod 2^32) + URc >= 2^32)
#   (IADD3's two-stage carry convention).  .X adds input carry bits:
#   sum += UPp + UPq (each set/negated predicate contributes its value).
#
# Note: no separate UIADD3.64 variant exists in the sm_90/sm_120 spec
# (the old note's ".64" table is unverified) — 64-bit uniform adds are done
# by chaining 32-bit UIADD3.X with the carry predicates.
# ---------------------------------------------------------------------------

REF = [
    (0x0000000706047290, 0x000fca000fffe008),  # UIADD3 UR4, UPT, UPT, UR6, UR7, UR8
    (0x0000000706047290, 0x000fca000f91e008),  # UIADD3 UR4, UP0, UP1, UR6, UR7, UR8
    (0x0000000706047290, 0x000fca000f91e108),  # ... with -UR6
    (0x1234567806047890, 0x000fca000f91e008),  # imm 0x12345678
    (0x0000000706047290, 0x000fca0009106408),  # UIADD3.X ... UP2, UP3
]
flat = assemble_flat("""UIADD3 UR4, UPT, UPT, UR6, UR7, UR8;[7:7:{}:5:1]
UIADD3 UR4, UP0, UP1, UR6, UR7, UR8;[7:7:{}:5:1]
UIADD3 UR4, UP0, UP1, -UR6, UR7, UR8;[7:7:{}:5:1]
UIADD3 UR4, UP0, UP1, UR6, 0x12345678, UR8;[7:7:{}:5:1]
UIADD3.X UR4, UP0, UP1, UR6, UR7, UR8, UP2, UP3;[7:7:{}:5:1]
""")
ok = True
for i, enc in enumerate(flat):
    good = enc == REF[i]
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} bytes [{i}] lo={enc[0]:016x} hi={enc[1]:016x}")


def build(src):
    return CudaModule(assemble(src, check_deps=False))


FILL = "    IADD3 R10, R10, RZ, RZ;[7:7:{}:5:1]\n"


def kernel(inst, x=False):
    pres = ("    UISETP.F UP0, UR6, UR8;[7:7:{2,4}:5:1]\n"
            "    UISETP.F UP1, UR6, UR8;[7:7:{2,4}:5:1]\n")
    if x:
        pres += ("    UISETP.F UP2, UR6, UR8;[7:7:{2,4}:5:1]\n"
                 "    UISETP.F UP3, UR6, UR8;[7:7:{2,4}:5:1]\n"
                 "    UISETP.T.AND UPT, UPT, UR6, UR8, UP3;[7:7:{2,4}:5:1]\n"
                 "    UISETP.T.AND UPT, UPT, UR6, UR8, UP2;[7:7:{2,4}:5:1]\n")
    pres += ("    UISETP.T.AND UPT, UPT, UR6, UR8, UP1;[7:7:{2,4}:5:1]\n"
             "    UISETP.T.AND UPT, UPT, UR6, UR8, UP0;[7:7:{2,4}:5:1]\n")
    dums = "".join(f"    UMOV UR9, UR17;[7:7:{{}}:5:1]\n" for _ in range(3))
    return f"""#fn t(a<8>, b<8>, c<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    LDCU UR7, #param(b);[3:7:{{}}:1:0]
    LDCU UR8, #param(c);[4:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR7;[7:7:{{3}}:5:1]
    UMOV UR9, UR8;[7:7:{{4}}:5:1]
{pres}    {inst}[7:7:{{2,3,4}}:5:1]
{dums}    UP2UR UR18, UPR;[7:7:{{}}:5:1]
    UP2UR UR16, UPR;[7:7:{{}}:5:1]
    UMOV UR9, UR17;[7:7:{{}}:5:1]
    UMOV UR14, UR17;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R3, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x4], R3;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(inst, a, b, c, x=False):
    mod = build(kernel(inst, x=x))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,),
               args=[a & 0xFFFFFFFF, b & 0xFFFFFFFF, c & 0xFFFFFFFF, d])
    mod.synchronize()
    s, pr = struct.unpack("<2I", mod.device_read(d, 8))
    mod.devmem_free(d)
    return s, pr & 1, (pr >> 1) & 1


try:
    run("UIADD3 UR17, UP0, UP1, UR6, UR7, UR8;", 5, 7, 9)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# Plain: sum + carry bits (UP0 = sum>>32, UP1 = sum>>33).
cases = [
    (5, 7, 9, "5+7+9"),
    (0xFFFFFFFF, 1, 0, "FF+1"),
    (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, "3x FF"),
    (0x7FFFFFFF, 0x7FFFFFFF, 0, "7FFF+7FFF"),
    (0xFFFFFFFF, 0xFFFFFFFF, 0, "2x FF"),
    (0x7FFFFFFF, 1, 0, "7FFF+1"),
    (0x80000000, 0x80000000, 0, "8000+8000"),
    (0x7FFFFFFF, 0x7FFFFFFF, 1, "7FFF+7FFF+1"),
    (0x40000000, 0x40000000, 0x40000000, "3x 4000"),
    (0x80000000, 0xFFFFFFFF, 0xFFFFFFFF, "8000+2x"),
]
for a, b, c, lab in cases:
    s, u, v = run("UIADD3 UR17, UP0, UP1, UR6, UR7, UR8;", a, b, c)
    tot = a + b + c
    s1 = a + b
    exp_u = 1 if s1 > 0xFFFFFFFF else 0
    exp_v = 1 if (s1 & 0xFFFFFFFF) + c > 0xFFFFFFFF else 0
    good = s == (tot & 0xFFFFFFFF) and u == exp_u and v == exp_v
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lab:12s}: sum=0x{s:08X} UP0={u} UP1={v} (exp {exp_u},{exp_v})")

# Negate.
s, u, v = run("UIADD3 UR17, UP0, UP1, -UR6, UR7, UR8;", 10, 3, 0)
good = s == 0xFFFFFFF9
ok &= good
print(f"{'ok ' if good else 'FAIL'} -UR6+UR7: 0x{s:08X} (exp 0xFFFFFFF9)")

# imm.
s, u, v = run("UIADD3 UR17, UP0, UP1, UR6, 0x10000000, UR8;", 0x0FFFFFFF, 0, 1)
good = s == 0x20000000
ok &= good
print(f"{'ok ' if good else 'FAIL'} imm: 0x{s:08X} (exp 0x20000000)")

# .X: sum += UPp + UPq (UP2/UP3 = T by the kernel? No — kernel clears them;
# use negated F to add 1: !UP3 with UP3=F -> +1).
s, u, v = run("UIADD3.X UR17, UP0, UP1, UR6, UR7, UR8, !UP2, !UP3;", 5, 7, 9, x=True)
good = s == 23   # !F + !F = 1 + 1 = +2
ok &= good
print(f"{'ok ' if good else 'FAIL'} .X carry 1+1: {s} (exp 23)")
s, u, v = run("UIADD3.X UR17, UP0, UP1, UR6, UR7, UR8, UP2, UP3;", 5, 7, 9, x=True)
good = s == 21   # F + F = 0
ok &= good
print(f"{'ok ' if good else 'FAIL'} .X carry 0+0: {s} (exp 21)")
s, u, v = run("UIADD3.X UR17, UP0, UP1, UR6, UR7, UR8, UP2, !UP3;", 5, 7, 9, x=True)
good = s == 22
ok &= good
print(f"{'ok ' if good else 'FAIL'} .X carry 1+0: {s} (exp 22)")
s, u, v = run("UIADD3.X UR17, UP0, UP1, UR6, UR7, UR8, !UP2, UP3;", 5, 7, 9, x=True)
good = s == 22
ok &= good
print(f"{'ok ' if good else 'FAIL'} .X carry 0+1: {s} (exp 22)")

print("\n=== UIADD3 semantic verification: ALL OK ===" if ok else "\n=== UIADD3 FAILURES ===")
sys.exit(0 if ok else 1)
