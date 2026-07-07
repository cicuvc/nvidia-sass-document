#!/usr/bin/env python3
"""UCLEA decoder — Uniform Clear Effective Address (sm_90). Spec-only."""

def ext(l, h, m, s):
    v = 0
    for b in range(s, m + 1):
        v |= (((h >> (b - 64)) if b >= 64 else (l >> b)) & 1) << (b - s)
    return v
ur = lambda r: "URZ" if r == 63 else f"UR{r}"
UPG = {0:"UP0",1:"UP1",2:"UP2",3:"UP3",4:"UP4",5:"UP5",6:"UP6",7:"UPT"}

def decode_uclea(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ur(ext(lo, hi, 21, 16))
    pu = UPG.get(ext(lo, hi, 83, 81), "?")
    ura = ur(ext(lo, hi, 29, 24))
    sz = ext(lo, hi, 76, 73)
    if op == 0x1cbc:
        urb = ur(ext(lo, hi, 37, 32))
        return f"UCLEA {urd}, {pu}, {ura}, {urb}, {sz}", "urb"
    elif op == 0x18bc:
        imm = ext(lo, hi, 47, 32)
        return f"UCLEA {urd}, {pu}, {ura}, 0x{imm:x}, {sz}", "imm"
    return None, f"bad 0x{op:03x}"

if __name__ == "__main__":
    print("UCLEA decoder — no empirical test vectors. Verification deferred.")
