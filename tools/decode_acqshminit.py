#!/usr/bin/env python3
"""Decode Blackwell ACQSHMINIT (sm_100/sm_120, opcode 0x877)."""
import sys


def bits(value, hi, lo):
    return (value >> lo) & ((1 << (hi - lo + 1)) - 1)


def decode(lo64, hi64):
    word = lo64 | (hi64 << 64)
    opcode = (bits(word, 91, 91) << 12) | bits(word, 11, 0)
    assert opcode == 0x877, f"unexpected opcode {opcode:#x}"
    pg = bits(word, 14, 12)
    pg_not = bits(word, 15, 15)
    guard = ""
    if pg != 7 or pg_not:
        pred = "PT" if pg == 7 else f"P{pg}"
        guard = f"@{'!' if pg_not else ''}{pred} "
    return guard + "ACQSHMINIT"


VECTORS = [
    (0x0000000000007877, 0x000fe20000000000, "ACQSHMINIT"),
    (0x0000000000000877, 0x000fca0000000000, "@P0 ACQSHMINIT"),
    (0x0000000000009877, 0x021fd00000000000, "@!P1 ACQSHMINIT"),
    (0x000000000000f877, 0x000fe20000000000, "@!PT ACQSHMINIT"),
]


if __name__ == "__main__":
    ok = True
    for lo, hi, expected in VECTORS:
        got = decode(lo, hi)
        good = got == expected
        ok &= good
        print(f"{'OK ' if good else 'XX '} {got:<20} | exp: {expected}")
    print("ALL PASS" if ok else "MISMATCH")
    sys.exit(0 if ok else 1)
