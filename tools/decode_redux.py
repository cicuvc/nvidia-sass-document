#!/usr/bin/env python3
"""Decoder for REDUX (warp-wide reduction to uniform register) on sm_90 — udp_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validated against real cuobjdump captures (sm_90, CUDA 13.1) from __reduce_*_sync.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x3c4
OP = {0: "", 1: ".OR", 2: ".XOR", 3: ".SUM", 4: ".MIN", 5: ".MAX"}  # AND(0) hidden default
SZ = {0: "", 1: ".S32"}                                              # U32(0) hidden

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def ureg(n): return "URZ" if n == 0x3f else f"UR{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    op = bits(w, 80, 78)
    sz = bits(w, 73, 73)
    URd = bits(w, 21, 16); Ra = bits(w, 31, 24)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    return f"{g}REDUX{OP[op]}{SZ[sz]} {ureg(URd)}, {reg(Ra)} ;"

VEC = [
    (0x00000000020673c4, 0x004e240000000000, "REDUX UR6, R2 ;"),          # AND (default)
    (0x00000000020673c4, 0x004e240000004000, "REDUX.OR UR6, R2 ;"),
    (0x00000000020673c4, 0x004e240000008000, "REDUX.XOR UR6, R2 ;"),
    (0x00000000020673c4, 0x004e24000000c000, "REDUX.SUM UR6, R2 ;"),
    (0x00000000020673c4, 0x004e240000010000, "REDUX.MIN UR6, R2 ;"),
    (0x00000000020673c4, 0x004e240000014000, "REDUX.MAX UR6, R2 ;"),
    (0x00000000020673c4, 0x004e240000010200, "REDUX.MIN.S32 UR6, R2 ;"),
    (0x00000000020673c4, 0x004e240000014200, "REDUX.MAX.S32 UR6, R2 ;"),
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:26s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
