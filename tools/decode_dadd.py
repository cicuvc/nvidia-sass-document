#!/usr/bin/env python3
"""Decoder for DADD (FP64 add) on sm_90 — fma64lite_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validated against real cuobjdump captures (sm_90, CUDA 13.1).

  DADD[.rnd] Rd, [-][|]Ra[|], [-][|]Rc[|]   ; Rd = (+/-|Ra|) + (+/-|Rc|), full FP64 (no FTZ)
Operands are 64-bit register pairs. The 2nd source can be reg/imm(double)/const/uniform.
"""
import sys, struct

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

FORM = {0x229: "R", 0x429: "I", 0x629: "C", 0x1629: "Cx", 0x1e29: "U"}
ROUND = {0: "", 1: ".RM", 2: ".RP", 3: ".RZ"}      # Round1; RN(0) hidden

def reg(n): return "RZ" if n == 0xff else f"R{n}"

def fp64_imm(hi32):                                  # imm is the high 32 bits of the double
    d = struct.unpack('>d', struct.pack('>Q', hi32 << 32))[0]
    return repr(d) if d != int(d) or abs(d) >= 1e16 else f"{d:g}"

def negabs(neg, ab, s):
    if ab: s = f"|{s}|"
    if neg: s = f"-{s}"
    return s

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in FORM, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    rnd = bits(w, 79, 78)
    ra_neg = bits(w, 72, 72); ra_abs = bits(w, 73, 73)
    rc_neg = bits(w, 75, 75); rc_abs = bits(w, 74, 74)
    Rd = bits(w, 23, 16); Ra = bits(w, 31, 24)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    a = negabs(ra_neg, ra_abs, reg(Ra))
    f = FORM[opcode]
    if f == "R":  c = reg(bits(w, 71, 64))
    elif f == "U": c = f"UR{bits(w,37,32)}"
    elif f == "I": c = fp64_imm(bits(w, 63, 32))
    else:
        bank = bits(w, 58, 54); off = bits(w, 53, 40) << 2
        c = f"c[{bank:#x}][{off:#x}]"
    c = negabs(rc_neg, rc_abs, c)
    return f"{g}DADD{ROUND[rnd]} {reg(Rd)}, {a}, {c} ;"

VEC = [
    (0x0000000002067229, 0x008fce0000000004, "DADD R6, R2, R4 ;"),
    (0x0000000002067229, 0x008fce0000004004, "DADD.RM R6, R2, R4 ;"),
    (0x0000000002067229, 0x008fce0000008004, "DADD.RP R6, R2, R4 ;"),
    (0x0000000002067229, 0x008fce000000c004, "DADD.RZ R6, R2, R4 ;"),
    (0x0000000002067229, 0x008fce0000000204, "DADD R6, |R2|, R4 ;"),
    (0x0000000002067229, 0x008fce0000000804, "DADD R6, R2, -R4 ;"),
    (0x0000000602047e29, 0x004fce0008000000, "DADD R4, R2, UR6 ;"),
    (0x4004000002047429, 0x004fce0000000000, "DADD R4, R2, 2.5 ;"),
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:26s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
