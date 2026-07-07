#!/usr/bin/env python3
"""FLO/BREV/UBREV/BMSK decoders — bit-manipulation instructions."""
from typing import Optional

def extract(lo, hi, bits):
    val = 0
    for bit in bits:
        bv = ((hi >> (bit - 64)) if bit >= 64 else (lo >> bit)) & 1
        val = (val << 1) | bv
    return val

def get_opcode(lo, hi):
    return extract(lo, hi, [91] + list(range(11, -1, -1)))

FLO_NAMES = {0: "U32", 1: "S32"}

def decode_flo(lo: int, hi: int) -> Optional[str]:
    opc = get_opcode(lo, hi)
    if opc not in (0x300, 0x1b00, 0xb00, 0x1d00, 0x900):
        return None
    pg = extract(lo, hi, [14,13,12]); pg_not = extract(lo, hi, [15])
    rd = extract(lo, hi, [23,22,21,20,19,18,17,16])
    rb = extract(lo, hi, [39,38,37,36,35,34,33,32])
    fmt = extract(lo, hi, [79,78])
    parts = []
    if pg != 7: parts.append(f"@{'!' if pg_not else ''}P{pg}")
    parts.append(f"FLO.{FLO_NAMES.get(fmt, str(fmt))}")
    parts.append(f"R{rd}," if rd != 0xff else "RZ,")
    parts.append(f"R{rb}" if rb != 0xff else "RZ")
    return " ".join(parts)

def decode_brev(lo: int, hi: int) -> Optional[str]:
    opc = get_opcode(lo, hi)
    if opc not in (0x301, 0x1b01, 0xb01, 0x1d01, 0x901):
        return None
    pg = extract(lo, hi, [14,13,12]); pg_not = extract(lo, hi, [15])
    rd = extract(lo, hi, [23,22,21,20,19,18,17,16])
    rb = extract(lo, hi, [39,38,37,36,35,34,33,32])
    parts = []
    if pg != 7: parts.append(f"@{'!' if pg_not else ''}P{pg}")
    parts.append("BREV")
    parts.append(f"R{rd}," if rd != 0xff else "RZ,")
    parts.append(f"R{rb}" if rb != 0xff else "RZ")
    return " ".join(parts)

def decode_ubrev(lo: int, hi: int) -> Optional[str]:
    opc = get_opcode(lo, hi)
    if opc not in (0x12be, 0x18be):
        return None
    urd = extract(lo, hi, [21,20,19,18,17,16])
    urb = extract(lo, hi, [37,36,35,34,33,32])
    upg = extract(lo, hi, [14,13,12])
    pg_not = extract(lo, hi, [15])
    parts = []
    if upg != 7: parts.append(f"@{'!' if pg_not else ''}UP{upg}")
    parts.append("UBREV")
    parts.append(f"UR{urd}," if urd != 0x3f else "URZ,")
    parts.append(f"UR{urb}" if urb != 0x3f else "URZ")
    return " ".join(parts)

def decode_bmsk(lo: int, hi: int) -> Optional[str]:
    opc = get_opcode(lo, hi)
    if opc not in (0x21b, 0x1a1b, 0xa1b, 0x1c1b, 0x81b):
        return None
    pg = extract(lo, hi, [14,13,12]); pg_not = extract(lo, hi, [15])
    rd = extract(lo, hi, [23,22,21,20,19,18,17,16])
    ra = extract(lo, hi, [31,30,29,28,27,26,25,24])
    rb = extract(lo, hi, [39,38,37,36,35,34,33,32])
    cw = extract(lo, hi, [75])
    parts = []
    if pg != 7: parts.append(f"@{'!' if pg_not else ''}P{pg}")
    mnem = "BMSK"
    if cw == 1: mnem += ".W"
    parts.append(mnem)
    parts.append(f"R{rd}," if rd != 0xff else "RZ,")
    parts.append(f"R{ra}," if ra != 0xff else "RZ,")
    parts.append(f"R{rb}" if rb != 0xff else "RZ")
    return " ".join(parts)

if __name__ == "__main__":
    tests = [
        ("FLO", decode_flo, [(0x0000000200077300, 0, "FLO.U32 R7, R2")]),
        ("BREV", decode_brev, [(0x0000000200097301, 0, "BREV R9, R2")]),
        ("UBREV", decode_ubrev, [(0x00000008000872be, 0x000fe40008000000, "UBREV UR8, UR8")]),
        ("BMSK", decode_bmsk, [(0x000000060d06721b, 0, "BMSK R6, R13, R6")]),
    ]
    for name, fn, vecs in tests:
        for lo, hi, exp in vecs:
            r = fn(lo, hi)
            ok = "OK" if r == exp else "MISMATCH"
            print(f"{name}: {r}  [{ok}]" + (f"  expected: {exp}" if ok != "OK" else ""))
    print("\nALL PASS" if all(fn(lo,hi)==exp for _,fn,vecs in tests for lo,hi,exp in vecs) else "SOME FAILED")
