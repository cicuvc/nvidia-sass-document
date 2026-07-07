#!/usr/bin/env python3
"""Decoder for MATCH (warp match: __match_any_sync / __match_all_sync) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validates against real cuobjdump captures (sm_90, CUDA 13.1).
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x3a1
OP  = {0: "ALL", 1: "ANY"}
SZ  = {0: "", 1: ".U64"}          # U32 is default (hidden)

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def pred(n): return "PT" if n == 7 else f"P{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    Rd     = bits(w, 23, 16)
    Ra     = bits(w, 31, 24)
    sz     = bits(w, 73, 73)
    op     = bits(w, 79, 79)
    Pu     = bits(w, 83, 81)
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    s = f"{guard}MATCH.{OP[op]}{SZ[sz]} "
    if op == 0:                        # ALL has a dest predicate
        s += f"{pred(Pu)}, "
    s += f"{reg(Rd)}, {reg(Ra)}"
    return s + " ;"

# real captured vectors (lo64, hi64, expected)
VEC = [
    (0x00000000020773a1, 0x002e2800000e8000, "MATCH.ANY R7, R2 ;"),
    (0x00000000020773a1, 0x004e2800000e8200, "MATCH.ANY.U64 R7, R2 ;"),
    (0x00000000020773a1, 0x004e240000000000, "MATCH.ALL P0, R7, R2 ;"),
    (0x00000000020773a1, 0x004e240000000200, "MATCH.ALL.U64 P0, R7, R2 ;"),
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:32s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
