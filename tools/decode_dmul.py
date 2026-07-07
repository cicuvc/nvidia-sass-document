#!/usr/bin/env python3
"""Decoder for DMUL (FP64 multiply) on sm_90 — fma64lite_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validated against real cuobjdump captures (sm_90, CUDA 13.1).

CONFIRMS the CLASS spec: rnd is a simple 2-bit field at [79:78] (in Hi64).
(An earlier note wrongly claimed rounding was "managed via opex/scoreboard rather
than a simple 2-bit field" — that was a Lo64-only measurement artifact; the rounding
bits live in Hi64.)

  DMUL[.rnd] Rd, [-][|]Ra[|], [-][|]Rb[|]   ; Rd = Ra * Rb (FP64)
"""
import sys, struct

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

FORM = {0x228: "R", 0x828: "I", 0xa28: "C", 0x1a28: "Cx", 0x1c28: "U"}
ROUND = {0: "", 1: ".RM", 2: ".RP", 3: ".RZ"}

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def na(neg, ab, s): return ("-" if neg else "") + (f"|{s}|" if ab else s)

def fp64_imm(hi32):
    d = struct.unpack('>d', struct.pack('>Q', hi32 << 32))[0]
    return f"{d:g}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in FORM, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    rnd = bits(w, 79, 78)                       # <-- spec position, in Hi64
    ra_neg = bits(w, 72, 72); ra_abs = bits(w, 73, 73)
    rb_neg = bits(w, 63, 63); rb_abs = bits(w, 62, 62)
    Rd = bits(w, 23, 16); Ra = bits(w, 31, 24)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    a = na(ra_neg, ra_abs, reg(Ra))
    f = FORM[opcode]
    if f == "R":   b = na(rb_neg, rb_abs, reg(bits(w, 39, 32)))
    elif f == "U": b = f"UR{bits(w,37,32)}"
    elif f == "I": b = fp64_imm(bits(w, 63, 32))
    else:
        bank = bits(w, 58, 54); off = bits(w, 53, 40) << 2
        b = f"c[{bank:#x}][{off:#x}]"
    return f"{g}DMUL{ROUND[rnd]} {reg(Rd)}, {a}, {b} ;"

VEC = [
    (0x0000000402067228, 0x008fce0000000000, "DMUL R6, R2, R4 ;"),
    (0x0000000402067228, 0x008fce0000004000, "DMUL.RM R6, R2, R4 ;"),
    (0x0000000402067228, 0x008fce0000008000, "DMUL.RP R6, R2, R4 ;"),
    (0x0000000402067228, 0x008fce000000c000, "DMUL.RZ R6, R2, R4 ;"),
    (0x4004000002047828, 0x004fce0000000000, "DMUL R4, R2, 2.5 ;"),
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:24s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
