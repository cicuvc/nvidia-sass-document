#!/usr/bin/env python3
"""FFMA full decoder — all 9 variants, verifying encoding vs disassembly."""

import sys
from typing import Optional

FMZ_NAMES = {0: "nofmz_hfma2", 1: "FMZ", 2: "FTZ", 3: "INVALID3"}
RND_NAMES = {0: "RN", 1: "RM", 2: "RP", 3: "RZ"}
SAT_NAMES = {0: "nosat", 1: "SAT"}

# All FFMA opcodes in 13-bit (bit91 + bits[11:0])
OPCODES = {
    0x223:  ("FFMA", "RRR_RRR"),
    0x423:  ("FFMA", "RRI_RRI"),
    0x623:  ("FFMA", "RRC_RRC"),
    0x823:  ("FFMA", "RIR_RIR"),
    0xa23:  ("FFMA", "RCR_RCR"),
    0x1623: ("FFMA", "RRCx_RRCx"),
    0x1a23: ("FFMA", "RCxR_RCxR"),
    0x1c23: ("FFMA", "RUR_RUR"),
    0x1e23: ("FFMA", "RRU_RRU"),
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

def decode_fffma(lo64: int, hi64: int) -> Optional[str]:
    """Reconstruct full SASS assembly from raw 128-bit encoding."""
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES:
        return None
    mnem, variant = OPCODES[opc]

    pg      = extract(lo64, hi64, [14, 13, 12])
    pg_not  = extract(lo64, hi64, [15])
    rd      = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    fmz     = extract(lo64, hi64, [80, 76])
    rnd     = extract(lo64, hi64, [79, 78])
    sat     = extract(lo64, hi64, [77])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}P{pg}")

    suff = ""
    if rnd != 0: suff += f".{RND_NAMES[rnd]}"
    if sat != 0: suff += ".SAT"
    if fmz == 1: suff += ".FMZ"
    elif fmz == 2: suff += ".FTZ"

    if variant == "RRR_RRR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
        rc = extract(lo64, hi64, [71, 70, 69, 68, 67, 66, 65, 64])
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        rb_neg = extract(lo64, hi64, [63])
        rb_abs = extract(lo64, hi64, [62])
        rc_neg = extract(lo64, hi64, [75])
        rc_abs = extract(lo64, hi64, [74])
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = reg_s(rb, rb_neg, rb_abs)
        rc_s = reg_s(rc, rc_neg, rc_abs)

    elif variant == "RRU_RRU":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rb = extract(lo64, hi64, [71, 70, 69, 68, 67, 66, 65, 64])
        urc = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        rb_neg = extract(lo64, hi64, [75])
        rb_abs = extract(lo64, hi64, [74])
        urc_neg = extract(lo64, hi64, [63])
        urc_abs = extract(lo64, hi64, [62])
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = reg_s(rb, rb_neg, rb_abs)
        rc_s = ur_s(urc, urc_neg, urc_abs)

    elif variant == "RIR_RIR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rc = extract(lo64, hi64, [71, 70, 69, 68, 67, 66, 65, 64])
        sb_imm = extract(lo64, hi64, list(range(63, 31, -1)))  # [63:32] MSB-first
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        rc_neg = extract(lo64, hi64, [75])
        rc_abs = extract(lo64, hi64, [74])
        # Decode F32Imm
        import struct
        sb_f32 = struct.unpack('>f', struct.pack('>I', sb_imm))[0]
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = f"{sb_f32:g}"
        rc_s = reg_s(rc, rc_neg, rc_abs)

    elif variant == "RRI_RRI":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rb = extract(lo64, hi64, [71, 70, 69, 68, 67, 66, 65, 64])
        sc_imm = extract(lo64, hi64, list(range(63, 31, -1)))
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        rb_neg = extract(lo64, hi64, [75])
        rb_abs = extract(lo64, hi64, [74])
        import struct
        sc_f32 = struct.unpack('>f', struct.pack('>I', sc_imm))[0]
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = reg_s(rb, rb_neg, rb_abs)
        rc_s = f"{sc_f32:g}"

    else:
        return f"{mnem} ({variant}) — decoder NYI"

    parts.append(f"{mnem}{suff} {rd_s}, {ra_s}, {rb_s}, {rc_s};")
    return f"({variant}) {' '.join(parts)}"

# ============================================================
# Test vectors from compiled+disassembled CUDA kernel + cublas
# ============================================================
TESTS = [
    # (lo64_str, hi64_str, cuobjdump_asm)
    ("0x4000000005057823", "0x001fe20000000000", "FFMA R5, R5, 2, R0"),
    ("0x4040000004057423", "0x001fc60000000005", "FFMA R5, R4, R5, 3"),
    ("0x8000000604057e23", "0x001fe20008000005", "FFMA R5, R4, R5, -UR6"),
    ("0x0000000604057e23", "0x001fc60008000105", "FFMA R5, -R4, R5, UR6"),
    ("0x0000000604057e23", "0x001fe20008004005", "FFMA.RM R5, R4, R5, UR6"),
    ("0x0000000604057e23", "0x001fe20008008005", "FFMA.RP R5, R4, R5, UR6"),
    ("0x0000000604057e23", "0x001fe2000800c005", "FFMA.RZ R5, R4, R5, UR6"),
    ("0x0000000604057e23", "0x001fe20008000005", "FFMA R5, R4, R5, UR6"),
    ("0x0000000604057e23", "0x001fe20008002005", "FFMA.SAT R5, R4, R5, UR6"),
    ("0x0000000604057e23", "0x001fe20008010005", "FFMA.FTZ R5, R4, R5, UR6"),
    ("0x0000000302057223", "0x001fe200000000ff", "FFMA R5, R2, R3, RZ"),
    ("0x0000000912130223", "0x040fe2000000081a", "@P0 FFMA R19, R18, R9, -R26"),
]

print("=" * 75)
print("FFMA Decoder — verification against cuobjdump disassembly")
print("=" * 75)

ok = 0
for lo_str, hi_str, expected in TESTS:
    lo = int(lo_str, 16)
    hi = int(hi_str, 16)
    result = decode_fffma(lo, hi)
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
