#!/usr/bin/env python3
"""Decoder for B2R / R2B (barrier-register <-> GPR moves) on sm_90.
128-bit instruction = hi64 (bits[127:64]) + lo64 (bits[63:0]).

B2R.RESULT is verified against real cuobjdump captures (sm_90, CUDA 13.1) from
__syncthreads_count/and/or (reads the BAR.RED reduction result). B2R.BAR/.WARP and
R2B were not observed (barrier-state save/restore, driver/trap level) -> round-trip only.
"""
import sys

def bits(w, hi, lo):
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)

OP_B2R = 0x31c
OP_R2B = 0x31e
B2R_MODE = {0: "BAR", 1: "RESULT", 2: "WARP"}    # BarmdBAR/RESULT/WARP
R2B_MODE = {0: "BAR", 2: "WARP"}                 # MODE_BAR_WARP (1,3 invalid)

def reg(n): return "RZ" if n == 0xff else f"R{n}"
def pred(n): return "PT" if n == 7 else f"P{n}"

def decode(lo64, hi64):
    w = (hi64 << 64) | lo64
    opcode = (bits(w, 91, 91) << 12) | bits(w, 11, 0)
    Pg     = bits(w, 14, 12)
    Pg_not = bits(w, 15, 15)
    mode   = bits(w, 79, 78)      # stride
    guard = "" if (Pg == 7 and not Pg_not) else f"@{'!' if Pg_not else ''}P{Pg} "
    if opcode == OP_B2R:
        Rd = bits(w, 23, 16)
        if mode == 1:             # RESULT: Rd[, Pu]
            Pu = bits(w, 83, 81)
            s = f"B2R.RESULT {reg(Rd)}"
            if Pu != 7: s += f", {pred(Pu)}"
            return f"{guard}{s} ;"
        if mode == 2:             # WARP: Rd
            return f"{guard}B2R.WARP {reg(Rd)} ;"
        # BAR (default, hidden): Rd, barname
        bar = bits(w, 57, 54)
        return f"{guard}B2R {reg(Rd)}, {bar:#x} ;"
    if opcode == OP_R2B:
        Rb  = bits(w, 39, 32)
        bar = bits(w, 57, 54)
        suffix = "" if mode == 0 else ".WARP"     # BAR default hidden
        return f"{guard}R2B{suffix} {bar:#x}, {reg(Rb)} ;"
    raise AssertionError(f"bad opcode {opcode:#x}")

def encode_b2r(mode=1, Rd=0, Pu=7, bar=0, Pg=7, Pg_not=0):
    w = (bits(OP_B2R,12,12)<<91)|(bits(OP_B2R,11,0)) | ((Pg&7)<<12)|((Pg_not&1)<<15)
    w |= (Rd&0xff)<<16 | (mode&3)<<78
    if mode == 1: w |= (Pu&7)<<81
    if mode == 0: w |= (bar&0xf)<<54
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

def encode_r2b(mode=0, Rb=0, bar=0, Pg=7, Pg_not=0):
    w = (bits(OP_R2B,12,12)<<91)|(bits(OP_R2B,11,0)) | ((Pg&7)<<12)|((Pg_not&1)<<15)
    w |= (Rb&0xff)<<32 | (bar&0xf)<<54 | (mode&3)<<78 | (7<<110)   # dst_wr_sb pinned 7
    return w & ((1<<64)-1), (w>>64)&((1<<64)-1)

REAL = [
    (0x000000000007731c, 0x000e2800000e4000, "B2R.RESULT R7 ;"),        # __syncthreads_count (popc)
    (0x0000000000ff731c, 0x000e240000004000, "B2R.RESULT RZ, P0 ;"),    # __syncthreads_and/or
]
SYNTH = [
    (encode_b2r(mode=0, Rd=4, bar=3),   "B2R R4, 0x3 ;"),
    (encode_b2r(mode=2, Rd=5),          "B2R.WARP R5 ;"),
    (encode_r2b(mode=0, Rb=6, bar=1),   "R2B 0x1, R6 ;"),
    (encode_r2b(mode=2, Rb=7, bar=2),   "R2B.WARP 0x2, R7 ;"),
]

if __name__ == "__main__":
    ok = True
    print("-- real captures --")
    for lo, hi, exp in REAL:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}{got:22s} | exp {exp}")
    print("-- synthetic round-trips --")
    for (lo, hi), exp in SYNTH:
        got = decode(lo, hi)
        m = "OK " if got == exp else "XX "
        if got != exp: ok = False
        print(f"{m}lo={lo:#018x} hi={hi:#018x} -> {got:18s} | exp {exp}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
