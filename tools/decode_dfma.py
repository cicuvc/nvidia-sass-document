#!/usr/bin/env python3
"""DFMA full decoder — FP64 fused multiply-add, 9 variants."""

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


OPCODES = {0x22b, 0x42b, 0x62b, 0x82b, 0xa2b, 0xc2b, 0xe2b, 0x162b, 0x1a2b, 0x1c2b, 0x1e2b}


def reg_s(r: int, neg: int, abs_: int) -> str:
    name = f"R{r}" if r != 0xff else "RZ"
    if neg: return f"-{name}"
    if abs_: return f"|{name}|"
    return name


def decode_dfma(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in OPCODES:
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rnd = extract(lo64, hi64, [79, 78])
    rd = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    ra = extract(lo64, hi64, [31, 30, 29, 28, 27, 26, 25, 24])
    rc = extract(lo64, hi64, [71, 70, 69, 68, 67, 66, 65, 64])

    is_rur = (opc in (0xc2b, 0x1c2b))
    if is_rur:
        urb = extract(lo64, hi64, [37, 36, 35, 34, 33, 32])
        rb_s = f"UR{urb}"
        rb = 0
        rb_neg = extract(lo64, hi64, [63])
        rb_abs = extract(lo64, hi64, [62])
    else:
        rb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
        rb_neg = extract(lo64, hi64, [63])
        rb_abs = extract(lo64, hi64, [62])
        rb_s = reg_s(rb, rb_neg, rb_abs)

    ra_neg = extract(lo64, hi64, [72])
    ra_abs = extract(lo64, hi64, [73])
    rb_neg = extract(lo64, hi64, [63])
    rb_abs = extract(lo64, hi64, [62])
    rc_neg = extract(lo64, hi64, [75])
    rc_abs = extract(lo64, hi64, [74])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}P{pg}")

    mnem = "DFMA"
    if rnd != 0:
        mnem += f".{RND[rnd]}"
    parts.append(mnem)

    parts.append(f"{reg_s(rd, 0, 0)},")
    parts.append(reg_s(ra, ra_neg, ra_abs) + ",")
    parts.append(rb_s + ",")
    parts.append(reg_s(rc, rc_neg, rc_abs))

    return " ".join(parts)


if __name__ == "__main__":
    tests = [
        (0x000000040a027c2b, 0x0041ee0000000a00, "DFMA R2, R10, UR4, R12"),
        (0x000000040a067c2b, 0x000ea20000000a00, "DFMA.RM R6, R10, UR4, R12"),
        (0x000000040a087c2b, 0x000ee20000000a00, "DFMA.RP R8, R10, UR4, R12"),
        (0x000000040a0a7c2b, 0x000f220000000a00, "DFMA.RZ R10, R10, UR4, R12"),
    ]
    ok = 0
    for lo, hi, exp in tests:
        r = decode_dfma(lo, hi)
        s = "OK" if r == exp else "MISMATCH"
        if r == exp: ok += 1
        print(f"{r:50s} [{s}]" + ("" if s == "OK" else f"  expected: {exp}"))
    print(f"\n{ok}/{len(tests)} PASS")
