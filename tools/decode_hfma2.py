#!/usr/bin/env python3
"""Decoder for HFMA2 / HFMA2.MMA (packed FP16x2 fused multiply-add)."""

import sys

# ── Enums ────────────────────────────────────────────────────────────────────

ISWZA = {0: "H1_H0", 2: "H0_H0", 3: "H1_H1"}
ISWZB = {0: "H1_H0", 1: "F32", 2: "H0_H0", 3: "H1_H1", 4: "H0_NH1"}

# ── Bit utilities ────────────────────────────────────────────────────────────

def get_bit(hi: int, lo: int, pos: int) -> int:
    if pos >= 64:
        return (hi >> (pos - 64)) & 1
    return (lo >> pos) & 1

def extract(hi: int, lo: int, msb: int, lsb: int) -> int:
    val = 0
    for b in range(msb, lsb - 1, -1):
        val = (val << 1) | get_bit(hi, lo, b)
    return val


# ── Helpers ──────────────────────────────────────────────────────────────────

def reg_name(r: int) -> str:
    return "RZ" if r == 255 else f"R{r}"

def pred_str(pg: int, pg_not: int) -> str:
    if pg == 7:
        return ""
    return f"@P{pg}" if not pg_not else f"@!P{pg}"

def iswz_suffix(v: int, kind: str = "A") -> str:
    if v == 0:
        return ""
    d = ISWZB if kind == "B" else ISWZA
    s = d.get(v, f"INVALID({v})")
    return f".{s}"

def fp16_str(v: int) -> str:
    sign = (v >> 15) & 1
    exp = (v >> 10) & 0x1F
    mant = v & 0x3FF
    if exp == 0:
        val = mant / 1024.0 * 2**-14
    else:
        val = (1 + mant / 1024.0) * 2**(exp - 15)
    val = -val if sign else val
    if v == 0:
        return "0"
    if val == int(val):
        return str(int(val))
    return f"{val:.1f}".rstrip('0').rstrip('.')


def fmt_operand(reg: int, negate: int, absolute: int, iswz_val: int = 0, iswz_kind: str = "A") -> str:
    """Format a source operand: |abs|-neg Rxx.ISWZ"""
    a = "|" if absolute else ""
    n = "-" if negate else ""
    sw = iswz_suffix(iswz_val, iswz_kind)
    return f"{a}{n}{reg_name(reg)}{sw}"


# ── Decoders ─────────────────────────────────────────────────────────────────

def decode_hfma2_rrr(hi: int, lo: int) -> str:
    pg = extract(hi, lo, 14, 12)
    pg_not = get_bit(hi, lo, 15)
    rd = extract(hi, lo, 23, 16)
    ra = extract(hi, lo, 31, 24)
    rb = extract(hi, lo, 39, 32)
    rc = extract(hi, lo, 71, 64)

    ra_str = fmt_operand(ra, get_bit(hi, lo, 72), get_bit(hi, lo, 73),
                         extract(hi, lo, 75, 74), "A")
    rb_str = fmt_operand(rb, get_bit(hi, lo, 63), get_bit(hi, lo, 62),
                         (get_bit(hi, lo, 86) << 2) | extract(hi, lo, 61, 60), "B")
    rc_str = fmt_operand(rc, get_bit(hi, lo, 84), get_bit(hi, lo, 83),
                         extract(hi, lo, 82, 81), "A")

    sat = (get_bit(hi, lo, 79) << 1) | get_bit(hi, lo, 77)
    fmz = (get_bit(hi, lo, 80) << 1) | get_bit(hi, lo, 76)

    mods = f"HFMA2"
    if sat == 1:
        mods += ".SAT"
    elif sat == 2:
        mods += ".RELU"
    if fmz == 1:
        mods += ".FMZ"
    elif fmz == 2:
        mods += ".FTZ"

    pre = f"{pred_str(pg, pg_not)} " if pred_str(pg, pg_not) else ""
    return f"{pre}{mods} {reg_name(rd)}, {ra_str}, {rb_str}, {rc_str}"


def decode_hfma2_mma_rrr(hi: int, lo: int) -> str:
    pg = extract(hi, lo, 14, 12)
    pg_not = get_bit(hi, lo, 15)
    rd = extract(hi, lo, 23, 16)
    ra = extract(hi, lo, 31, 24)
    rb = extract(hi, lo, 39, 32)
    rc = extract(hi, lo, 71, 64)

    ra_str = fmt_operand(ra, get_bit(hi, lo, 72), get_bit(hi, lo, 73))
    rb_str = fmt_operand(rb, get_bit(hi, lo, 63), get_bit(hi, lo, 62))
    rc_str = fmt_operand(rc, get_bit(hi, lo, 84), get_bit(hi, lo, 83))

    sat = (get_bit(hi, lo, 79) << 1) | get_bit(hi, lo, 77)
    fmz = (get_bit(hi, lo, 80) << 1) | get_bit(hi, lo, 76)

    mods = f"HFMA2.MMA"
    if sat == 1:
        mods += ".SAT"
    elif sat == 2:
        mods += ".RELU"
    if fmz == 1:
        mods += ".FMZ"
    elif fmz == 2:
        mods += ".FTZ"

    pre = f"{pred_str(pg, pg_not)} " if pred_str(pg, pg_not) else ""
    return f"{pre}{mods} {reg_name(rd)}, {ra_str}, {rb_str}, {rc_str}"


def decode_hfma2_mma_rri(hi: int, lo: int) -> str:
    """RRI: Rd, Ra, Rb, immH, immL (no Rc)"""
    pg = extract(hi, lo, 14, 12)
    pg_not = get_bit(hi, lo, 15)
    rd = extract(hi, lo, 23, 16)
    ra = extract(hi, lo, 31, 24)
    rb = extract(hi, lo, 71, 64)
    sc = extract(hi, lo, 63, 48)
    sb = extract(hi, lo, 47, 32)

    ra_str = fmt_operand(ra, get_bit(hi, lo, 72), get_bit(hi, lo, 73))
    rb_str = fmt_operand(rb, get_bit(hi, lo, 84), get_bit(hi, lo, 83))

    sat = (get_bit(hi, lo, 79) << 1) | get_bit(hi, lo, 77)
    fmz = (get_bit(hi, lo, 80) << 1) | get_bit(hi, lo, 76)

    mods = f"HFMA2.MMA"
    if fmz == 1:
        mods += ".FMZ"
    elif fmz == 2:
        mods += ".FTZ"
    if sat == 1:
        mods += ".SAT"

    pre = f"{pred_str(pg, pg_not)} " if pred_str(pg, pg_not) else ""
    return f"{pre}{mods} {reg_name(rd)}, {ra_str}, {rb_str}, {fp16_str(sc)}, {fp16_str(sb)}"


def decode_hfma2_mma_rir(hi: int, lo: int) -> str:
    """RIR: Rd, Ra, immH, immL, Rc"""
    pg = extract(hi, lo, 14, 12)
    pg_not = get_bit(hi, lo, 15)
    rd = extract(hi, lo, 23, 16)
    ra = extract(hi, lo, 31, 24)
    rc = extract(hi, lo, 71, 64)
    sc = extract(hi, lo, 63, 48)
    sb = extract(hi, lo, 47, 32)

    ra_str = fmt_operand(ra, get_bit(hi, lo, 72), get_bit(hi, lo, 73))
    rc_str = fmt_operand(rc, get_bit(hi, lo, 84), get_bit(hi, lo, 83))

    sat = (get_bit(hi, lo, 79) << 1) | get_bit(hi, lo, 77)
    fmz = (get_bit(hi, lo, 80) << 1) | get_bit(hi, lo, 76)

    mods = f"HFMA2.MMA"
    if fmz == 1:
        mods += ".FMZ"
    elif fmz == 2:
        mods += ".FTZ"
    if sat == 1:
        mods += ".SAT"

    pre = f"{pred_str(pg, pg_not)} " if pred_str(pg, pg_not) else ""
    return f"{pre}{mods} {reg_name(rd)}, {ra_str}, {fp16_str(sc)}, {fp16_str(sb)}, {rc_str}"


# ── Dispatcher ───────────────────────────────────────────────────────────────

def decode(hi: int, lo: int) -> str:
    opcode = (get_bit(hi, lo, 91) << 12) | extract(hi, lo, 11, 0)
    if opcode == 0x231:
        return decode_hfma2_rrr(hi, lo)
    elif opcode == 0x235:
        return decode_hfma2_mma_rrr(hi, lo)
    elif opcode == 0x435:
        return decode_hfma2_mma_rri(hi, lo)
    elif opcode == 0x835:
        return decode_hfma2_mma_rir(hi, lo)
    else:
        ofmt = (get_bit(hi, lo, 85) << 1) | get_bit(hi, lo, 78)
        return f"UNKNOWN opcode 0x{opcode:04x} ({opcode})"


# ── Test vectors ─────────────────────────────────────────────────────────────

test_vectors = [
    # HFMA2.MMA RRI from cublas: R32, -RZ, RZ, 0, 0
    (0x000fe200000001ff, 0x00000000ff207435, "HFMA2.MMA R32, -RZ, RZ, 0, 0"),
    (0x000fe200000001ff, 0x00000000ff0f7435, "HFMA2.MMA R15, -RZ, RZ, 0, 0"),
    (0x000fe200000001ff, 0x00000000ff077435, "HFMA2.MMA R7, -RZ, RZ, 0, 0"),
    (0x000fe200000001ff, 0x00000000ff027435, "HFMA2.MMA R2, -RZ, RZ, 0, 0"),
    (0x000fe200000001ff, 0x00000000ff0c7435, "HFMA2.MMA R12, -RZ, RZ, 0, 0"),
    (0x000fe200000001ff, 0x00000000ff267435, "HFMA2.MMA R38, -RZ, RZ, 0, 0"),
    (0x000fd800000001ff, 0x00000000ff0c7435, "HFMA2.MMA R12, -RZ, RZ, 0, 0"),
    (0x000fe200000001ff, 0x00000000ff1f7435, "HFMA2.MMA R31, -RZ, RZ, 0, 0"),
    (0x000fe200000001ff, 0x00000000ff037435, "HFMA2.MMA R3, -RZ, RZ, 0, 0"),
    # HFMA2.MMA RIR from test kernel: Rd, Ra, 1, 1, Rc
    (0x001fce0000000005, 0x3c003c0004057835, "HFMA2.MMA R5, R4, 1, 1, R5"),
    (0x001fce0000002005, 0x3c003c0004057835, "HFMA2.MMA.SAT R5, R4, 1, 1, R5"),
    (0x001fce0000010005, 0x3c003c0004057835, "HFMA2.MMA.FTZ R5, R4, 1, 1, R5"),
    (0x001fce0000012005, 0x3c003c0004057835, "HFMA2.MMA.FTZ.SAT R5, R4, 1, 1, R5"),
    (0x001fce0000000105, 0x3c003c0004057835, "HFMA2.MMA R5, -R4, 1, 1, R5"),
    (0x001fce0000100005, 0x3c003c0004057835, "HFMA2.MMA R5, R4, 1, 1, -R5"),
    (0x001fce0000100105, 0x3c003c0004057835, "HFMA2.MMA R5, -R4, 1, 1, -R5"),
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
