#!/usr/bin/env python3
"""Decoder for HADD2 (FP16x2 packed half-add)."""

import sys
from dataclasses import dataclass

# ── Enums ────────────────────────────────────────────────────────────────────

ISWZA = {0: "H1_H0", 2: "H0_H0", 3: "H1_H1"}
OFMT = {0: "F16_V2", 1: "F32", 2: "BF16_V2"}

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


# ── Encode helpers ───────────────────────────────────────────────────────────

def reg_name(r: int) -> str:
    if r == 255:
        return "RZ"
    return f"R{r}"

def ur_name(r: int) -> str:
    if r == 63:
        return "URZ"
    return f"UR{r}"

def pred_name(pg: int, pg_not: int) -> str:
    if pg == 7:
        return ""
    s = f"P{pg}"
    if pg_not:
        return f"@!{s} "
    return f"@{s} "

def ofmt_suffix(ofmt_val: int) -> str:
    """Return the .F32 / .BF16 / (empty) suffix."""
    if ofmt_val == 1:
        return ".F32"
    if ofmt_val == 2:
        return ".BF16"
    return ""

def iswz_suffix(iswz_val: int) -> str:
    if iswz_val == 0:
        return ""  # H1_H0 is default, omitted
    s = ISWZA.get(iswz_val, f"INVALID({iswz_val})")
    return f".{s}"

def negate_prefix(val: int) -> str:
    return "-" if val else ""


# ── Decoder context ──────────────────────────────────────────────────────────

@dataclass
class Decode:
    hi: int
    lo: int
    opcode: int
    ofmt: int        # [85],[78]: 0=F16_V2, 1=F32, 2=BF16_V2
    ftz: int         # [80]
    sat: int         # [77]
    rd: int
    ra: int
    iswzA: int       # [75:74]
    e: int           # [72]: Ra@negate
    sz: int           # [73]: Ra@absolute
    pg: int
    pg_not: int
    opex: int

    def is_f32(self) -> bool:
        return self.ofmt == 1

    def modifiers(self) -> str:
        parts = []
        if self.ftz:
            parts.append(".FTZ")
        if self.sat:
            parts.append(".SAT")
        return "".join(parts)

    def predicate_str(self) -> str:
        return pred_name(self.pg, self.pg_not)


# ── Source B (C operand) decoders ────────────────────────────────────────────

def decode_rr(d: Decode) -> str:
    """RR variant: register source."""
    hsel = extract(d.hi, d.lo, 61, 60)   # iswzB_as_C
    sb_inv = get_bit(d.hi, d.lo, 63)      # Rc@negate
    sc_abs = get_bit(d.hi, d.lo, 62)      # Rc@absolute
    rc = extract(d.hi, d.lo, 39, 32)

    ra_neg = negate_prefix(d.e)
    ra_abs = "|" + ra_neg if d.sz else ra_neg
    ra_suffix = iswz_suffix(d.iswzA)

    rc_neg = negate_prefix(sb_inv)
    rc_abs = "|" + rc_neg if sc_abs else rc_neg
    rc_suffix = iswz_suffix(hsel)

    return f"{d.predicate_str()}HADD2{ofmt_suffix(d.ofmt)}{d.modifiers()} {reg_name(d.rd)}, {ra_abs}{reg_name(d.ra)}{ra_suffix}, {rc_abs}{reg_name(rc)}{rc_suffix}"


def decode_rc(d: Decode) -> str:
    """RC variant: constant bank source."""
    hsel = extract(d.hi, d.lo, 61, 60)    # iswzB
    sb_inv = get_bit(d.hi, d.lo, 63)       # Sc@negate
    sc_abs = get_bit(d.hi, d.lo, 62)       # Sc@absolute
    sb_bank = extract(d.hi, d.lo, 58, 54)
    sb_offset = extract(d.hi, d.lo, 53, 40)

    ra_neg = negate_prefix(d.e)
    ra_abs = "|" + ra_neg if d.sz else ra_neg
    ra_suffix = iswz_suffix(d.iswzA)

    sc_neg = negate_prefix(sb_inv)
    sc_abs = "|" + sc_neg if sc_abs else sc_neg
    sc_suffix = iswz_suffix(hsel)

    # ConstBankAddress2 maps (bank, addr) to (sb_bank, sb_offset)
    # Reverse: bank=0x19/special mapping... approximate for now
    return f"{d.predicate_str()}HADD2{ofmt_suffix(d.ofmt)}{d.modifiers()} {reg_name(d.rd)}, {ra_abs}{reg_name(d.ra)}{ra_suffix}, c[{sb_bank}][{sb_offset}]{sc_suffix}"


def decode_ri(d: Decode) -> str:
    """RI variant: two FP16 immediates."""
    sc_raw = extract(d.hi, d.lo, 63, 48)
    sb_raw = extract(d.hi, d.lo, 47, 32)

    # Convert FP16 to float for display
    def fp16_to_float(v: int) -> float:
        sign = (v >> 15) & 1
        exp = (v >> 10) & 0x1F
        mant = v & 0x3FF
        if exp == 0:
            val = mant / 1024.0 * 2**-14
        elif exp == 31:
            val = float('inf') if mant == 0 else float('nan')
        else:
            val = (1 + mant / 1024.0) * 2**(exp - 15)
        return -val if sign else val

    sc_f = fp16_to_float(sc_raw)
    sb_f = fp16_to_float(sb_raw)

    ra_neg = negate_prefix(d.e)
    ra_abs = "|" + ra_neg if d.sz else ra_neg
    ra_suffix = iswz_suffix(d.iswzA)

    return f"{d.predicate_str()}HADD2{ofmt_suffix(d.ofmt)}{d.modifiers()} {reg_name(d.rd)}, {ra_abs}{reg_name(d.ra)}{ra_suffix}, {sc_f}, {sb_f}"


def decode_ru(d: Decode) -> str:
    """RU variant: uniform register source."""
    hsel = extract(d.hi, d.lo, 61, 60)    # iswzB_as_C
    sb_inv = get_bit(d.hi, d.lo, 63)       # URc@negate
    sc_abs = get_bit(d.hi, d.lo, 62)       # URc@absolute
    rc_ur = extract(d.hi, d.lo, 37, 32)

    ra_neg = negate_prefix(d.e)
    ra_abs = "|" + ra_neg if d.sz else ra_neg
    ra_suffix = iswz_suffix(d.iswzA)

    rc_neg = negate_prefix(sb_inv)
    rc_abs = "|" + rc_neg if sc_abs else rc_neg
    rc_suffix = iswz_suffix(hsel)

    return f"{d.predicate_str()}HADD2{ofmt_suffix(d.ofmt)}{d.modifiers()} {reg_name(d.rd)}, {ra_abs}{reg_name(d.ra)}{ra_suffix}, {rc_abs}{ur_name(rc_ur)}{rc_suffix}"


def decode_rcx(d: Decode) -> str:
    """RCx variant: extended constant (UR + offset)."""
    hsel = extract(d.hi, d.lo, 61, 60)    # iswzB_as_C
    sb_inv = get_bit(d.hi, d.lo, 63)       # Sc@negate
    sc_abs = get_bit(d.hi, d.lo, 62)       # Sc@absolute
    sb_offset = extract(d.hi, d.lo, 53, 40)  # Sc_offset (scaled by 4)
    rc_ur = extract(d.hi, d.lo, 37, 32)

    ra_neg = negate_prefix(d.e)
    ra_abs = "|" + ra_neg if d.sz else ra_neg
    ra_suffix = iswz_suffix(d.iswzA)

    rc_neg = negate_prefix(sb_inv)
    rc_abs = "|" + rc_neg if sc_abs else rc_neg
    rc_suffix = iswz_suffix(hsel)

    return f"{d.predicate_str()}HADD2{ofmt_suffix(d.ofmt)}{d.modifiers()} {reg_name(d.rd)}, {ra_abs}{reg_name(d.ra)}{ra_suffix}, {rc_abs}c[{ur_name(rc_ur)}][{sb_offset}]{rc_suffix}"


# ── Dispatcher ───────────────────────────────────────────────────────────────

def decode(hi: int, lo: int) -> str:
    d = Decode(
        hi=hi, lo=lo,
        opcode=(get_bit(hi, lo, 91) << 12) | extract(hi, lo, 11, 0),
        ofmt=(get_bit(hi, lo, 85) << 1) | get_bit(hi, lo, 78),
        ftz=get_bit(hi, lo, 80),
        sat=get_bit(hi, lo, 77),
        rd=extract(hi, lo, 23, 16),
        ra=extract(hi, lo, 31, 24),
        iswzA=extract(hi, lo, 75, 74),
        e=get_bit(hi, lo, 72),
        sz=get_bit(hi, lo, 73),
        pg=extract(hi, lo, 14, 12),
        pg_not=get_bit(hi, lo, 15),
        opex=(
            (extract(hi, lo, 124, 122) << 5) | extract(hi, lo, 109, 105)
        ),
    )

    op = d.opcode
    if op == 0x0230:  # RR (and F32_RR)
        return decode_rr(d)
    elif op == 0x0630:  # RC (and F32_RC)
        return decode_rc(d)
    elif op == 0x0430:  # RI / F32_RI / F32i_
        return decode_ri(d)
    elif op == 0x1e30:  # RU (and F32_RU)
        return decode_ru(d)
    elif op == 0x1630:  # RCx (and F32_RCx)
        return decode_rcx(d)
    else:
        return f"UNKNOWN HADD2 opcode 0x{op:04x}"


# ── Test vectors ─────────────────────────────────────────────────────────────

test_vectors = [
    # cublas HADD2.F32
    (0x004fca0000004100, 0x2000000eff087230, "HADD2.F32 R8, -RZ, R14.H0_H0"),
    (0x004fe40000004100, 0x2000000eff0c7230, "HADD2.F32 R12, -RZ, R14.H0_H0"),
    (0x008fc60000004100, 0x20000008ff0a7230, "HADD2.F32 R10, -RZ, R8.H0_H0"),
    (0x004fe40000004100, 0x2000000eff147230, "HADD2.F32 R20, -RZ, R14.H0_H0"),
    (0x008fc60000004100, 0x20000008ff167230, "HADD2.F32 R22, -RZ, R8.H0_H0"),
    (0x010fe40000004100, 0x2000000aff0c7230, "HADD2.F32 R12, -RZ, R10.H0_H0"),
    (0x020fe40000004100, 0x20000008ff0e7230, "HADD2.F32 R14, -RZ, R8.H0_H0"),
    (0x004fe40000004100, 0x2000002bff2b7230, "HADD2.F32 R43, -RZ, R43.H0_H0"),
    (0x008fc60000004100, 0x20000009ff097230, "HADD2.F32 R9, -RZ, R9.H0_H0"),
    (0x010fc60000004100, 0x20000008ff087230, "HADD2.F32 R8, -RZ, R8.H0_H0"),
    (0x020fc60000004100, 0x20000016ff167230, "HADD2.F32 R22, -RZ, R22.H0_H0"),
    (0x004fca0000004100, 0x20000008ff297230, "HADD2.F32 R41, -RZ, R8.H0_H0"),
]


def run_tests():
    passed = 0
    failed = 0
    for hi, lo, expected in test_vectors:
        result = decode(hi, lo)
        if result == expected:
            passed += 1
            print(f"  PASS: {result}")
        else:
            failed += 1
            print(f"  FAIL: got      {result}")
            print(f"        expected  {expected}")
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
