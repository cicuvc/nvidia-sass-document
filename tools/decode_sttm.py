#!/usr/bin/env python3
"""STTM decoder — PTX tcgen05.st (tensor-memory store), sm100.

Store mirror of LDTM: reads registers, writes TMEM. Opcode 0x19ed.
Data source in Rb [39:32], TMEM base address in URc [71:64]. Uses
EXPAND16BIT (.unpack::16b) where LDTM uses PACK. Validated against real
sm_100a vectors (tests/sttm_test.cu).
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


def decode_sttm(lo64: int, hi64: int) -> Optional[str]:
    if get_opcode(lo64, hi64) != 0x19ed:
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    rb = extract(lo64, hi64, [39, 38, 37, 36, 35, 34, 33, 32])  # data source reg
    urc = extract(lo64, hi64, [71, 70, 69, 68, 67, 66, 65, 64])  # TMEM base addr
    layout = extract(lo64, hi64, [87, 82, 81])
    num = extract(lo64, hi64, [85, 84, 83])
    expand = extract(lo64, hi64, [80])
    off = extract(lo64, hi64, list(range(79, 71, -1)) + list(range(63, 39, -1)))
    off = s32(off)

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    mnem = "STTM"
    if layout != 2:  # 32dp32bit default elided
        mnem += f".{LAYOUT[layout]}"
    if num != 0:  # x1 default elided
        mnem += f".{NUM[num]}"
    if expand:
        mnem += ".EXPAND16BIT"
    parts.append(mnem)

    rb_s = f"R{rb}" if rb != 0xff else "RZ"
    base = f"UR{urc}" if urc != 0x3f else "URZ"
    addr = f"tmem[{base}]" if off == 0 else f"tmem[{base}+{off:#x}]"
    parts.append(f"{addr}, {rb_s}")
    return " ".join(parts)


if __name__ == "__main__":
    # Vectors from tests/sttm_test.cubin (nvcc -arch=sm_100a, CUDA 13.1).
    test_vectors = [
        (0x00000004000079ed, 0x0041e20008040006, "STTM tmem[UR6], R4"),
        (0x00000004000079ed, 0x0081e200080c0006, "STTM.x2 tmem[UR6], R4"),
        (0x00000004000079ed, 0x0001e200080e0006, "STTM.16dp64bit.x2 tmem[UR6], R4"),
        (0x00000004000079ed, 0x0101e20008100006, "STTM.16dp128bit.x4 tmem[UR6], R4"),
        (0x00000004000079ed, 0x0001e20008020006, "STTM.16dp256bit tmem[UR6], R4"),
        (0x00000004000079ed, 0x0001e20008010006, "STTM.16dp128bit.EXPAND16BIT tmem[UR6], R4"),
        (0x00000004000079ed, 0x0001e20008880006, "STTM.16dp32bit_t0_t15.x2 tmem[UR6], R4"),
        (0x00001004000079ed, 0x0001e200088a0006, "STTM.16dp32bit_t16_t31.x2 tmem[UR6+0x10], R4"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_sttm(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
