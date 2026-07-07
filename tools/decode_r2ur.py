#!/usr/bin/env python3
"""Decoder for R2UR (Register -> Uniform Register) on sm_90 — udp_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validated against real cuobjdump captures (sm_90, CUDA 13.1) from libcublasLt.so.
The .OR (cross-lane OR-reduce) form is round-trip only (not captured).
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x2ca

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def ureg(n): return "URZ" if n == 0x3f else f"UR{n}"
def pred(n): return "PT" if n == 7 else f"P{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg   = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    ORb  = bits(w, 84, 84)
    Pu   = bits(w, 83, 81)
    URd  = bits(w, 21, 16)
    Ra   = bits(w, 31, 24)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    if ORb:                                   # OR-reduce across lanes; Pu shown
        return f"{g}R2UR.OR {pred(Pu)}, {ureg(URd)}, {reg(Ra)} ;"
    pu = f"{pred(Pu)}, " if Pu != 7 else ""   # noOR: Pu shown only if not PT
    return f"{g}R2UR {pu}{ureg(URd)}, {reg(Ra)} ;"

def encode(URd=0, Ra=0, Pu=7, ORb=0, Pg=7, Pg_not=0):
    w = (bits(OPCODE,12,12)<<91)|bits(OPCODE,11,0)|((Pg&7)<<12)|((Pg_not&1)<<15)
    w |= (URd&0x3f)<<16 | (Ra&0xff)<<24 | (Pu&7)<<81 | (ORb&1)<<84
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

REAL = [
    (0x00000000040d02ca, 0x008fe400000e0000, "@P0 R2UR UR13, R4 ;"),
    (0x00000000020c02ca, 0x004fd600000e0000, "@P0 R2UR UR12, R2 ;"),
    (0x00000000000e72ca, 0x002fda00000e0000, "R2UR UR14, R0 ;"),
    (0x00000000040902ca, 0x008fc400000e0000, "@P0 R2UR UR9, R4 ;"),
    (0x00000000020802ca, 0x004fd600000e0000, "@P0 R2UR UR8, R2 ;"),
    (0x00000000000772ca, 0x002fda00000e0000, "R2UR UR7, R0 ;"),
]
SYNTH = [
    (encode(URd=5, Ra=6, ORb=1, Pu=0), "R2UR.OR P0, UR5, R6 ;"),
    (encode(URd=5, Ra=6, ORb=1, Pu=7), "R2UR.OR PT, UR5, R6 ;"),
]

if __name__ == "__main__":
    ok = True
    print("-- real captures --")
    for lo, hi, exp in REAL:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:22s} | exp {exp}")
    print("-- synthetic (.OR) round-trips --")
    for (lo, hi), exp in SYNTH:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:22s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
