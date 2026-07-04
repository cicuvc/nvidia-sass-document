#!/usr/bin/env python3
"""FSET decoder — FP32 comparison result to register."""

import struct
from typing import Optional

FCMP_NAMES = {
    0: "F",  1: "LT",  2: "EQ",  3: "LE",
    4: "GT", 5: "NE",  6: "GE",  7: "NUM",
    8: "NAN",9: "LTU",10: "EQU",11: "LEU",
    12:"GTU",13:"NEU",14:"GEU",15:"T",
}
BOP_NAMES = {0: "AND", 1: "OR", 2: "XOR"}

OPCODES = {
    0x20a: ("FSET", "RRR_RRR"),
    0x80a: ("FSET", "RIR_RIR"),
    0xa0a: ("FSET", "RCR_RCR"),
    0x1a0a: ("FSET", "RCxR_RCxR"),
    0x1c0a: ("FSET", "RUR_RUR"),
}

def extract(lo64, hi64, bits):
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val

def get_opcode(lo64, hi64):
    return extract(lo64, hi64, [91, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0])

def reg_s(r):
    return f"R{r}" if r != 0xff else "RZ"

def decode_fset(lo64, hi64):
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES:
        return None
    mnem, variant = OPCODES[opc]

    pg     = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rd     = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    fcomp  = extract(lo64, hi64, [79, 78, 77, 76])
    bop    = extract(lo64, hi64, [75, 74])
    ftz    = extract(lo64, hi64, [80])
    pp     = extract(lo64, hi64, [89, 88, 87])
    pp_not = extract(lo64, hi64, [90])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}P{pg}")

    cmp_name = FCMP_NAMES.get(fcomp, f"?{fcomp}")
    suffixes = []
    if ftz: suffixes.append("FTZ")
    suffixes.append(cmp_name)
    if bop in BOP_NAMES: suffixes.append(BOP_NAMES[bop])

    if pp == 7:
        pp_str = "!" if pp_not else ""
        pp_str += "PT"
    else:
        pp_str = f"P{pp}"
        if pp_not: pp_str = f"!{pp_str}"

    suff = ".BF." + ".".join(suffixes) if suffixes else ".BF"

    if variant == "RRR_RRR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
        operands = f"{reg_s(rd)}, {reg_s(ra)}, {reg_s(rb)}"
    elif variant == "RIR_RIR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        sb_imm = extract(lo64, hi64, list(range(63, 31, -1)))
        operands = f"{reg_s(rd)}, {reg_s(ra)}, {sb_imm}"
    elif variant == "RUR_RUR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        urb = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])
        operands = f"{reg_s(rd)}, {reg_s(ra)}, UR{urb}"
    else:
        return f"{mnem} ({variant}) — NYI"

    parts.append(f"{mnem}{suff} {operands}, {pp_str};")
    return f"({variant}) {' '.join(parts)}"

# ============================================================
TESTS = [
    # sm_90 kernel output — all share lo64=0x000000050405720a
    ("0x000000050405720a", "0x001fc60003801000", "FSET.BF.LT.AND"),
    ("0x000000050405720a", "0x001fc60003802000", "FSET.BF.EQ.AND"),
    ("0x000000050405720a", "0x001fc60003803000", "FSET.BF.LE.AND"),
    ("0x000000050405720a", "0x001fc60003804000", "FSET.BF.GT.AND"),
    ("0x000000050405720a", "0x001fc60003805000", "FSET.BF.NE.AND"),
    ("0x000000050405720a", "0x001fc60003806000", "FSET.BF.GE.AND"),
    ("0x000000050405720a", "0x001fc60003807000", "FSET.BF.NUM.AND"),
    ("0x000000050405720a", "0x001fc60003808000", "FSET.BF.NAN.AND"),
    ("0x000000050405720a", "0x001fc60003809000", "FSET.BF.LTU.AND"),
    ("0x000000050405720a", "0x001fc6000380a000", "FSET.BF.EQU.AND"),
    ("0x000000050405720a", "0x001fc6000380b000", "FSET.BF.LEU.AND"),
    ("0x000000050405720a", "0x001fc6000380c000", "FSET.BF.GTU.AND"),
    ("0x000000050405720a", "0x001fc6000380d000", "FSET.BF.NEU.AND"),
    ("0x000000050405720a", "0x001fc6000380e000", "FSET.BF.GEU.AND"),
]

print("=" * 75)
print("FSET Decoder — 14 comparison types")
print("=" * 75)
ok = 0
for lo_s, hi_s, exp in TESTS:
    r = decode_fset(int(lo_s, 16), int(hi_s, 16))
    m = "(match)" if r and exp in r else "(MISMATCH)"
    if r and exp in r: ok += 1
    print(f"  expected prefix: {exp}")
    print(f"  decoded:          {r} {m}")
print(f"\n{ok}/{len(TESTS)} matches")
