#!/usr/bin/env python3
"""UPRMT decoder — Uniform Byte Permute (sm_90)"""
def ext(l, h, m, s):
    v = 0
    for b in range(s, m + 1):
        v |= (((h >> (b - 64)) if b >= 64 else (l >> b)) & 1) << (b - s)
    return v
ur = lambda r: "URZ" if r == 63 else f"UR{r}"
def decode_uprmt(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ext(lo, hi, 21, 16); ura = ext(lo, hi, 29, 24)
    urc = ext(lo, hi, 69, 64)
    if op == 0x1896:
        imm = ext(lo, hi, 63, 32)
        return f"UPRMT {ur(urd)}, {ur(ura)}, 0x{imm:x}, {ur(urc)}", "imm"
    elif op == 0x1296:
        urb = ext(lo, hi, 37, 32)
        return f"UPRMT {ur(urd)}, {ur(ura)}, {ur(urb)}, {ur(urc)}", "noimm"
    return None, f"bad opcode 0x{op:03x}"

h2 = lambda s: int(s, 16)
T = [
    ("0x0000888004047896", "0x000fe2000800003f", "UPRMT UR4, UR4, 0x8880, URZ"),
    ("0x0000888006047896", "0x000fe2000800003f", "UPRMT UR4, UR6, 0x8880, URZ"),
]
def main():
    for l, h, w in T:
        r = decode_uprmt(h2(l), h2(h))
        print(f"{'OK' if r[0]==w else 'FAIL'}: {r[0]}" + (f" (want {w})" if r[0]!=w else ""))
main()
