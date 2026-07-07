#!/usr/bin/env python3
"""DMUL decoder — FP64 multiply, 5 variants (RUR_RU observed)."""
from typing import Optional

RND = {0: "RN", 1: "RM", 2: "RP", 3: "RZ"}

def extract(lo, hi, bits):
    val = 0
    for bit in bits:
        bv = ((hi >> (bit - 64)) if bit >= 64 else (lo >> bit)) & 1
        val = (val << 1) | bv
    return val

def get_opcode(lo, hi):
    return extract(lo, hi, [91] + list(range(11, -1, -1)))

OPCODES = {0x228, 0x428, 0x628, 0x828, 0xa28, 0xc28, 0xe28, 0x1628, 0x1a28, 0x1c28, 0x1e28}

def reg_s(r, neg, abs_):
    n = f"R{r}" if r != 0xff else "RZ"
    if neg: return f"-{n}"
    if abs_: return f"|{n}|"
    return n

def decode_dmul(lo, hi):
    opc = get_opcode(lo, hi)
    if opc not in OPCODES: return None

    pg = extract(lo, hi, [14,13,12]); pg_not = extract(lo, hi, [15])
    rd = extract(lo, hi, [23,22,21,20,19,18,17,16])
    ra = extract(lo, hi, [31,30,29,28,27,26,25,24])

    is_rur = (opc in (0xc28, 0x1c28))
    if is_rur:
        urb = extract(lo, hi, [37,36,35,34,33,32])
        rb_s = f"UR{urb}"
    else:
        rb = extract(lo, hi, [39,38,37,36,35,34,33,32])
        rb_s = reg_s(rb, 0, 0)

    rnd = extract(lo, hi, [79,78])

    parts = []; mnem = "DMUL"
    if pg != 7: parts.append(f"@{'!' if pg_not else ''}P{pg}")
    if rnd != 0: mnem += f".{RND[rnd]}"
    parts.append(mnem)
    parts.append(f"{reg_s(rd,0,0)},"); parts.append(reg_s(ra,0,0)+","); parts.append(rb_s)
    return " ".join(parts)

if __name__ == "__main__":
    tests = [
        (0x000000040a027c28, 0x004fea0000000a00, "DMUL R2, R10, UR4"),
        (0x000000040a067c28, 0x000ea20000000a00, "DMUL.RM R6, R10, UR4"),
        (0x000000040a087c28, 0x000ee20000000a00, "DMUL.RP R8, R10, UR4"),
        (0x000000040a0a7c28, 0x000f220000000a00, "DMUL.RZ R10, R10, UR4"),
    ]
    ok = 0
    for lo, hi, exp in tests:
        r = decode_dmul(lo, hi); s = "OK" if r == exp else "MISMATCH"
        if r == exp: ok += 1
        print(f"{r:45s} [{s}]" + (f"  expected: {exp}" if s != "OK" else ""))
    print(f"\n{ok}/{len(tests)} PASS")
