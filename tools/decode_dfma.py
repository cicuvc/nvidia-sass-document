#!/usr/bin/env python3
"""Decoder for DFMA (FP64 fused multiply-add) on sm_90 — fma64lite_pipe.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validated against real cuobjdump captures (sm_90, CUDA 13.1).

CONFIRMS the CLASS spec: rnd is at [79:78] (in Hi64), negate/abs at [75:72].
(An earlier note wrongly claimed a rounding-encoding "mismatch" — that was an
artifact of recording only Lo64, where the rounding bits do not live.)

  DFMA[.rnd] Rd, [-][|]Ra[|], [-][|]Rb[|], [-][|]Rc[|]  ; Rd = Ra*Rb + Rc (FP64)
"""
import sys, struct

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

FORM = {0x22b: "R", 0x42b: "I", 0x62b: "C", 0x82b: "aI", 0xa2b: "aC",
        0x162b: "Cx", 0x1a2b: "aCx", 0x1c2b: "U", 0x1e2b: "Uc"}
ROUND = {0: "", 1: ".RM", 2: ".RP", 3: ".RZ"}

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def na(neg, ab, s): return ("-" if neg else "") + (f"|{s}|" if ab else s)

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in FORM, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    rnd = bits(w, 79, 78)                       # <-- spec position, in Hi64
    ra_neg = bits(w, 72, 72); ra_abs = bits(w, 73, 73)
    rc_neg = bits(w, 75, 75); rc_abs = bits(w, 74, 74)
    Rd = bits(w, 23, 16); Ra = bits(w, 31, 24); Rc = bits(w, 71, 64)
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    a = na(ra_neg, ra_abs, reg(Ra))
    f = FORM[opcode]
    if f in ("R",):     b = reg(bits(w, 39, 32))          # RRR: Rb at [39:32]
    elif f in ("U",):   b = f"UR{bits(w,37,32)}"          # RUR: URb at [37:32]
    else:               b = "<b>"                         # other forms not exercised here
    c = na(rc_neg, rc_abs, reg(Rc))
    return f"{g}DFMA{ROUND[rnd]} {reg(Rd)}, {a}, {b}, {c} ;"

# real captures (RRR) — tests/dfma_test.cu
VEC = [
    (0x000000040208722b, 0x008fce0000000006, "DFMA R8, R2, R4, R6 ;"),
    (0x000000040208722b, 0x008fce0000004006, "DFMA.RM R8, R2, R4, R6 ;"),
    (0x000000040208722b, 0x008fce0000008006, "DFMA.RP R8, R2, R4, R6 ;"),
    (0x000000040208722b, 0x008fce000000c006, "DFMA.RZ R8, R2, R4, R6 ;"),
    (0x000000040208722b, 0x008fce0000000906, "DFMA R8, -R2, R4, -R6 ;"),
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:30s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
