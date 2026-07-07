#!/usr/bin/env python3
"""Decoder for CLMAD (carry-less / GF(2) multiply-add) on sm_90.

NOTE: not emittable with CUDA 13.1 (PTX `clmad` needs PTX ISA 9.3; this ptxas caps
at 9.1). Semantics are authoritative from the PTX ISA doc; the encoding is from the
CLASS ENCODING in sm_90_instructions.txt. Validation is a round-trip for the RRR
form (encode documented fields -> decode), NOT a match against silicon.

Semantics (PTX clmad.mode.u64 d,a,b,c):
  tmp[127:0] = carryless_mul(a, b)          # GF(2)[x]: tmp ^= b<<i for each set bit i of a
  d = (mode==.lo ? tmp[63:0] : tmp[127:64]) ^ c
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

# opcode -> operand form (which of B/C is reg/const/uniform)
FORM = {
    0x22c:  "RRR",   # Ra=R, Rb=R,  Rc=R
    0xa2c:  "RCR",   # Rb = const bank
    0x1a2c: "RCxR",  # Rb = const bank (extended addr)
    0x62c:  "RRC",   # Rc = const bank
    0x162c: "RRCx",  # Rc = const bank (extended addr)
    0x1c2c: "RUR",   # Rb = uniform reg
    0x1e2c: "RRU",   # Rc = uniform reg
}
HILO = {0: "LO", 1: "HI"}

def reg(n):  return "RZ" if n == 0xff else f"R{n}"

def clmul(a, b):
    t = 0
    for i in range(64):
        if (a >> i) & 1:
            t ^= b << i
    return t & ((1 << 128) - 1)

def clmad(a, b, c, hi):
    t = clmul(a, b)
    half = (t >> 64) if hi else (t & ((1 << 64) - 1))
    return half ^ c

def encode_rrr(Rd=0, Ra=0, Rb=0, Rc=0, hilo=0, Pg=7, Pg_not=0):
    op = 0x22c
    w = (bits(op,12,12)<<91)|bits(op,11,0)|((Pg&7)<<12)|((Pg_not&1)<<15)
    w |= (Rd&0xff)<<16 | (Ra&0xff)<<24 | (Rb&0xff)<<32 | (Rc&0xff)<<64 | (hilo&1)<<77
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in FORM, f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    hilo   = bits(w, 77, 77)
    Rd     = bits(w, 23, 16); Ra = bits(w, 31, 24)
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    form = FORM[opcode]
    if form == "RRR":
        Rb = bits(w, 39, 32); Rc = bits(w, 71, 64)
        return f"{guard}CLMAD.{HILO[hilo]} {reg(Rd)}, {reg(Ra)}, {reg(Rb)}, {reg(Rc)} ;"
    if form in ("RUR",):        # Rb uniform, Rc reg
        URb = bits(w, 37, 32); Rc = bits(w, 71, 64)
        return f"{guard}CLMAD.{HILO[hilo]} {reg(Rd)}, {reg(Ra)}, UR{URb}, {reg(Rc)} ;"
    if form in ("RRU",):        # Rc uniform, Rb reg (Rb held in [71:64], URc in [37:32])
        Rb = bits(w, 71, 64); URc = bits(w, 37, 32)
        return f"{guard}CLMAD.{HILO[hilo]} {reg(Rd)}, {reg(Ra)}, {reg(Rb)}, UR{URc} ;"
    # const-bank forms (RCR/RCxR: Rb const; RRC/RRCx: Rc const)
    bank = bits(w, 58, 54); off = bits(w, 53, 40) << 2
    Rc = bits(w, 71, 64)
    if form in ("RCR", "RCxR"):
        return f"{guard}CLMAD.{HILO[hilo]} {reg(Rd)}, {reg(Ra)}, c[{bank:#x}][{off:#x}], {reg(Rc)} ;"
    Rb = bits(w, 71, 64)
    return f"{guard}CLMAD.{HILO[hilo]} {reg(Rd)}, {reg(Ra)}, {reg(Rb)}, c[{bank:#x}][{off:#x}] ;"

CASES = [
    (encode_rrr(Rd=2, Ra=4, Rb=6, Rc=8, hilo=0), "CLMAD.LO R2, R4, R6, R8 ;"),
    (encode_rrr(Rd=2, Ra=4, Rb=6, Rc=8, hilo=1), "CLMAD.HI R2, R4, R6, R8 ;"),
    (encode_rrr(Rd=10, Ra=0xff, Rb=2, Rc=0xff, hilo=0), "CLMAD.LO R10, RZ, R2, RZ ;"),
]

if __name__ == "__main__":
    # semantics sanity: (x)*(x)=x^2 in GF(2); a=2(x), b=2(x) -> clmul=4(x^2); lo=4, ^c
    assert clmad(0b10, 0b10, 0, 0) == 0b100
    assert clmad(0xffffffffffffffff, 1, 0, 0) == 0xffffffffffffffff
    print(f"semantics: clmul(0b11,0b11)={clmul(0b11,0b11):#x} (x+1)^2 = x^2+1 = 0b101")
    ok = True
    for (lo, hi), exp in CASES:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:30s} | exp {exp}")
    print("ROUND-TRIP OK (synthetic)" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
