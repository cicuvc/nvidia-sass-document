import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule

# ---------------------------------------------------------------------------
# UPLOP3 — uniform predicate three-input logic (udp_pipe; verified SM120)
#
#   UPLOP3.LUT UPu, UPv, [!]UPp, [!]UPq, [!]UPr, uimm8, vimm8   (0x89c)
#   UPLOP3.LUT UPu, [!]UPp, [!]UPq, [!]UPr, uimm8               (1-out ALT)
#
# Silicon semantics (RTX 5090):
#   UPu = uimm8[ (UPr) | (UPq)<<1 | (UPp)<<2 ]
#   UPv = vimm8[ (UPr) | (UPq)<<1 | (UPp)<<2 ]
# i.e. the truth-table index order is (r, q, p) — the same a/c-style swap
# found on ULOP3 (inputs p and r are swapped vs the "standard" p|q<<1|r<<2
# order).  [!] negates the corresponding input bit.
#
# Outputs are uniform predicates; read back via UP2UR's UPR bitmask
# (UP0 -> bit 0, UP1 -> bit 1).  Tests clear all predicates first (they
# persist across launches) and settle the udp path.
# ---------------------------------------------------------------------------

REF = [
    (0x000000000069789c, 0x000fca0001107246),  # UPLOP3.LUT UP0, UP1, UP2, UP3, UP4, 0x96, 0x69
    (0x000000000000789c, 0x000fca0001707246),  # UPLOP3.LUT UP0, UP2, UP3, UP4, 0x96 (1-out)
    (0x000000000069789c, 0x000fca0005107246),  # ... with !UP2 input
]
flat = assemble_flat("""UPLOP3.LUT UP0, UP1, UP2, UP3, UP4, 0x96, 0x69;[7:7:{}:5:1]
UPLOP3.LUT UP0, UP2, UP3, UP4, 0x96;[7:7:{}:5:1]
UPLOP3.LUT UP0, UP1, !UP2, UP3, UP4, 0x96, 0x69;[7:7:{}:5:1]
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


def kernel(p, q, r, uimm, vimm=None, neg_r=False):
    def setp(pn, val):
        return f"    UISETP.{'T' if val else 'F'} UP{pn}, UR6, UR8;[7:7:{{2,3}}:5:1]\n"
    rn = "!" if neg_r else ""
    if vimm is None:
        uplop3 = f"UPLOP3.LUT UP0, UP2, UP3, UP4, 0x{uimm:X};"
    else:
        uplop3 = f"UPLOP3.LUT UP0, UP1, UP2, UP3, {rn}UP4, 0x{uimm:X}, 0x{vimm:X};"
    return f"""#fn t(a<8>, b<8>, out<1024>) {{
    LDCU.64 {{UR4, UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:1:0]
    LDC.64 {{R6, R7}}, #param(out);[1:7:{{}}:1:0]
    LDCU UR6, #param(a);[2:7:{{}}:1:0]
    LDCU UR8, #param(b);[3:7:{{}}:1:0]
    UMOV UR9, UR6;[7:7:{{2}}:5:1]
    UMOV UR9, UR8;[7:7:{{3}}:5:1]
    UISETP.F UP0, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP1, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP2, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP3, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.F UP4, UR6, UR8;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP4;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP3;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP2;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP1;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP0;[7:7:{{2,3}}:5:1]
{setp(2, p)}{setp(3, q)}{setp(4, r)}    UISETP.T.AND UPT, UPT, UR6, UR8, UP4;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP3;[7:7:{{2,3}}:5:1]
    UISETP.T.AND UPT, UPT, UR6, UR8, UP2;[7:7:{{2,3}}:5:1]
    {uplop3}[7:7:{{}}:5:1]
{DUMS}    UP2UR UR16, UPR;[7:7:{{}}:5:1]
    UMOV UR9, UR16;[7:7:{{}}:5:1]
    UMOV UR14, UR16;[7:7:{{}}:5:1]
    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{{}}:8:1]
{FILL}{FILL}    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x0], R2;[7:7:{{0,1}}:1:0]
    EXIT;[7:7:{{}}:5:0]
}}"""


def run(p, q, r, uimm, vimm=None, neg_r=False):
    mod = build(kernel(p, q, r, uimm, vimm, neg_r))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[0, 0, d])
    mod.synchronize()
    v = struct.unpack("<I", mod.device_read(d, 4))[0]
    mod.devmem_free(d)
    return v


def model(p, q, r, lut, neg_r=False):
    if neg_r:
        r = 1 - r
    return (lut >> (r | (q << 1) | (p << 2))) & 1


try:
    run(0, 0, 0, 0x96)
except RuntimeError as e:
    print(f"skip GPU checks (no CUDA driver/GPU): {e}")
    sys.exit(0 if ok else 1)

print()

# 2-output form: UP0 = uimm8[r|q<<1|p<<2] over all 8 input combos x 4 LUTs.
for p in (0, 1):
    for q in (0, 1):
        for r in (0, 1):
            for lut in (0x96, 0x3C, 0xAA, 0x01):
                v = run(p, q, r, lut)
                u = v & 1
                exp = model(p, q, r, lut)
                good = u == exp
                ok &= good
                if not good:
                    print(f"FAIL uimm p={p} q={q} r={r} LUT=0x{lut:02X}: UP0={u} (exp {exp})")
print("ok  UP0 = uimm8[(r)|(q)<<1|(p)<<2] (32 combos)")

# UP1 = vimm8[...].
for p in (0, 1):
    for q in (0, 1):
        for r in (0, 1):
            for lut in (0x3C, 0xAA):
                v = run(p, q, r, 0x00, lut)
                u1 = (v >> 1) & 1
                exp = model(p, q, r, lut)
                good = u1 == exp
                ok &= good
                if not good:
                    print(f"FAIL vimm p={p} q={q} r={r} LUT=0x{lut:02X}: UP1={u1} (exp {exp})")
print("ok  UP1 = vimm8[(r)|(q)<<1|(p)<<2] (16 combos)")

# [!] negation on UPr.
for p, q, r, lut in [(1, 0, 0, 0x3C), (1, 0, 1, 0x3C), (0, 1, 0, 0x96)]:
    v = run(p, q, r, lut, vimm=0x00, neg_r=True)
    u = v & 1
    exp = model(p, q, r, lut, neg_r=True)
    good = u == exp
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} !UPr p={p} q={q} r={r} LUT=0x{lut:02X}: UP0={u} (exp {exp})")

# 1-output ALT form.
v = run(1, 0, 0, 0x3C)   # vimm=None -> 1-output ALT form
u = v & 1
exp = model(1, 0, 0, 0x3C)
good = u == exp
ok &= good
print(f"{'ok ' if good else 'FAIL'} 1-out form p=1,q=0,r=0 LUT=0x3C: UP0={u} (exp {exp})")

print("\n=== UPLOP3 semantic verification: ALL OK ===" if ok else "\n=== UPLOP3 FAILURES ===")
sys.exit(0 if ok else 1)
