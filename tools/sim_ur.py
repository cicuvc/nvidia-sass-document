#!/usr/bin/env python3
"""Simulate uniform-register SASS instructions (UMOV, USHF, ULOP3.LUT).

Feed cuobjdump hex lines, get the final UR state.
Each 128-bit instruction = lo64 + hi64 hex words (two hex lines from cuobjdump).
"""

import re, sys, struct

UR = {i: 0 for i in range(64)}  # UR0..UR63, UR63=URZ fixed at 0


def bits(val, hi, lo):
    """Extract bits[hi:lo] inclusive."""
    mask = ((1 << (hi - lo + 1)) - 1) << lo
    return (val & mask) >> lo


def sim_umov(lo, hi):
    """UMOV: opcode 0x0882 (imm) or 0x1c82 (reg)."""
    op = bits(lo, 11, 0) if bits(hi, 91 - 64, 91 - 64) == 0 else None
    op13_hi = bits(hi, 91 - 64, 91 - 64)
    op13_lo = bits(lo, 11, 0)
    op13 = (op13_hi << 12) | op13_lo
    rd = bits(lo, 21, 16)
    if op13 == 0x0882:
        imm = bits(lo, 63, 32)
        old = UR[rd]
        UR[rd] = imm & 0xFFFFFFFF
        print(f"  UMOV UR{rd}, 0x{imm:x}  -> UR{rd}=0x{UR[rd]:08x} (was 0x{old:08x})")
    elif op13 == 0x1c82:
        rb = bits(lo, 37, 32)
        old = UR[rd]
        UR[rd] = 0 if rb == 63 else UR[rb]
        src = 'URZ' if rb == 63 else f'UR{rb}'
        print(f"  UMOV UR{rd}, {src}  -> UR{rd}=0x{UR[rd]:08x} (was 0x{old:08x})")


def sim_ushf(lo, hi):
    """USHF funnel shift. Opcode 0x1299 (3 reg), 0x1499 (imm shift), 0x1899 (imm B)."""
    op13_hi = bits(hi, 91 - 64, 91 - 64)
    op13_lo = bits(lo, 11, 0)
    op13 = (op13_hi << 12) | op13_lo
    rd = bits(lo, 21, 16)
    ra = bits(lo, 29, 24)
    dir_bit = bits(hi, 76 - 64, 76 - 64)  # 0=left, 1=right
    cw = bits(hi, 75 - 64, 75 - 64)  # 0=clamp, 1=wrap
    fmt = bits(hi, 74 - 64, 73 - 64)  # 2=S32, 3=U32, 0=S64, 1=U64
    hilo = bits(hi, 80 - 64, 80 - 64)  # 0=LO, 1=HI

    if op13 == 0x1499:
        rb = bits(lo, 37, 32)
        rc = bits(hi, 69 - 64, 69 - 64)
        shift_n = rb if rb != 63 else UR[rb]
        val_a = UR[ra]
        val_c = 0 if rc == 63 else UR[rc]
    elif op13 == 0x1299:
        rb = bits(lo, 37, 32)
        rc = bits(hi, 69 - 64, 69 - 64)
        shift_n = UR[rb]
        val_a = UR[ra]
        val_c = 0 if rc == 63 else UR[rc]
    elif op13 == 0x1899:
        shift_n = bits(lo, 63, 32)  # immediate shift amount
        rc = bits(hi, 69 - 64, 69 - 64)
        val_a = UR[ra]
        val_c = 0 if rc == 63 else UR[rc]
    else:
        return

    if dir_bit == 0:  # left
        concat = ((val_a & 0xFFFFFFFF) << 32) | (val_c & 0xFFFFFFFF)
        shifted = concat << shift_n
    else:  # right
        concat = ((val_a & 0xFFFFFFFF) << 32) | (val_c & 0xFFFFFFFF)
        shifted = concat >> shift_n

    if hilo == 0:
        result = shifted & 0xFFFFFFFF
    else:
        result = (shifted >> 32) & 0xFFFFFFFF

    direction = 'L' if dir_bit == 0 else 'R'
    fmt_str = {0: 'S64', 1: 'U64', 2: 'S32', 3: 'U32'}[fmt]
    hl = 'LO' if hilo == 0 else 'HI'
    old = UR[rd]
    UR[rd] = result
    print(f"  USHF.{direction}.{fmt_str}.{hl} UR{rd}, UR{ra}, {shift_n}, UR'{val_c:08x}"
          f"  -> UR{rd}=0x{result:08x} (was 0x{old:08x})")


def sim_ulop3(lo, hi):
    """ULOP3.LUT with immediate. Opcode 0x1892 (imm) or 0x1292 (noimm)."""
    op13_hi = bits(hi, 91 - 64, 91 - 64)
    op13_lo = bits(lo, 11, 0)
    op13 = (op13_hi << 12) | op13_lo
    rd = bits(lo, 21, 16)
    ra = bits(lo, 29, 24)
    rc = bits(hi, 69 - 64, 69 - 64)
    lut = bits(hi, 79 - 64, 72 - 64)
    pop = bits(hi, 80 - 64, 80 - 64)

    val_a = UR[ra]
    val_c = 0 if rc == 63 else UR[rc]
    val_b = 0
    if op13 == 0x1892:
        val_b = bits(lo, 63, 32)
    elif op13 == 0x1292:
        rb = bits(lo, 37, 32)
        val_b = UR[rb]

    result = 0
    for bit in range(32):
        a = (val_a >> bit) & 1
        b = (val_b >> bit) & 1
        c = (val_c >> bit) & 1
        idx = (a << 2) | (b << 1) | c
        out = (lut >> idx) & 1
        result |= out << bit

    old = UR[rd]
    UR[rd] = result
    print(f"  ULOP3.LUT UR{rd}, UR{ra}, 0x{val_b:x}, UR'{val_c:08x}, lut=0x{lut:02x}"
          f"  -> UR{rd}=0x{result:08x} (was 0x{old:08x})")


def sim_instruction(lo, hi):
    """Dispatch based on opcode."""
    op13_hi = bits(hi, 91 - 64, 91 - 64)
    op13_lo = bits(lo, 11, 0)
    op13 = (op13_hi << 12) | op13_lo

    if op13 == 0x0882 or op13 == 0x1c82:
        sim_umov(lo, hi)
    elif op13 in (0x1299, 0x1499, 0x1899):
        sim_ushf(lo, hi)
    elif op13 in (0x1292, 0x1892):
        sim_ulop3(lo, hi)
    else:
        print(f"  [skip] opcode=0x{op13:03x}")


def main():
    # Read lo+hi hex pairs from stdin or file args
    lines = sys.stdin.read().splitlines() if not sys.argv[1:] else \
        open(sys.argv[1]).read().splitlines()

    # Collect hex tokens matching 0x[N]{8,16}
    hex_vals = []
    for line in lines:
        for m in re.finditer(r'0x[0-9a-fA-F]{8,16}', line):
            hex_vals.append(m.group())

    i = 0
    while i + 1 < len(hex_vals):
        lo_str = hex_vals[i]
        hi_str = hex_vals[i + 1]
        lo = int(lo_str, 16)
        hi = int(hi_str, 16)

        op13_hi = bits(hi, 91 - 64, 91 - 64)
        op13_lo = bits(lo, 11, 0)
        op13 = (op13_hi << 12) | op13_lo

        if op13 in (0x0882, 0x1c82, 0x1299, 0x1499, 0x1899, 0x1292, 0x1892):
            print(f"[{lo_str} | {hi_str}]")
            sim_instruction(lo, hi)
            i += 2
            continue
        i += 1

    print("\n=== Final UR state ===")
    for reg in sorted(UR):
        val = UR[reg]
        if val != 0 or reg < 10:
            print(f"  UR{reg:2d} = 0x{val:08x}  ({val})")
    print(f"\n  UR4:UR5 = 0x{UR[4]:08x}_{UR[5]:08x}")


if __name__ == '__main__':
    main()
