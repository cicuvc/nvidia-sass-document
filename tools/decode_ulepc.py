#!/usr/bin/env python3
"""Decoder for ULEPC (Uniform Load Effective PC) on sm_90 — udp_pipe sibling of LEPC.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

NOTE: no real ULEPC capture (ptxas emitted per-thread LEPC for the printf/assert
paths tried; ULEPC needs a warp-uniform CALL/relative-address context not produced
here). Encoding is from the CLASS ENCODING; the layout is identical to the verified
LEPC (see decode_lepc.py) except the destination is a uniform register URd[21:16] and
the pipe is udp_pipe. Validation is a round-trip (encode -> decode).
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OP_URURUR = 0x13ce   # ULEPC URd            (PC into URd:URd+1)
OP_UR_I_R = 0x19ce   # ULEPC URd, sImm58    (PC + imm58)  (+ ulepc_rel_ ALT, same bits)

def ureg(n): return "URZ" if n == 0x3f else f"UR{n}"
def sext(v, n): return v - (1 << n) if (v >> (n - 1)) & 1 else v

def encode(op, URd=0, imm=0, Pg=7, Pg_not=0):
    w = (bits(op,12,12)<<91)|bits(op,11,0)|((Pg&7)<<12)|((Pg_not&1)<<15)
    w |= (URd & 0x3f) << 16
    if op == OP_UR_I_R:
        w |= (imm & ((1 << 58) - 1)) << 24
    return w & ((1 << 64) - 1), (w >> 64) & ((1 << 64) - 1)

def decode(lo64, hi64, addr=None):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in (OP_URURUR, OP_UR_I_R), f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12); Pg_not = bits(w, 15, 15)
    URd    = bits(w, 21, 16)
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}UP{Pg} "
    if opcode == OP_URURUR:
        return f"{guard}ULEPC {ureg(URd)} ;"
    imm = sext(bits(w, 81, 24), 58)
    if addr is not None:                       # cuobjdump prints resolved target (as LEPC)
        return f"{guard}ULEPC {ureg(URd)}, {addr + 16 + imm:#x} ;"
    sign = "-" if imm < 0 else ""
    return f"{guard}ULEPC {ureg(URd)}, {sign}{abs(imm):#x} ;"

# round-trip self-tests (SYNTHETIC — not silicon-verified)
CASES = [
    (OP_URURUR, dict(URd=4),            None, "ULEPC UR4 ;"),
    (OP_UR_I_R, dict(URd=6, imm=0x100), None, "ULEPC UR6, 0x100 ;"),
    (OP_UR_I_R, dict(URd=8, imm=-8),    None, "ULEPC UR8, -0x8 ;"),
    (OP_UR_I_R, dict(URd=6, imm=0x10),  0x110, "ULEPC UR6, 0x130 ;"),  # LEPC-style resolved target
]

if __name__ == "__main__":
    ok = True
    for op, kw, addr, exp in CASES:
        lo, hi = encode(op, **kw)
        got = decode(lo, hi, addr)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:20s} | exp {exp}")
    print("ROUND-TRIP OK (synthetic)" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
