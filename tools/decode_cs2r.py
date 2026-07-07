#!/usr/bin/env python3
"""Decoder for CS2R (Constant/Counter Special-register to Register) on sm_90 — int_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

CS2R is the fixed-latency (COUPLED, int_pipe) counterpart of S2R: used for the clock/
timer counters (SR_CLOCKLO/HI, SR_GLOBALTIMERLO/HI) and the `CS2R Rd, SRZ` zeroing idiom.
64-bit is the default (reads SR:SR+1 into Rd:Rd+1); `.32` reads a single 32-bit SR.
Validated against real cuobjdump captures (sm_90, CUDA 13.1).
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from decode_s2r_s2ur import SR, sr_name          # reuse the SpecialRegister name map

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x805

def reg(n): return "RZ" if n == 0xff else f"R{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    sz  = bits(w, 80, 80)          # QInteger: 0=32, 1=64 (default, hidden)
    SRa = bits(w, 79, 72)
    Rd  = bits(w, 23, 16)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    suf = "" if sz else ".32"
    return f"{g}CS2R{suf} {reg(Rd)}, {sr_name(SRa)} ;"

def encode(Rd=0, SRa=255, sz=1, Pg=7, Pg_not=0):
    w = (bits(OPCODE,12,12)<<91)|bits(OPCODE,11,0)|((Pg&7)<<12)|((Pg_not&1)<<15)
    w |= (Rd&0xff)<<16 | (SRa&0xff)<<72 | (sz&1)<<80
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

REAL = [
    (0x0000000000047805, 0x000fe20000015200, "CS2R R4, SR_GLOBALTIMERLO ;"),  # 64-bit
    (0x0000000000047805, 0x000fe20000015000, "CS2R R4, SR_CLOCKLO ;"),        # clock64()
    (0x0000000000057805, 0x000fe20000005000, "CS2R.32 R5, SR_CLOCKLO ;"),     # clock()
]
SYNTH = [
    (encode(Rd=6, SRa=255, sz=1), "CS2R R6, SRZ ;"),       # 64-bit zeroing idiom (R6:R7 = 0)
    (encode(Rd=6, SRa=255, sz=0), "CS2R.32 R6, SRZ ;"),    # 32-bit zeroing
]

if __name__ == "__main__":
    ok = True
    print("-- real captures --")
    for lo, hi, exp in REAL:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:30s} | exp {exp}")
    print("-- synthetic round-trips --")
    for (lo, hi), exp in SYNTH:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:18s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
