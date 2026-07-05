#!/usr/bin/env python3
"""Decoder for HSET2 / HSETP2 (packed FP16x2 compare)."""

import sys

ISWZA = {0: "H1_H0", 2: "H0_H0", 3: "H1_H1"}
FCMP_MAP = {
    0: "F", 1: "LT", 2: "EQ", 3: "LE", 4: "GT", 5: "NE", 6: "GE",
    7: "NUM", 8: "NAN", 9: "LTU", 10: "EQU", 11: "LEU", 12: "GTU",
    13: "NEU", 14: "GEU", 15: "T",
}
BVAL_MAP = {0: "BM", 1: "BF"}
BOP_MAP = {0: "AND", 1: "OR", 2: "XOR"}
H_AND_MAP = {0: "", 1: ".H_AND"}

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


def decode_hset2_rr(hi: int, lo: int) -> str:
    rd = extract(hi, lo, 23, 16)
    ra = extract(hi, lo, 31, 24)
    rc = extract(hi, lo, 39, 32)
    pg = extract(hi, lo, 14, 12)
    pg_not = get_bit(hi, lo, 15)

    cmp = extract(hi, lo, 79, 76)       # FCMP
    bval = get_bit(hi, lo, 71)          # BVal: 0=BM, 1=BF
    bop = extract(hi, lo, 70, 69)       # Bop: AND/OR/XOR
    ftz = get_bit(hi, lo, 80)           # FTZ
    iswza = extract(hi, lo, 75, 74)
    iswzb = extract(hi, lo, 61, 60)
    pp = extract(hi, lo, 89, 87)        # output predicate
    pp_not = get_bit(hi, lo, 90)

    ra_str = fmt_operand(ra, get_bit(hi, lo, 72), get_bit(hi, lo, 73), iswza)
    rc_str = fmt_operand(rc, get_bit(hi, lo, 63), get_bit(hi, lo, 62), iswzb)

    parts = []
    pre = pred_str(pg, pg_not)
    if pre:
        parts.append(pre)

    mnem = "HSET2"
    bval_str = BVAL_MAP.get(bval, f"?({bval})")
    cmp_str = FCMP_MAP.get(cmp, f"?({cmp})")
    bop_str = BOP_MAP.get(bop, f"?({bop})")
    mods = f"{bval_str}.{cmp_str}.{bop_str}" if bval == 1 else f"{cmp_str}.{bop_str}"
    if ftz:
        mods += ".FTZ"
    parts.append(f"{mnem}.{mods}")

    m = " ".join(parts)
    pp_str = "PT" if pp == 7 else f"P{pp}"
    if pp_not:
        pp_str = f"!{pp_str}"

    return f"{m} {reg_name(rd)}, {ra_str}, {rc_str}, {pp_str}"


def decode_hsetp2_rr(hi: int, lo: int) -> str:
    ra = extract(hi, lo, 31, 24)
    rc = extract(hi, lo, 39, 32)
    pg = extract(hi, lo, 14, 12)
    pg_not = get_bit(hi, lo, 15)

    cmp = extract(hi, lo, 79, 76)
    bop = extract(hi, lo, 70, 69)
    ftz = get_bit(hi, lo, 80)
    h_and = get_bit(hi, lo, 71)          # H_AND
    iswza = extract(hi, lo, 75, 74)
    iswzb = extract(hi, lo, 61, 60)
    pu = extract(hi, lo, 83, 81)          # output predicate Pu
    pv = extract(hi, lo, 86, 84)          # output predicate Pv (writes Pv and Pv+1)
    pp = extract(hi, lo, 89, 87)
    pp_not = get_bit(hi, lo, 90)

    ra_str = fmt_operand(ra, get_bit(hi, lo, 72), get_bit(hi, lo, 73), iswza)
    rc_str = fmt_operand(rc, get_bit(hi, lo, 63), get_bit(hi, lo, 62), iswzb)

    parts = []
    pre = pred_str(pg, pg_not)
    if pre:
        parts.append(pre)

    parts.append("HSETP2")
    cmp_str = FCMP_MAP.get(cmp, f"?({cmp})")
    parts.append(f".{cmp_str}")

    bop_str = BOP_MAP.get(bop, f"?({bop})")
    if bop != 0:
        parts.append(f".{bop_str}")

    if h_and:
        parts.append(".H_AND")
    if ftz:
        parts.append(".FTZ")

    m = " ".join(parts)
    pp_str = "PT" if pp == 7 else f"P{pp}"
    if pp_not:
        pp_str = f"!{pp_str}"

    pu_str = "PT" if pu == 7 else f"P{pu}"
    pv_str = "PT" if pv == 7 else f"P{pv}"

    return f"{m} {pu_str}|{pv_str}, {ra_str}, {rc_str}, {pp_str}"


def decode(hi: int, lo: int) -> str:
    opcode = (get_bit(hi, lo, 91) << 12) | extract(hi, lo, 11, 0)
    if opcode in (0x233,):
        return decode_hset2_rr(hi, lo)
    elif opcode in (0x234,):
        return decode_hsetp2_rr(hi, lo)
    else:
        return f"UNKNOWN opcode 0x{opcode:04x} ({opcode})"


test_vectors = [
    # HSET2 from test kernel
    (0x001fca0003801080, 0x0000000504057233, "HSET2.BF.LT.AND R5, R4, R5, PT"),
    (0x001fca0003802080, 0x0000000504057233, "HSET2.BF.EQ.AND R5, R4, R5, PT"),
    (0x001fca0003803080, 0x0000000504057233, "HSET2.BF.LE.AND R5, R4, R5, PT"),
    (0x001fca0003804080, 0x0000000504057233, "HSET2.BF.GT.AND R5, R4, R5, PT"),
    (0x001fca0003805080, 0x0000000504057233, "HSET2.BF.NE.AND R5, R4, R5, PT"),
    (0x001fca0003806080, 0x0000000504057233, "HSET2.BF.GE.AND R5, R4, R5, PT"),
    # HSET2 with different Rd
    (0x001fca0003801080, 0x0000000504007233, "HSET2.BF.LT.AND R0, R4, R5, PT"),
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
