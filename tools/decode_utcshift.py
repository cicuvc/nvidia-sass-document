#!/usr/bin/env python3
"""UTCSHIFT decoder — PTX tcgen05.shift.down (async TMEM row-shift), sm100.

Opcode 0x19e6. Shifts 32-byte elements down by one row across all rows of a TMEM
matrix except the last. Standalone counterpart of the fused UTCHMMA.ASHIFT.

Validated against real sm_100a vectors (tests/tcgen05_shift_test.cu).
"""

from typing import Optional

UREG_ZERO = 0xFF


def extract(lo64: int, hi64: int, bits: list[int]) -> int:
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val


def get_opcode(lo64: int, hi64: int) -> int:
    return extract(lo64, hi64, [91] + list(range(11, -1, -1)))


def s32(val: int) -> int:
    return val - 0x100000000 if val & 0x80000000 else val


def ureg(v: int) -> str:
    return "URZ" if v == UREG_ZERO else f"UR{v}"


def decode_utcshift(lo64: int, hi64: int) -> Optional[str]:
    if get_opcode(lo64, hi64) != 0x19E6:
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    ura = extract(lo64, hi64, list(range(31, 23, -1)))
    off = extract(lo64, hi64, list(range(79, 71, -1)) + list(range(63, 39, -1)))
    off = s32(off)
    mode_down = extract(lo64, hi64, [80])          # DOWNONLY (=1 DOWN)
    cluster2 = extract(lo64, hi64, [85])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    mnem = "UTCSHIFT"
    if cluster2:
        mnem += ".2CTA"
    if mode_down:
        mnem += ".DOWN"
    parts.append(mnem)

    addr = f"tmem[{ureg(ura)}]" if off == 0 else f"tmem[{ureg(ura)}+{off:#x}]"
    parts.append(addr)
    return " ".join(parts)


if __name__ == "__main__":
    # Vectors from tests/tcgen05_shift_test.cubin (nvcc -arch=sm_100a, CUDA 13.1).
    test_vectors = [
        (0x00000000060079e6, 0x000fd80008010000, "UTCSHIFT.DOWN tmem[UR6]"),
        (0x00000000040079e6, 0x001fd80008210000, "UTCSHIFT.2CTA.DOWN tmem[UR4]"),
        (0x00000000040079e6, 0x001fd80008010000, "UTCSHIFT.DOWN tmem[UR4]"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_utcshift(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
