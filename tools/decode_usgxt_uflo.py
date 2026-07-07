#!/usr/bin/env python3
"""USGXT + UFLO decoders (sm_90). No empirical vectors — spec-only."""

def ext(l, h, m, s):
    v = 0
    for b in range(s, m + 1):
        v |= (((h >> (b - 64)) if b >= 64 else (l >> b)) & 1) << (b - s)
    return v
ur = lambda r: "URZ" if r == 63 else f"UR{r}"

UPG = {0:"UP0",1:"UP1",2:"UP2",3:"UP3",4:"UP4",5:"UP5",6:"UP6",7:"UPT"}
CW = {0:"C", 1:"W"}

def decode_usgxt(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ext(lo, hi, 21, 16); ura = ext(lo, hi, 29, 24)
    cw = ext(lo, hi, 75, 75)
    if op == 0x129a:
        urb = ext(lo, hi, 37, 32)
        return f"USGXT.{CW.get(cw,'?')} {ur(urd)}, {ur(ura)}, {ur(urb)}", "noimm"
    elif op == 0x189a:
        imm = ext(lo, hi, 63, 32)
        return f"USGXT.{CW.get(cw,'?')} {ur(urd)}, {ur(ura)}, 0x{imm:x}", "imm"
    return None, f"bad opcode 0x{op:03x}"

def decode_uflo(lo, hi):
    op = ext(lo, hi, 91, 91) << 12 | ext(lo, hi, 11, 0)
    urd = ext(lo, hi, 21, 16)
    sh = ext(lo, hi, 74, 74); inv = ext(lo, hi, 63, 63)
    pu = ext(lo, hi, 83, 81)
    pu_str = "" if pu == 7 else f"{UPG.get(pu,f'UP{pu}')}, "
    if op == 0x12bd:
        urb = ext(lo, hi, 37, 32)
        return f"UFLO{' .SH' if sh else ''} {pu_str}{ur(urd)}, {'[-]' if inv else ''}{ur(urb)}", "noimm"
    elif op == 0x18bd:
        imm = ext(lo, hi, 63, 32)
        return f"UFLO{' .SH' if sh else ''} {pu_str}{ur(urd)}, 0x{imm:x}", "imm"
    return None, f"bad opcode 0x{op:03x}"

if __name__ == "__main__":
    print("USGXT + UFLO decoders — no empirical test vectors.")
    print("Verification deferred.")
