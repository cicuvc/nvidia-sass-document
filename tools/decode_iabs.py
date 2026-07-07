#!/usr/bin/env python3
"""Decoder for IABS (integer absolute value, 32-bit) on sm_90 — int_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
RRR form verified against real cuobjdump capture (sm_90, CUDA 13.1); the imm/const/
uniform operand forms are round-trip only (ptxas emits RRR, loading consts to a reg first).

  IABS Rd, <src>  ->  Rd = |src|  (32-bit signed; no modifiers)
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

FORM = {0x213: "R", 0x813: "I", 0xa13: "C", 0x1a13: "Cx", 0x1c13: "U"}

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def sext(v, n): return v - (1 << n) if (v >> (n - 1)) & 1 else v

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in FORM, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    Rd = bits(w, 23, 16)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    f = FORM[opcode]
    if f == "R":  src = reg(bits(w, 39, 32))
    elif f == "U": src = f"UR{bits(w,37,32)}"
    elif f == "I":
        imm = sext(bits(w, 63, 32), 32)
        src = f"-{-imm & 0xffffffff:#x}" if imm < 0 else f"{imm:#x}"
    else:          # C / Cx const bank
        bank = bits(w, 58, 54); off = bits(w, 53, 40) << 2
        src = f"c[{bank:#x}][{off:#x}]"
    return f"{g}IABS {reg(Rd)}, {src} ;"

def enc(op, Rd=0, Rb=0, URb=0, imm=0, Pg=7):
    w = (bits(op,12,12)<<91)|bits(op,11,0)|((Pg&7)<<12)|((Rd&0xff)<<16)
    if op == 0x213: w |= (Rb&0xff)<<32
    if op == 0x1c13: w |= (URb&0x3f)<<32
    if op == 0x813: w |= (imm & 0xffffffff)<<32
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

REAL = [
    (0x0000000200007213, 0x004fc80000000000, "IABS R0, R2 ;"),
]
SYNTH = [
    (enc(0x213, Rd=5, Rb=7),      "IABS R5, R7 ;"),
    (enc(0x1c13, Rd=5, URb=3),    "IABS R5, UR3 ;"),
    (enc(0x813, Rd=5, imm=0x100), "IABS R5, 0x100 ;"),
]

if __name__ == "__main__":
    ok = True
    print("-- real --")
    for lo, hi, exp in REAL:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:18s} | exp {exp}")
    print("-- synthetic round-trips --")
    for (lo, hi), exp in SYNTH:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:16s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
