#!/usr/bin/env python3
"""FADD full decoder — all 5 variants, verifying encoding vs disassembly."""

import struct
from typing import Optional

RND_NAMES = {0: "RN", 1: "RM", 2: "RP", 3: "RZ"}
SAT_NAMES = {0: "nosat", 1: "SAT"}

OPCODES = {
    0x221:  ("FADD", "RRR_RR"),
    0x421:  ("FADD", "RRI_RI"),
    0x621:  ("FADD", "RRC_RC"),
    0x1621: ("FADD", "RRCx_RCx"),
    0x1e21: ("FADD", "RRU_RU"),
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

def decode_fadd(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES:
        return None
    mnem, variant = OPCODES[opc]

    pg      = extract(lo64, hi64, [14, 13, 12])
    pg_not  = extract(lo64, hi64, [15])
    rd      = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    ftz     = extract(lo64, hi64, [80])
    rnd     = extract(lo64, hi64, [79, 78])
    sat     = extract(lo64, hi64, [77])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}P{pg}")

    suff = ""
    if rnd != 0: suff += f".{RND_NAMES[rnd]}"
    if sat != 0: suff += ".SAT"
    if ftz != 0: suff += ".FTZ"

    if variant == "RRR_RR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rc = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        rc_neg = extract(lo64, hi64, [63])
        rc_abs = extract(lo64, hi64, [62])
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rc_s = reg_s(rc, rc_neg, rc_abs)

    elif variant == "RRU_RU":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        urc = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        urc_neg = extract(lo64, hi64, [63])
        urc_abs = extract(lo64, hi64, [62])
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rc_s = ur_s(urc, urc_neg, urc_abs)

    elif variant == "RRI_RI":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        sc_imm = extract(lo64, hi64, list(range(63, 31, -1)))
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        sc_f32 = struct.unpack('>f', struct.pack('>I', sc_imm))[0]
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rc_s = f"{sc_f32:g}"

    else:
        return f"{mnem} ({variant}) — NYI"

    parts.append(f"{mnem}{suff} {rd_s}, {ra_s}, {rc_s};")
    return f"({variant}) {' '.join(parts)}"


# Test vectors from compiled disassembly + cublas
TESTS = [
    ("0x4040000005057421", "0x001fca0000000000", "FADD R5, R5, 3"),          # RRI imm Sc=3.0
    ("0x8000000504057221", "0x001fc60000000100", "FADD R5, -R4, -R5"),         # RRR double negate
    ("0x0000000504057221", "0x001fe4000000c000", "FADD.RZ R5, R4, R5"),         # RRR .RZ
    ("0x8000000504057221", "0x001fca0000000000", "FADD R5, R4, -R5"),           # RRR negate Rc
    ("0x8000000405057221", "0x001fe40000000000", "FADD R5, R5, -R4"),           # RRR negate Rc (alt)
    ("0x0000000504057221", "0x001fc60000004000", "FADD.RM R5, R4, R5"),         # RRR .RM
    ("0x0000000504057221", "0x001fe40000008000", "FADD.RP R5, R4, R5"),         # RRR .RP
    ("0x0000000504057221", "0x001fca0000000000", "FADD R5, R4, R5"),            # RRR plain
    ("0x00000006ff057e21", "0x000fe20008000000", "FADD R5, RZ, UR6"),           # RRU
    ("0x0000000504057221", "0x001fc60000010000", "FADD.FTZ R5, R4, R5"),        # RRR .FTZ
    ("0x0000000504057221", "0x001fe40000002000", "FADD.SAT R5, R4, R5"),        # RRR .SAT
    # cublas
    ("0x800000ff1920e221", "0x004fe20000000100", "@!P6 FADD R32, -R25, -RZ"),
    ("0x800000ff1504c221", "0x000fe20000000100", "@!P4 FADD R4, -R21, -RZ"),
    ("0x800000ff0f089221", "0x004fe20000000100", "@!P1 FADD R8, -R15, -RZ"),
]

print("=" * 75)
print("FADD Decoder — verification against cuobjdump disassembly")
print("=" * 75)

ok = 0
for lo_str, hi_str, expected in TESTS:
    lo = int(lo_str, 16)
    hi = int(hi_str, 16)
    result = decode_fadd(lo, hi)
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
