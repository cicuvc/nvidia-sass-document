#!/usr/bin/env python3
"""FMNMX decoder — base variant (isA=0), verifying encoding vs disassembly."""

import struct
from typing import Optional

OPCODES = {
    0x209:  ("FMNMX", "RRR_RRR"),
    0x809:  ("FMNMX", "RIR_RIR"),
    0xa09:  ("FMNMX", "RCR_RCR"),
    0x1a09: ("FMNMX", "RCxR_RCxR"),
    0x1c09: ("FMNMX", "RUR_RUR"),
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

def decode_fmnmx(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES:
        return None
    mnem, variant = OPCODES[opc]

    pg     = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rd     = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    ftz    = extract(lo64, hi64, [80])
    nan    = extract(lo64, hi64, [81])
    xors   = extract(lo64, hi64, [82])
    pp     = extract(lo64, hi64, [89, 88, 87])
    pp_not = extract(lo64, hi64, [90])
    isa    = extract(lo64, hi64, [65])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}P{pg}")

    suff = ""
    if ftz: suff += ".FTZ"
    if nan: suff += ".NAN"
    if xors: suff += ".XORSIGN"

    # Pp predicate output
    if pp == 7:
        pp_str = "!" if pp_not else ""
        pp_str += "PT"
    else:
        pp_str = f"P{pp}"
        if pp_not:
            pp_str = f"!{pp_str}"

    if isa:
        pu = extract(lo64, hi64, [68, 67, 66])
        pu_str = f"P{pu}"
    else:
        pu_str = None

    if variant == "RRR_RRR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        rb_neg = extract(lo64, hi64, [63])
        rb_abs = extract(lo64, hi64, [62])
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = reg_s(rb, rb_neg, rb_abs)
        operands = f"{rd_s}, {ra_s}, {rb_s}"

    elif variant == "RIR_RIR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        sb_imm = extract(lo64, hi64, list(range(63, 31, -1)))
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        sb_f32 = struct.unpack('>f', struct.pack('>I', sb_imm))[0]
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = f"{sb_f32:g}"
        operands = f"{rd_s}, {ra_s}, {rb_s}"

    elif variant == "RUR_RUR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        urb = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])
        ra_neg = extract(lo64, hi64, [72])
        ra_abs = extract(lo64, hi64, [73])
        urb_neg = extract(lo64, hi64, [63])
        urb_abs = extract(lo64, hi64, [62])
        rd_s = reg_s(rd, 0, 0)
        ra_s = reg_s(ra, ra_neg, ra_abs)
        rb_s = ur_s(urb, urb_neg, urb_abs)
        operands = f"{rd_s}, {ra_s}, {rb_s}"

    else:
        return f"{mnem} ({variant}) — NYI"

    if pu_str:
        parts.append(f"{mnem}{suff} {pu_str}, {operands}, {pp_str};")
    else:
        parts.append(f"{mnem}{suff} {operands}, {pp_str};")
    return f"({variant}) {' '.join(parts)}"


TESTS = [
    # kernel: fmaxf → FMNMX !PT (max)
    ("0x0000000504057209", "0x001fc60007800000", "FMNMX R5, R4, R5, !PT"),
    # kernel: fminf → FMNMX PT (min)
    ("0x0000000504057209", "0x001fc60003800000", "FMNMX R5, R4, R5, PT"),
    # kernel: max.ftz.f32 → FMNMX.FTZ !PT
    ("0x0000000504057209", "0x001fc60007810000", "FMNMX.FTZ R5, R4, R5, !PT"),
    # kernel: max.NaN.f32 → FMNMX.NAN !PT
    ("0x0000000504057209", "0x001fc60007820000", "FMNMX.NAN R5, R4, R5, !PT"),
    # kernel: fmaxf(a, 255.0f) → FMNMX RIR imm=255
    ("0x437f000005057809", "0x001fc60007800000", "FMNMX R5, R5, 255, !PT"),
    # kernel: fminf(a, 0.0f) → FMNMX RUR RZ
    ("0x00000006ff057c09", "0x000fe2000b800000", "FMNMX R5, RZ, UR6, PT"),
    # cublas: @!P6 max with imm=255
    ("0x437f00000000e809", "0x000fc80003800000", "@!P6 FMNMX R0, R0, 255, PT"),
    # cublas: @!P6 min with RZ
    ("0x00000000ff00e209", "0x000fc80007800000", "@!P6 FMNMX R0, RZ, R0, !PT"),
    # cublas: @!P6 max with imm=255, different register
    ("0x437f00000606d809", "0x000fe20003800000", "@!P5 FMNMX R6, R6, 255, PT"),
    # cublas: @!P5 min with RZ
    ("0x00000006ff06d209", "0x000fe40007800000", "@!P5 FMNMX R6, RZ, R6, !PT"),
]

print("=" * 75)
print("FMNMX Decoder — verification against cuobjdump disassembly")
print("=" * 75)

ok = 0
for lo_str, hi_str, expected in TESTS:
    lo = int(lo_str, 16)
    hi = int(hi_str, 16)
    result = decode_fmnmx(lo, hi)
    if result is None:
        print(f"\nFAIL: UNKNOWN {lo_str}/{hi_str} (opc={hex(get_opcode(lo,hi))})")
        continue
    match = "(match)" if expected in result else "(MISMATCH)"
    if expected in result:
        ok += 1
    print(f"\n  cuobjdump: {expected}")
    print(f"  decoded:   {result} {match}")

print(f"\n{'='*75}")
print(f"{ok}/{len(TESTS)} matches")
