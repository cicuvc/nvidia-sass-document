#!/usr/bin/env python3
"""Decoder for P2R / R2P (predicate file <-> GPR pack/unpack) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

RIR (immediate-mask) forms are verified against real cuobjdump captures (sm_90,
CUDA 13.1). RRR (register-mask) forms are round-trip only.

  P2R.Bsel Rd, PR, Ra, mask : byte[Bsel] of Rd = (predicate_file & mask); other bytes from Ra
  R2P.Bsel PR, Ra, mask     : predicate_file = unpack(byte[Bsel] of Ra) under mask
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

BSEL = {0: "B0", 1: "B1", 2: "B2", 3: "B3"}
# opcode -> (op, mask_form)
P2R = {0x203: "R", 0xa03: "C", 0x1a03: "Cx", 0x1c03: "U", 0x803: "I"}
R2P = {0x204: "R", 0xa04: "C", 0x1a04: "Cx", 0x1c04: "U", 0x804: "I"}

def reg(n): return "RZ" if n == 0xff else f"R{n}"

def bsuf(sel):                 # byte-select mnemonic suffix (B0 default hidden)
    return "" if sel == 0 else f".{BSEL[sel]}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    Pg     = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    sel    = bits(w, 77, 76)          # insert (P2R) / a_bsel (R2P)
    Ra     = bits(w, 31, 24)
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    if opcode in P2R:
        Rd = bits(w, 23, 16)
        form = P2R[opcode]
        mask = f"{bits(w,63,32):#x}" if form == "I" else reg(bits(w,39,32))
        return f"{guard}P2R{bsuf(sel)} {reg(Rd)}, PR, {reg(Ra)}, {mask} ;"
    if opcode in R2P:
        form = R2P[opcode]
        mask = f"{bits(w,63,32):#x}" if form == "I" else reg(bits(w,39,32))
        return f"{guard}R2P{bsuf(sel)} PR, {reg(Ra)}, {mask} ;"
    raise AssertionError(f"bad opcode {opcode:#x}")

def enc_p2r_rrr(Rd,Ra,Rb,sel=0,Pg=7):
    w=(bits(0x203,12,12)<<91)|0x203|((Pg&7)<<12)|((Rd&0xff)<<16)|((Ra&0xff)<<24)|((Rb&0xff)<<32)|((sel&3)<<76)
    return w&((1<<64)-1),(w>>64)&((1<<64)-1)
def enc_r2p_rrr(Ra,Rb,sel=0,Pg=7):
    w=(bits(0x204,12,12)<<91)|0x204|((Pg&7)<<12)|((Ra&0xff)<<24)|((Rb&0xff)<<32)|((sel&3)<<76)
    return w&((1<<64)-1),(w>>64)&((1<<64)-1)

REAL = [
    (0x0000007f00037803, 0x000fca0000000000, "P2R R3, PR, R0, 0x7f ;"),   # pack 7 preds
    (0x0000000a02007804, 0x000fe40000000000, "R2P PR, R2, 0xa ;"),        # unpack mask 0xa
]
SYNTH = [
    (enc_p2r_rrr(3,0,5),       "P2R R3, PR, R0, R5 ;"),
    (enc_p2r_rrr(3,0,5,sel=1), "P2R.B1 R3, PR, R0, R5 ;"),
    (enc_r2p_rrr(2,6),         "R2P PR, R2, R6 ;"),
    (enc_r2p_rrr(2,6,sel=2),   "R2P.B2 PR, R2, R6 ;"),
]

if __name__ == "__main__":
    ok = True
    print("-- real captures --")
    for lo, hi, exp in REAL:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:24s} | exp {exp}")
    print("-- synthetic round-trips --")
    for (lo, hi), exp in SYNTH:
        got = decode(lo, hi); m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:24s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
