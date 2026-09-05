#!/usr/bin/env python3
"""Decoder for USETMAXREG (SETMAXREG) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Reconstructs the cuobjdump SASS text and validates against captured vectors.
"""
import sys

def bits(word128, hi, lo):
    return (word128 >> lo) & ((1 << (hi - lo + 1)) - 1)

MODE = {1: "DEALLOC", 2: "TRY_ALLOC"}   # ALLOC also encodes as 2 (indistinguishable)
POOL = {1: "CTAPOOL"}

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in (0x19c8, 0x13c8), f"unexpected opcode {opcode:#x}"
    Pg      = bits(w, 14, 12)
    Pg_not  = bits(w, 15, 15)
    Sb      = bits(w, 41, 32)      # imm register count
    URb     = bits(w, 37, 32)      # UR register count
    num     = bits(w, 73, 72)      # mode
    sh      = bits(w, 74, 74)      # pool
    Pu      = bits(w, 83, 81)      # dest uniform predicate (alloc only)

    mode = MODE[num]
    pool = POOL[sh]

    # predicate guard prefix
    pred = ""
    if not (Pg == 7 and Pg_not == 0):
        pg = "UPT" if Pg == 7 else f"UP{Pg}"
        pred = f"@{'!' if Pg_not else ''}{pg} "

    s = f"{pred}USETMAXREG.{mode}.{pool} "
    if num == 2:                   # alloc/try_alloc has a dest predicate
        upu = "UPT" if Pu == 7 else f"UP{Pu}"
        s += f"{upu}, "
    s += f"{Sb:#x}" if opcode == 0x19c8 else ("URZ" if URb == 63 else f"UR{URb}")
    return s + " ;"

# (lo64, hi64, expected)
VEC = [
    (0x00000080000079c8, 0x000e0000080e0500, "USETMAXREG.DEALLOC.CTAPOOL 0x80 ;"),
    (0x00000060000079c8, 0x000e0000080e0500, "USETMAXREG.DEALLOC.CTAPOOL 0x60 ;"),
    (0x00000040000079c8, 0x000e0000080e0500, "USETMAXREG.DEALLOC.CTAPOOL 0x40 ;"),
    (0x00000018000079c8, 0x000e0000080e0500, "USETMAXREG.DEALLOC.CTAPOOL 0x18 ;"),
    (0x000000f0000079c8, 0x000e240008000600, "USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0xf0 ;"),
    (0x000000c0000079c8, 0x000e240008000600, "USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0xc0 ;"),
    (0x00000080000079c8, 0x000e240008000600, "USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x80 ;"),
    (0x00000040000079c8, 0x000e240008000600, "USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x40 ;"),
    (0x00000008000073c8, 0x000e8a0008020600, "USETMAXREG.TRY_ALLOC.CTAPOOL UP1, UR8 ;"),
    (0x0000000a000073c8, 0x000e8a00080e0500, "USETMAXREG.DEALLOC.CTAPOOL UR10 ;"),
    (0x000000810000f9c8, 0x000e8a0008040600,
     "@!UPT USETMAXREG.TRY_ALLOC.CTAPOOL UP2, 0x81 ;"),
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp:
            ok = False
        print(f"{m}{got:45s} | exp: {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
