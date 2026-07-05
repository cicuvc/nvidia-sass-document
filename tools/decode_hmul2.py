#!/usr/bin/env python3
"""Decoder for HMUL2 (packed FP16x2 multiply)."""

import sys

ISWZA = {0: "H1_H0", 2: "H0_H0", 3: "H1_H1"}

def get_bit(hi: int, lo: int, pos: int) -> int:
    if pos >= 64:
        return (hi >> (pos - 64)) & 1
    return (lo >> pos) & 1

def extract(hi: int, lo: int, msb: int, lsb: int) -> int:
    val = 0
    for b in range(msb, lsb - 1, -1):
        val = (val << 1) | get_bit(hi, lo, b)
    return val

def reg_name(r: int) -> str:
    return "RZ" if r == 255 else f"R{r}"

def pred_str(pg: int, pg_not: int) -> str:
    if pg == 7:
        return ""
    return f"@P{pg}" if not pg_not else f"@!P{pg}"

def iswz_suffix(v: int) -> str:
    if v == 0:
        return ""
    s = ISWZA.get(v, f"INVALID({v})")
    return f".{s}"

def fmt_operand(reg: int, negate: int, absolute: int, iswz: int) -> str:
    a = "|" if absolute else ""
    n = "-" if negate else ""
    sw = iswz_suffix(iswz)
    return f"{a}{n}{reg_name(reg)}{sw}"

def decode_hmul2_rr(hi: int, lo: int) -> str:
    rd = extract(hi, lo, 23, 16)
    ra = extract(hi, lo, 31, 24)
    rb = extract(hi, lo, 39, 32)
    pg = extract(hi, lo, 14, 12)
    pg_not = get_bit(hi, lo, 15)

    ra_str = fmt_operand(ra, get_bit(hi, lo, 72), get_bit(hi, lo, 73),
                         extract(hi, lo, 75, 74))
    rb_str = fmt_operand(rb, get_bit(hi, lo, 63), get_bit(hi, lo, 62),
                         extract(hi, lo, 61, 60))

    sat = get_bit(hi, lo, 77)
    fmz = (get_bit(hi, lo, 80) << 1) | get_bit(hi, lo, 76)

    mods = "HMUL2"
    if fmz == 1:
        mods += ".FMZ"
    elif fmz == 2:
        mods += ".FTZ"
    if sat:
        mods += ".SAT"

    pre = f"{pred_str(pg, pg_not)} " if pred_str(pg, pg_not) else ""
    return f"{pre}{mods} {reg_name(rd)}, {ra_str}, {rb_str}"

def decode(hi: int, lo: int) -> str:
    opcode = (get_bit(hi, lo, 91) << 12) | extract(hi, lo, 11, 0)
    if opcode == 0x232:
        return decode_hmul2_rr(hi, lo)
    else:
        return f"UNKNOWN opcode 0x{opcode:04x} ({opcode})"

test_vectors = [
    # cublas HMUL2 with H0_H0 broadcasts
    (0x004fc80000000800, 0x2000000704047232, "HMUL2 R4, R4.H0_H0, R7.H0_H0"),
    (0x004fc80000000800, 0x200000090e097232, "HMUL2 R9, R14.H0_H0, R9.H0_H0"),
    (0x004fc80000000800, 0x2000000a050a7232, "HMUL2 R10, R5.H0_H0, R10.H0_H0"),
    # cublas with predicate
    (0x000fe40000000800, 0x2000000805008232, "@!P0 HMUL2 R0, R5.H0_H0, R8.H0_H0"),
    (0x000fe20000000800, 0x2000001211008232, "@!P0 HMUL2 R0, R17.H0_H0, R18.H0_H0"),
    (0x000fe20000000800, 0x2000001407008232, "@!P0 HMUL2 R0, R7.H0_H0, R20.H0_H0"),
]

def run_tests():
    passed = 0
    failed = 0
    for hi, lo, expected in test_vectors:
        result = decode(hi, lo)
        if result == expected:
            passed += 1
        else:
            failed += 1
            print(f"  FAIL: got      {result}")
            print(f"        expected  {expected}")
    if passed:
        print(f"  ... ({passed} more passed)")
    print(f"\n  {passed} passed, {failed} failed")

if __name__ == '__main__':
    if len(sys.argv) == 3:
        hi = int(sys.argv[1], 16)
        lo = int(sys.argv[2], 16)
        print(decode(hi, lo))
    elif len(sys.argv) == 2 and sys.argv[1] == 'test':
        run_tests()
    else:
        run_tests()
