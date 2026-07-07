#!/usr/bin/env python3
"""Decoder for GETLMEMBASE / SETLMEMBASE on sm_90.

NOTE: legacy pair (sm_70+). ptxas no longer emits them (modern local-memory
spill/addressing uses the implicit per-thread ABI window, not an explicit base
register), and they are absent from the available libraries. Field layout is
from the CLASS ENCODING in sm_90_instructions.txt; validation is a round-trip
(encode documented fields -> decode), NOT a match against silicon/cuobjdump.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OP_GET = 0x3c0   # writes Rd (64-bit pair)
OP_SET = 0x3c1   # reads  Ra (64-bit pair)

def reg(n):
    return "RZ" if n == 0xff else f"R{n}"

def encode(op, R=0, Pg=7, Pg_not=0):
    w = 0
    w |= (bits(op, 12, 12) << 91) | (bits(op, 11, 0) << 0)
    w |= (Pg & 7) << 12
    w |= (Pg_not & 1) << 15
    if op == OP_GET:
        w |= (R & 0xff) << 16          # Rd [23:16]
    else:
        w |= (R & 0xff) << 24          # Ra [31:24]
        w |= 7 << 110                  # dst_wr_sb pinned to 7
    return w & ((1 << 64) - 1), (w >> 64) & ((1 << 64) - 1)

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    pred = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    if opcode == OP_GET:
        return f"{pred}GETLMEMBASE {reg(bits(w,23,16))} ;"   # Rd:Rd+1
    if opcode == OP_SET:
        return f"{pred}SETLMEMBASE {reg(bits(w,31,24))} ;"   # Ra:Ra+1
    raise AssertionError(f"bad opcode {opcode:#x}")

# round-trip self-tests (SYNTHETIC — not silicon-verified)
CASES = [
    (OP_GET, dict(R=2),  "GETLMEMBASE R2 ;"),
    (OP_GET, dict(R=4),  "GETLMEMBASE R4 ;"),
    (OP_SET, dict(R=2),  "SETLMEMBASE R2 ;"),
    (OP_SET, dict(R=6),  "SETLMEMBASE R6 ;"),
    (OP_GET, dict(R=8, Pg=0, Pg_not=1), "@!P0 GETLMEMBASE R8 ;"),
]

if __name__ == "__main__":
    ok = True
    for op, kw, exp in CASES:
        lo, hi = encode(op, **kw)
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:28s} | exp {exp}")
    print("ROUND-TRIP OK (synthetic)" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
