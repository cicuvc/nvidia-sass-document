#!/usr/bin/env python3
"""LDTM decoder — PTX tcgen05.ld (tensor-memory load), sm100.

Reconstructs the cuobjdump spelling from the 128-bit encoding and validates
against real sm_100a vectors (tests/ldtm_test.cu). Opcode 0x19ee.
"""

from typing import Optional

LAYOUT = {
    0: "16dp128bit", 1: "16dp256bit", 2: "32dp32bit", 3: "16dp64bit",
    4: "16dp32bit_t0_t15", 5: "16dp32bit_t16_t31", 6: "INVALID6", 7: "INVALID7",
}
NUM = {0: "x1", 1: "x2", 2: "x4", 3: "x8", 4: "x16", 5: "x32", 6: "x64", 7: "x128"}


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


def decode_ldtm(lo64: int, hi64: int) -> Optional[str]:
    if get_opcode(lo64, hi64) != 0x19ee:
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rd = extract(lo64, hi64, [23, 22, 21, 20, 19, 18, 17, 16])
    urb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])
    # layout = {bit87, bit82, bit81}; num = [85:83]; pack = bit80
    layout = extract(lo64, hi64, [87, 82, 81])
    num = extract(lo64, hi64, [85, 84, 83])
    pack = extract(lo64, hi64, [80])
    # Sb_offset split field [79:72] || [63:40]
    off = extract(lo64, hi64, list(range(79, 71, -1)) + list(range(63, 39, -1)))
    off = s32(off)

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    mnem = "LDTM"
    if layout != 2:  # 32dp32bit is the default, elided by cuobjdump
        mnem += f".{LAYOUT[layout]}"
    if num != 0:  # x1 default elided
        mnem += f".{NUM[num]}"
    if pack:
        mnem += ".PACK16BIT"
    parts.append(mnem)

    rd_s = f"R{rd}" if rd != 0xff else "RZ"
    base = f"UR{urb}" if urb != 0x3f else "URZ"
    addr = f"tmem[{base}]" if off == 0 else f"tmem[{base}+{off:#x}]"
    parts.append(f"{rd_s}, {addr}")
    return " ".join(parts)


if __name__ == "__main__":
    # Vectors from tests/ldtm_test.cubin (nvcc -arch=sm_100a, CUDA 13.1).
    test_vectors = [
        (0x00000006000079ee, 0x001e220008040000, "LDTM R0, tmem[UR6]"),
        (0x00000006001879ee, 0x000e6200080c0000, "LDTM.x2 R24, tmem[UR6]"),
        (0x00000006000279ee, 0x000fe200080e0000, "LDTM.16dp64bit.x2 R2, tmem[UR6]"),
        (0x00000006000479ee, 0x000ea20008100000, "LDTM.16dp128bit.x4 R4, tmem[UR6]"),
        (0x00000006000c79ee, 0x000ee20008020000, "LDTM.16dp256bit R12, tmem[UR6]"),
        (0x00000006001279ee, 0x000f2200080d0000, "LDTM.x2.PACK16BIT R18, tmem[UR6]"),
        (0x00000006001079ee, 0x000fe20008880000, "LDTM.16dp32bit_t0_t15.x2 R16, tmem[UR6]"),
        (0x00001006001079ee, 0x000f6200088a0000, "LDTM.16dp32bit_t16_t31.x2 R16, tmem[UR6+0x10]"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_ldtm(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
