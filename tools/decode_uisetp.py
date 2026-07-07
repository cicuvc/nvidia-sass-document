#!/usr/bin/env python3
"""UISETP decoder — Uniform Integer Set-Predicate (sm_90). Spec-only, no empirical vectors."""

def ext(l, h, m, s):
    v = 0
    for b in range(s, m + 1):
        v |= (((h >> (b - 64)) if b >= 64 else (l >> b)) & 1) << (b - s)
    return v
ur = lambda r: "URZ" if r == 63 else f"UR{r}"
UPG = {0:"UP0",1:"UP1",2:"UP2",3:"UP3",4:"UP4",5:"UP5",6:"UP6",7:"UPT"}
ICMP = {0:"F",1:"LT",2:"EQ",3:"LE",4:"GT",5:"NE",6:"GE",7:"T"}
BOP = {0:"AND",1:"OR",2:"XOR",3:"INVALID"}

def decode_uisetp(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    icmp = ext(lo, hi, 78, 76); bop = ext(lo, hi, 75, 74)
    pu = ext(lo, hi, 83, 81); cop = ext(lo, hi, 86, 84)
    pnz = ext(lo, hi, 89, 87); nz = ext(lo, hi, 90, 90)
    is_simple = (bop == 0 and cop == 7 and pnz == 7 and nz == 0)
    if op in (0x128c, 0x188c):
        ura = ur(ext(lo, hi, 29, 24))
        if op == 0x128c:
            rb = ur(ext(lo, hi, 37, 32))
        else:
            imm = ext(lo, hi, 63, 32)
            rb = f"0x{imm:x}" if imm < 0x80000000 else f"-0x{-imm:08x}" if imm & 0x80000000 else f"0x{imm:x}"
        cmp = ICMP.get(icmp, str(icmp))
        if is_simple:
            return f"UISETP.{cmp} {UPG.get(pu, f'UP{pu}')}, {ura}, {rb}", "simple"
        else:
            bo = BOP.get(bop, str(bop))
            upv = UPG.get(cop, f'UP{cop}')
            upp = f"{'!' if nz else ''}{UPG.get(pnz, f'UP{pnz}')}"
            return f"UISETP.{cmp}.{bo} {UPG.get(pu, f'UP{pu}')}, {upv}, {ura}, {rb}, {upp}", "full"
    return None, f"bad 0x{op:03x}"

if __name__ == "__main__":
    print("UISETP decoder — no empirical test vectors. Verification deferred.")
