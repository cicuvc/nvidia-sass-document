#!/usr/bin/env python3
"""UBREV + UBMSK decoders (sm_90). No empirical vectors — spec-only."""

def ext(l, h, m, s):
    v = 0
    for b in range(s, m + 1):
        v |= (((h >> (b - 64)) if b >= 64 else (l >> b)) & 1) << (b - s)
    return v
ur = lambda r: "URZ" if r == 63 else f"UR{r}"
CW = {0: "C", 1: "W"}

def decode_ubrev(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ur(ext(lo, hi, 21, 16))
    if op == 0x12be:
        return f"UBREV {urd}, {ur(ext(lo, hi, 37, 32))}", "noimm"
    elif op == 0x18be:
        return f"UBREV {urd}, 0x{ext(lo, hi, 63, 32):x}", "imm"
    return None, f"bad 0x{op:03x}"

def decode_ubmsk(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ur(ext(lo, hi, 21, 16)); ura = ur(ext(lo, hi, 29, 24))
    cw = ext(lo, hi, 75, 75)
    if op == 0x129b:
        return f"UBMSK.{CW.get(cw,'?')} {urd}, {ura}, {ur(ext(lo, hi, 37, 32))}", "noimm"
    elif op == 0x189b:
        return f"UBMSK.{CW.get(cw,'?')} {urd}, {ura}, 0x{ext(lo, hi, 63, 32):x}", "imm"
    return None, f"bad 0x{op:03x}"

if __name__ == "__main__":
    print("UBREV + UBMSK decoders — no empirical test vectors.")
    print("Verification deferred.")
