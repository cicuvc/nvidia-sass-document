#!/usr/bin/env python3
"""Decoder for VOTEU (uniform warp vote/ballot) on sm_90 — udp_pipe sibling of VOTE.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

One real capture (from __activemask()) anchors the layout; the other voteop modes
are round-trip constructions (encode documented fields -> decode), clearly marked.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OPCODE = 0x886
VOTEOP = {0: "ALL", 1: "ANY", 2: "EQ", 3: "INVALID3"}

def ureg(n): return "URZ" if n == 0x3f else f"UR{n}"
def upred(n): return "UPT" if n == 7 else f"UP{n}"
def pred(n): return "PT" if n == 7 else f"P{n}"

def encode(voteop=1, URd=0x3f, UPu=7, Pp=7, Pp_not=0, Pg=7, Pg_not=0):
    w = 0
    w |= (bits(OPCODE, 12, 12) << 91) | (bits(OPCODE, 11, 0) << 0)
    w |= (Pg & 7) << 12
    w |= (Pg_not & 1) << 15
    w |= (URd & 0x3f) << 16
    w |= (voteop & 3) << 72
    w |= (UPu & 7) << 81
    w |= (Pp & 7) << 87
    w |= (Pp_not & 1) << 90
    return w & ((1 << 64) - 1), (w >> 64) & ((1 << 64) - 1)

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode == OPCODE, f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    URd    = bits(w, 21, 16)
    voteop = bits(w, 73, 72)
    UPu    = bits(w, 83, 81)
    Pp     = bits(w, 89, 87)
    Pp_not = bits(w, 90, 90)
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    ops = []
    if URd != 0x3f:
        ops.append(ureg(URd))
    ops.append(upred(UPu))
    ops.append(f"{'!' if Pp_not else ''}{pred(Pp)}")
    return f"{guard}VOTEU.{VOTEOP[voteop]} " + ", ".join(ops) + " ;"

# real capture (lo64, hi64) + synthetic round-trips
REAL = [
    (0x0000000000047886, 0x000fe400038e0100, "VOTEU.ANY UR4, UPT, PT ;"),   # __activemask()
]
SYNTH = [
    (dict(voteop=1, URd=0x3f, UPu=0, Pp=0), "VOTEU.ANY UP0, P0 ;"),
    (dict(voteop=0, URd=0x3f, UPu=0, Pp=0), "VOTEU.ALL UP0, P0 ;"),
    (dict(voteop=2, URd=0x3f, UPu=0, Pp=0), "VOTEU.EQ UP0, P0 ;"),
    (dict(voteop=1, URd=5,    UPu=7, Pp=1, Pp_not=1), "VOTEU.ANY UR5, UPT, !P1 ;"),
]

if __name__ == "__main__":
    ok = True
    print("-- real captures --")
    for lo, hi, exp in REAL:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:30s} | exp {exp}")
    print("-- synthetic round-trips --")
    for kw, exp in SYNTH:
        lo, hi = encode(**kw)
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:26s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
