#!/usr/bin/env python3
"""IMNMX decoder — legacy integer min/max (sm_75 and earlier)."""

import struct
from typing import Optional

OPCODES = {
    0x217:  ("IMNMX", "RRR_RRR"),
    0x817:  ("IMNMX", "RIR_RsIR"),
    0xa17:  ("IMNMX", "RCR_RCR"),
    0x1a17: ("IMNMX", "RCxR_RCxR"),
    0x1c17: ("IMNMX", "RUR_RUR"),
}

FMT_NAMES = {0: "U32", 1: "S32"}

def extract(lo64: int, hi64: int, bits: list[int]) -> int:
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val

def get_opcode(lo64: int, hi64: int) -> int:
    return extract(lo64, hi64, [91, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0])

def reg_s(r: int) -> str:
    return f"R{r}" if r != 0xff else "RZ"

def decode_imnmx(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES:
        return None
    mnem, variant = OPCODES[opc]

    pg     = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rd     = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    pp     = extract(lo64, hi64, [89, 88, 87])
    pp_not = extract(lo64, hi64, [90])
    fmt    = extract(lo64, hi64, [73])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}P{pg}")

    suffix = FMT_NAMES.get(fmt, "?")
    if suffix == "S32":
        suff = ""
    else:
        suff = f".{suffix}"

    if pp == 7:
        pp_str = "!" if pp_not else ""
        pp_str += "PT"
    else:
        pp_str = f"P{pp}"
        if pp_not:
            pp_str = f"!{pp_str}"

    if variant == "RRR_RRR":
        ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
        rb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
        operands = f"{reg_s(rd)}, {reg_s(ra)}, {reg_s(rb)}"

    elif variant == "RIR_RsIR":
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


if __name__ == "__main__":
    TESTS = [
        ("0x0000000300007217", "0x004fca0003800200", "IMNMX R0, R0, R3, PT"),
        ("0x0000000300007217", "0x004fca0003800000", "IMNMX.U32 R0, R0, R3, PT"),
        ("0x0000000300007217", "0x004fca0007800200", "IMNMX R0, R0, R3, !PT"),
        ("0x0000000300007217", "0x004fca0007800000", "IMNMX.U32 R0, R0, R3, !PT"),
    ]
    ok = 0
    for lo_s, hi_s, exp in TESTS:
        r = decode_imnmx(int(lo_s, 16), int(hi_s, 16))
        m = "(match)" if r and exp in r else "(MISMATCH)"
        if r and exp in r: ok += 1
        print(f"  cuobjdump: {exp}")
        print(f"  decoded:   {r} {m}\n")
    print(f"{ok}/{len(TESTS)} matches")
