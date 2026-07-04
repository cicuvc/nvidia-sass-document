#!/usr/bin/env python3
"""FMUL decoder — 5 variants, verifying encoding vs disassembly."""

import struct
from typing import Optional

RND_NAMES = {0: "RN", 1: "RM", 2: "RP", 3: "RZ"}
SAT_NAMES = {0: "nosat", 1: "SAT"}

OPCODES = {
    0x220:  ("FMUL", "RRR_RR"),
    0x820:  ("FMUL", "RIR_RI"),
    0xa20:  ("FMUL", "RCR_RC"),
    0x1a20: ("FMUL", "RCxR_RCx"),
    0x1c20: ("FMUL", "RUR_RU"),
}

def extract(lo64: int, hi64: int, bits: list[int]) -> int:
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val

def get_opcode(lo64: int, hi64: int) -> int:
    return extract(lo64, hi64, [91, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0])

def reg_s(r: int, neg: int, abs_: int) -> str:
    name = f"R{r}" if r != 0xff else "RZ"
    if neg: name = f"-{name}"
    elif abs_: name = f"|{name}|"
    return name

def ur_s(r: int, neg: int, abs_: int) -> str:
    name = f"UR{r}" if r != 0x3f else "URZ"
    if neg: name = f"-{name}"
    elif abs_: name = f"|{name}|"
    return name

def decode_fmul(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES:
        return None
    mnem, variant = OPCODES[opc]

    pg     = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rd     = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    fmz    = extract(lo64, hi64, [80, 76])
    rnd    = extract(lo64, hi64, [79, 78])
    sat    = extract(lo64, hi64, [77])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}P{pg}")

    suff = ""
    if rnd != 0: suff += f".{RND_NAMES[rnd]}"
    if sat != 0: suff += ".SAT"
    if fmz == 1: suff += ".FMZ"
    elif fmz == 2: suff += ".FTZ"

    if variant in ("RRR_RR", "RUR_RU"):
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])

        if variant == "RRR_RR":
            rb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
            rb_neg = extract(lo64, hi64, [63])
            rb_abs = extract(lo64, hi64, [62])
            rd_s = reg_s(rd, 0, 0)
            ra_s = reg_s(ra, ra_neg, ra_abs)
            rb_s = reg_s(rb, rb_neg, rb_abs)
        else:  # RUR_RU
            urb = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])
            urb_neg = extract(lo64, hi64, [63])
            urb_abs = extract(lo64, hi64, [62])
            rd_s = reg_s(rd, 0, 0)
            ra_s = reg_s(ra, ra_neg, ra_abs)
            rb_s = ur_s(urb, urb_neg, urb_abs)

    elif variant == "RIR_RI":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        sb_imm = extract(lo64, hi64, list(range(63, 31, -1)))
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        sb_f32 = struct.unpack('>f', struct.pack('>I', sb_imm))[0]
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = f"{sb_f32:g}"

    else:
        return f"{mnem} ({variant}) — NYI"

    parts.append(f"{mnem}{suff} {rd_s}, {ra_s}, {rb_s};")
    return f"({variant}) {' '.join(parts)}"


TESTS = [
    # kernel: RIR imm Sb=3.0
    ("0x4040000005057820", "0x001fc60000400000", "FMUL R5, R5, 3"),
    # kernel: RRR .RZ
    ("0x0000000504057220", "0x001fca000040c000", "FMUL.RZ R5, R4, R5"),
    # kernel: RRR plain (double negate cancelled → a*b)
    ("0x0000000504057220", "0x001fe40000400000", "FMUL R5, R4, R5"),
    # kernel: RRR .RM
    ("0x0000000504057220", "0x001fe40000404000", "FMUL.RM R5, R4, R5"),
    # kernel: RRR .RP
    ("0x0000000504057220", "0x001fc60000408000", "FMUL.RP R5, R4, R5"),
    # kernel: RUR (RZ * UR6 = 0)
    ("0x00000006ff057c20", "0x000fc60008400000", "FMUL R5, RZ, UR6"),
    # kernel: RRR .FTZ
    ("0x0000000504057220", "0x001fe40000410000", "FMUL.FTZ R5, R4, R5"),
    # kernel: RRR .SAT
    ("0x0000000504057220", "0x001fe40000402000", "FMUL.SAT R5, R4, R5"),
    # cublas: RRR predicated
    ("0x00000013101c0220", "0x002fe20000400000", "@P0 FMUL R28, R16, R19"),
    ("0x000000131c1c1220", "0x001fca0000400000", "@P1 FMUL R28, R28, R19"),
]

print("=" * 75)
print("FMUL Decoder — verification against cuobjdump disassembly")
print("=" * 75)

ok = 0
for lo_str, hi_str, expected in TESTS:
    lo = int(lo_str, 16)
    hi = int(hi_str, 16)
    result = decode_fmul(lo, hi)
    if result is None:
        print(f"\nFAIL: UNKNOWN {lo_str}/{hi_str}")
        continue
    match = "(match)" if expected in result else "(MISMATCH)"
    if expected in result:
        ok += 1
    print(f"\n  cuobjdump: {expected}")
    print(f"  decoded:   {result} {match}")

print(f"\n{'='*75}")
print(f"{ok}/{len(TESTS)} matches")
