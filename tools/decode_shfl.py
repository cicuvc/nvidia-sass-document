#!/usr/bin/env python3
"""Decoder for SHFL (warp shuffle: __shfl_sync family) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).
Validates against real cuobjdump captures (sm_90, CUDA 13.1).

Operand forms (by opcode): index (b) and bound (c) each register or immediate:
  RRR=0x389  RRI=0x589  RIR=0x989  RII=0xf89   (b, then c)
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

SHFLMD = {0: "IDX", 1: "UP", 2: "DOWN", 3: "BFLY"}
FORM = {0x389: ("R", "R"), 0x589: ("R", "I"), 0x989: ("I", "R"), 0xf89: ("I", "I")}

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def pred(n): return "PT" if n == 7 else f"P{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in FORM, f"bad opcode {opcode:#x}"
    bform, cform = FORM[opcode]
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    Rd     = bits(w, 23, 16)
    Ra     = bits(w, 31, 24)
    shflmd = bits(w, 59, 58)
    Pu     = bits(w, 83, 81)
    # index operand b
    b = reg(bits(w, 39, 32)) if bform == "R" else f"{bits(w, 57, 53):#x}"
    # bound operand c
    c = reg(bits(w, 71, 64)) if cform == "R" else f"{bits(w, 52, 40):#x}"
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    return f"{guard}SHFL.{SHFLMD[shflmd]} {pred(Pu)}, {reg(Rd)}, {reg(Ra)}, {b}, {c} ;"

# real captured vectors (lo64, hi64, expected)
VEC = [
    (0x08001f0702077589, 0x002e2800000e0000, "SHFL.DOWN PT, R7, R2, R7, 0x1f ;"),   # RRI reg delta
    (0x00781f0002077f89, 0x004e2800000e0000, "SHFL.IDX PT, R7, R2, 0x3, 0x181f ;"), # RII width=8
    (0x0e001f0002077f89, 0x004e2800000e0000, "SHFL.BFLY PT, R7, R2, 0x10, 0x1f ;"), # RII xor 16
    (0x08401f0002077f89, 0x004e2800000e0000, "SHFL.DOWN PT, R7, R2, 0x2, 0x1f ;"),  # RII down 2
    (0x0420000002077989, 0x004e2800000e00ff, "SHFL.UP PT, R7, R2, 0x1, RZ ;"),      # RIR up 1 (bound=RZ)
    (0x00001f0702077589, 0x002e2800000e0000, "SHFL.IDX PT, R7, R2, R7, 0x1f ;"),    # RRI reg lane
    (0x00601f0002077f89, 0x004e2800000e0000, "SHFL.IDX PT, R7, R2, 0x3, 0x1f ;"),   # RII idx 3
]

if __name__ == "__main__":
    ok = True
    for lo, hi, exp in VEC:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:38s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
