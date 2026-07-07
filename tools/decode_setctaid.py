#!/usr/bin/env python3
"""Decoder for SETCTAID on sm_90.

NOTE: not emitted by nvcc/ptxas from user code (driver/ABI setup op, VQ_ADU,
grouped with SETLMEMBASE/AL2P). No real captured vectors were found in the
available libraries. Field layout is from the CLASS ENCODING in
sm_90_instructions.txt; validation is a round-trip (encode documented fields ->
decode), NOT a match against silicon/cuobjdump text.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x31f
DIM = {0: "X", 1: "Y", 2: "Z", 3: "ALL"}

def reg(n):
    return "RZ" if n == 0xff else f"R{n}"

def encode(Ra=0, dim=3, Pg=7, Pg_not=0, dst_wr_sb=7):
    w = 0
    w |= (bits(OPCODE, 12, 12) << 91) | (bits(OPCODE, 11, 0) << 0)
    w |= (Pg & 7) << 12
    w |= (Pg_not & 1) << 15
    w |= (Ra & 0xff) << 24
    w |= (dim & 3) << 78
    w |= (dst_wr_sb & 7) << 110      # VarLatOperandEnc identity for 0x7
    return w & ((1 << 64) - 1), (w >> 64) & ((1 << 64) - 1)

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    Ra     = bits(w, 31, 24)
    dim    = bits(w, 79, 78)
    pred = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    suffix = "" if dim == 3 else f".{DIM[dim]}"   # ALL is the default (assumed hidden)
    return f"{pred}SETCTAID{suffix} {reg(Ra)} ;"

# round-trip self-tests (SYNTHETIC — not silicon-verified)
CASES = [
    (dict(Ra=2, dim=3),  "SETCTAID R2 ;"),        # ALL -> 64-bit pair R2:R3
    (dict(Ra=4, dim=0),  "SETCTAID.X R4 ;"),
    (dict(Ra=5, dim=1),  "SETCTAID.Y R5 ;"),
    (dict(Ra=6, dim=2),  "SETCTAID.Z R6 ;"),
    (dict(Ra=0xff, dim=3), "SETCTAID RZ ;"),
    (dict(Ra=8, dim=0, Pg=0, Pg_not=1), "@!P0 SETCTAID.X R8 ;"),
]

if __name__ == "__main__":
    ok = True
    for kw, exp in CASES:
        lo, hi = encode(**kw)
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:26s} | exp {exp}")
    print("ROUND-TRIP OK (synthetic)" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
