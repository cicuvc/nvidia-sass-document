#!/usr/bin/env python3
"""Decoder for FCHK (FP check — fast-divide safety pre-check) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

Semantics verified on SM120: Pu=1 when the fast Newton-Raphson divide can't
produce a correctly-rounded quotient (NaN/Inf/0/denorm operands, |Ra|<2^-102,
|Rb|<2^-125 or >=2^125, or quotient outside [2^-125, 2^127)).
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

# opcodes: RRR=0x302 RIR=0x902 RCR=0xb02 RCxR=0x1b02 RUR=0x1d02
OPCODES = {0x302: "RRR", 0x902: "RIR", 0xb02: "RCR", 0x1b02: "RCxR", 0x1d02: "RUR"}

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def ureg(n): return "URZ" if n == 0x3f else f"UR{n}"

def fmt_src(variant, ra, rb, urb):
    ra_s = reg(ra)
    if variant in ("RRR", "RIR"):
        rb_s = "RZ" if rb == 0xff else f"R{rb}"
    elif variant == "RUR":
        rb_s = ureg(urb)
    else:
        rb_s = f"c[{rb}][{urb}]"
    return ra_s, rb_s

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    variant = OPCODES.get(opcode)
    assert variant, f"bad opcode {opcode:#x}"
    Pg = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    Pu = bits(w, 83, 81)
    Ra = bits(w, 31, 24)
    Rb = bits(w, 39, 32)
    Ra_abs = bits(w, 73, 73); Ra_neg = bits(w, 72, 72)
    Rb_neg = bits(w, 63, 63); Rb_abs = bits(w, 62, 62)
    ra_s, rb_s = fmt_src(variant, Ra, Rb, 0)
    ra_f = ("|" if Ra_abs else "") + ra_s + ("|" if Ra_abs else "")
    if Ra_neg:
        ra_f = "-" + ra_f
    rb_f = ("|" if Rb_abs else "") + rb_s + ("|" if Rb_abs else "")
    if Rb_neg:
        rb_f = "-" + rb_f
    g = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    pu = "PT" if Pu == 7 else f"P{Pu}"
    return f"{g}FCHK {pu}, {ra_f}, {rb_f} ;"

def encode(Pu=0, Ra=0, Rb=0, Ra_abs=0, Ra_neg=0, Rb_neg=0, Rb_abs=0,
           Pg=7, Pg_not=0, opcode=0x302):
    w = (bits(opcode, 12, 12) << 91) | bits(opcode, 11, 0)
    w |= ((Pg & 7) << 12) | ((Pg_not & 1) << 15)
    w |= ((Pu & 7) << 81) | ((Ra_abs & 1) << 73) | ((Ra_neg & 1) << 72)
    w |= ((Rb_neg & 1) << 63) | ((Rb_abs & 1) << 62)
    w |= ((Ra & 0xff) << 24) | ((Rb & 0xff) << 32)
    return w & ((1 << 64) - 1), (w >> 64) & ((1 << 64) - 1)

CASES = [
    (encode(Pu=0, Ra=6, Rb=7),                "FCHK P0, R6, R7 ;"),
    (encode(Pu=1, Ra=6, Rb=7),                "FCHK P1, R6, R7 ;"),
    (encode(Pu=0, Ra=6, Rb=7, Ra_abs=1),      "FCHK P0, |R6|, R7 ;"),
    (encode(Pu=0, Ra=6, Rb=7, Ra_neg=1),      "FCHK P0, -R6, R7 ;"),
    (encode(Pu=0, Ra=6, Rb=7, Rb_neg=1),      "FCHK P0, R6, -R7 ;"),
    (encode(Pu=0, Ra=6, Rb=7, Rb_abs=1),      "FCHK P0, R6, |R7| ;"),
    (encode(Pu=0, Ra=6, Rb=7, Ra_neg=1, Ra_abs=1), "FCHK P0, -|R6|, R7 ;"),
    (encode(Pu=5, Ra=0, Rb=255, opcode=0x902), "FCHK P5, R0, RZ ;"),
]

ok = True
for (lo, hi), want in CASES:
    got = decode(lo, hi)
    good = got == want
    ok &= good
    print(f"{'ok ' if good else 'FAIL'} {lo:016x} {hi:016x} -> {got}" + ("" if good else f"  want {want}"))
print("ALL OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
