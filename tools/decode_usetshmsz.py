#!/usr/bin/env python3
"""Decoder for USETSHMSZ (SETSMEMSIZE) on sm_90.

NOTE: no ptxas/library emission of this instruction was found, so there are NO
real captured vectors. The field layout below is taken directly from the CLASS
ENCODING in sm_90_instructions.txt. Validation here is a round-trip (encode the
documented fields, then decode) — it proves the bit math is self-consistent, NOT
that it matches silicon/cuobjdump text.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OP_IMM = 0x19c9   # usetshmsz__Ib  and usetshmsz__FLUSH
OP_UR  = 0x13c9   # usetshmsz__URb

def encode(size=None, ur=None, flush=False, Pg=7, Pg_not=0):
    op = OP_UR if ur is not None else OP_IMM
    w = 0
    w |= (bits(op, 12, 12) << 91) | (bits(op, 11, 0) << 0)   # opcode {[91],[11:0]}
    w |= (Pg & 7) << 12
    w |= (Pg_not & 1) << 15
    if flush:
        w |= 1 << 72                     # e = FLUSHONLY(1)
    elif ur is not None:
        w |= (ur & 0x3f) << 32           # Ra_URb [37:32]
    else:
        w |= ((size or 0) & 0xfffff) << 32   # Sb [51:32], 20-bit byte size
    return w & ((1<<64)-1), (w >> 64) & ((1<<64)-1)

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in (OP_IMM, OP_UR), f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    e      = bits(w, 72, 72)             # 1 => .FLUSH
    pred = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}UP{Pg} "
    if e:
        return f"{pred}USETSHMSZ.FLUSH ;"
    if opcode == OP_UR:
        ur = bits(w, 37, 32)
        rb = "URZ" if ur == 63 else f"UR{ur}"
        return f"{pred}USETSHMSZ {rb} ;"
    sz = bits(w, 51, 32)
    return f"{pred}USETSHMSZ {sz:#x} ;"

# round-trip self-tests (SYNTHETIC — not silicon-verified)
CASES = [
    (dict(size=0x8000), "USETSHMSZ 0x8000 ;"),
    (dict(size=0x0),    "USETSHMSZ 0x0 ;"),
    (dict(size=0xfffff),"USETSHMSZ 0xfffff ;"),
    (dict(ur=5),        "USETSHMSZ UR5 ;"),
    (dict(ur=63),       "USETSHMSZ URZ ;"),
    (dict(flush=True),  "USETSHMSZ.FLUSH ;"),
    (dict(size=0x100, Pg=0, Pg_not=1), "@!UP0 USETSHMSZ 0x100 ;"),
]

if __name__ == "__main__":
    ok = True
    for kw, exp in CASES:
        lo, hi = encode(**kw)
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:32s} | exp {exp}")
    print("ROUND-TRIP OK (synthetic)" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
