#!/usr/bin/env python3
"""Decoder for VOTE (warp vote/ballot: __ballot_sync/__any_sync/__all_sync/__uni) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validates against real cuobjdump captures (sm_90, CUDA 13.1).
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x806
VOTEOP = {0: "ALL", 1: "ANY", 2: "EQ", 3: "INVALID3"}

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def pred(n): return "PT" if n == 7 else f"P{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    Rd     = bits(w, 23, 16)
    voteop = bits(w, 73, 72)
    Pu     = bits(w, 83, 81)
    Pp     = bits(w, 89, 87)
    Pp_not = bits(w, 90, 90)
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    ops = []
    if Rd != 0xff:                 # RZ default is omitted
        ops.append(reg(Rd))
    ops.append(pred(Pu))
    ops.append(f"{'!' if Pp_not else ''}{pred(Pp)}")
    return f"{guard}VOTE.{VOTEOP[voteop]} " + ", ".join(ops) + " ;"

# real captured vectors (lo64, hi64, expected)
VEC = [
    (0x0000000000077806, 0x000fca00040e0100, "VOTE.ANY R7, PT, !P0 ;"),   # __ballot_sync(!pred)
    (0x0000000000077806, 0x000fca00000e0100, "VOTE.ANY R7, PT, P0 ;"),    # __ballot_sync(pred)
    (0x0000000000ff7806, 0x000fc80000000100, "VOTE.ANY P0, P0 ;"),        # __any_sync
    (0x0000000000ff7806, 0x000fc80000000000, "VOTE.ALL P0, P0 ;"),        # __all_sync
    (0x0000000000ff7806, 0x000fc80000000200, "VOTE.EQ P0, P0 ;"),         # __uni_sync
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:28s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
