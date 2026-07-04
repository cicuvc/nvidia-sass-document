#!/usr/bin/env python3
"""MUFU decoder — Multi-Function Unit: Rd = Op(Rb)."""

from typing import Optional

MUFUOP_NAMES = {
    0:"COS", 1:"SIN", 2:"EX2", 3:"LG2", 4:"RCP",
    5:"RSQ", 6:"RCP64H", 7:"RSQ64H", 8:"SQRT", 9:"TANH",
    10:"INVALID10",11:"INVALID11",12:"INVALID12",13:"INVALID13",14:"INVALID14",15:"INVALID15",
}

OPCODES = {
    0x308:  ("MUFU", "RRR_RR"),
    0x908:  ("MUFU", "RIR_RI"),
    0xb08:  ("MUFU", "RCR_RC"),
    0x1b08: ("MUFU", "RCxR_RCx"),
    0x1d08: ("MUFU", "RUR_RU"),
}

def extract(lo64, hi64, bits):
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val
def get_opcode(lo64, hi64):
    return extract(lo64, hi64, [91,11,10,9,8,7,6,5,4,3,2,1,0])

def decode_mufu(lo64, hi64):
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES: return None
    mnem, variant = OPCODES[opc]

    pg = extract(lo64, hi64, [14,13,12]); pg_not = extract(lo64, hi64, [15])
    rd = extract(lo64, hi64, [23,22,21,20,19,18,17,16])
    mufuop = extract(lo64, hi64, [77,76,75,74])

    parts = []
    if pg != 7: parts.append(f"@{'!' if pg_not else ''}P{pg}")
    op_name = MUFUOP_NAMES.get(mufuop, f"?{mufuop}")

    if variant == "RRR_RR":
        rb = extract(lo64, hi64, [39,38,37,36,35,34,33,32])
        rb_neg = extract(lo64, hi64, [63]); rb_abs = extract(lo64, hi64, [62])
        rd_s = f"RZ" if rd==0xff else f"R{rd}"
        rb_s = f"RZ" if rb==0xff else f"R{rb}"
        if rb_neg: rb_s = f"-{rb_s}"
        elif rb_abs: rb_s = f"|{rb_s}|"
    elif variant == "RUR_RU":
        urb = extract(lo64, hi64, [37,36,35,34,33,32])
        rb_neg = extract(lo64, hi64, [63]); rb_abs = extract(lo64, hi64, [62])
        rd_s = f"RZ" if rd==0xff else f"R{rd}"
        rb_s = f"URZ" if urb==0x3f else f"UR{urb}"
        if rb_neg: rb_s = f"-{rb_s}"
        elif rb_abs: rb_s = f"|{rb_s}|"
    elif variant == "RIR_RI":
        sb_imm = extract(lo64, hi64, list(range(63, 31, -1)))
        import struct
        sb_f32 = struct.unpack('>f', struct.pack('>I', sb_imm))[0]
        rd_s = f"RZ" if rd==0xff else f"R{rd}"
        rb_s = f"{sb_f32:g}"
    else:
        return f"{mnem} ({variant}) — NYI"

    parts.append(f"{mnem}.{op_name} {rd_s}, {rb_s};")
    return f"({variant}) {' '.join(parts)}"

TESTS = [
    ("0x0000000500057308", "0x000e240000000000", "MUFU.COS"),
    ("0x0000000500057308", "0x000e240000000400", "MUFU.SIN"),
    ("0x0000000000057308", "0x000e240000000800", "MUFU.EX2"),
    ("0x0000000600057d08", "0x000e240008000800", "MUFU.EX2 R5, UR6"),
    ("0x0000000600057d08", "0x000e240008000c00", "MUFU.LG2 R5, UR6"),
    ("0x0000000600057d08", "0x000e240008001000", "MUFU.RCP R5, UR6"),
    ("0x0000000600057d08", "0x000e240008001400", "MUFU.RSQ R5, UR6"),
    ("0x0000000600057d08", "0x000e240008002000", "MUFU.SQRT R5, UR6"),
    ("0x0000000600057d08", "0x000e240008002400", "MUFU.TANH R5, UR6"),
    # cublas
    ("0x0000000300057308", "0x001e240000001800", "MUFU.RCP64H"),
    ("0x0000000f00097308", "0x000e620000001c00", "MUFU.RSQ64H"),
]

ok = 0
for lo_s, hi_s, exp in TESTS:
    r = decode_mufu(int(lo_s,16), int(hi_s,16))
    m = "(match)" if r and exp in r else "(MISMATCH)"
    if r and exp in r: ok += 1
    print(f"  expected: {exp}")
    print(f"  decoded:  {r} {m}\n")
print(f"{ok}/{len(TESTS)} matches")
