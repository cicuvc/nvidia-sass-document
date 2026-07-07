#!/usr/bin/env python3
"""Decoder for LEPC (Load Effective PC) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

Verified against real cuobjdump captures (sm_90, CUDA 13.1) from a printf kernel:
printf lowering emits `LEPC Rd, target` to form a PC-relative address for the
vprintf ABI. The R_I_R form's printed operand is the RESOLVED target =
(instr_addr + 16) + sImm58 (next-instruction-relative); reconstruction therefore
needs the instruction's own address.

The RRR form (LEPC Rd, no imm, opcode 0x34e) was not observed on sm_90 (sm_70 idiom);
it is round-trip only.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OP_RRR = 0x34e   # LEPC Rd           (PC into Rd:Rd+1)   -- sm_70, not seen on sm_90
OP_RIR = 0x94e   # LEPC Rd, sImm58   (PC + imm58)        -- sm_90

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def sext(v, n): return v - (1 << n) if (v >> (n - 1)) & 1 else v

def encode(op, Rd=0, imm=0, Pg=7, Pg_not=0):
    w = 0
    w |= (bits(op, 12, 12) << 91) | (bits(op, 11, 0) << 0)
    w |= (Pg & 7) << 12
    w |= (Pg_not & 1) << 15
    w |= (Rd & 0xff) << 16
    if op == OP_RIR:
        w |= (imm & ((1 << 58) - 1)) << 24
    return w & ((1 << 64) - 1), (w >> 64) & ((1 << 64) - 1)

def decode(lo64, hi64, addr=None):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    assert opcode in (OP_RRR, OP_RIR), f"bad opcode {opcode:#x}"
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    Rd     = bits(w, 23, 16)
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    if opcode == OP_RRR:
        return f"{guard}LEPC {reg(Rd)} ;"
    imm = sext(bits(w, 81, 24), 58)
    if addr is not None:                       # cuobjdump prints resolved target
        tgt = addr + 16 + imm
        return f"{guard}LEPC {reg(Rd)}, {tgt:#x} ;"
    sign = "-" if imm < 0 else ""              # address-agnostic: raw offset
    return f"{guard}LEPC {reg(Rd)}, {sign}{abs(imm):#x} ;"

# real captured vectors (addr, lo64, hi64, expected)  -- from tests/lepc_test.cu (printf)
REAL = [
    (0x110, 0x000000001014794e, 0x000fce0000000000, "LEPC R20, 0x130 ;"),
    (0x1d0, 0x000000001014794e, 0x000fce0000000000, "LEPC R20, 0x1f0 ;"),
]
# synthetic round-trips (RRR unseen on sm_90; negative imm)
SYNTH = [
    (OP_RRR, dict(Rd=2),            None, "LEPC R2 ;"),
    (OP_RIR, dict(Rd=6, imm=0x100), None, "LEPC R6, 0x100 ;"),
    (OP_RIR, dict(Rd=8, imm=-8),    None, "LEPC R8, -0x8 ;"),
]

if __name__ == "__main__":
    ok = True
    print("-- real captures (printf) --")
    for addr, lo, hi, exp in REAL:
        got = decode(lo, hi, addr)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}@{addr:#06x} {got:22s} | exp {exp}")
    print("-- synthetic round-trips --")
    for op, kw, addr, exp in SYNTH:
        lo, hi = encode(op, **kw)
        got = decode(lo, hi, addr)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:16s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
