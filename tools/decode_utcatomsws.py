#!/usr/bin/env python3
"""UTCATOMSWS decoder — uniform tensor-core atomic on software state, sm100.

The workhorse of the tcgen05 TMEM software allocator. Three opcodes:
  0x13e3  CAS  — compare-and-swap (URd, URb, URc; result pred UPu)
  0x15e3  FAS  — FIND_AND_SET (URd, URb; result pred UPu; optional .ALIGN)
  0x19e3  OP   — AND / OR on software-state word (URd, URb; op = bit[87])
Each has a `.ONE` alternate (same bits; display-only modifier).

Validated against real sm_100a vectors mined from the tcgen05.alloc/dealloc
lowering (tests/ldtm_test.cubin).
"""

from typing import Optional

# 8-bit uniform-register field: 0xff prints as URZ (like GPR RZ convention).
UREG_ZERO = 0xFF


def extract(lo64: int, hi64: int, bits: list[int]) -> int:
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val


def get_opcode(lo64: int, hi64: int) -> int:
    return extract(lo64, hi64, [91] + list(range(11, -1, -1)))


def ureg(v: int) -> str:
    return "URZ" if v == UREG_ZERO else f"UR{v}"


def decode_utcatomsws(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in (0x13E3, 0x15E3, 0x19E3):
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    urd = extract(lo64, hi64, list(range(23, 15, -1)))
    urb = extract(lo64, hi64, list(range(39, 31, -1)))
    pu = extract(lo64, hi64, [83, 82, 81])
    cluster2 = extract(lo64, hi64, [85])          # ignoreKill <= cluster_sz (1=2CTA)
    align = extract(lo64, hi64, [75])             # FAS only

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    mnem = "UTCATOMSWS"
    if cluster2:           # .2CTA prints before the op suffix
        mnem += ".2CTA"
    if opc == 0x15E3:      # FIND_AND_SET
        mnem += ".FIND_AND_SET"
        if align:
            mnem += ".ALIGN"
    elif opc == 0x13E3:    # CAS
        mnem += ".CAS"
    else:                  # OP: AND / OR selected by bit[87]
        mnem += ".OR" if extract(lo64, hi64, [87]) else ".AND"
    parts.append(mnem)

    # Operand order mirrors cuobjdump: [UPu ',']? URd ',' URb [',' URc(CAS)]
    ops = []
    if opc in (0x13E3, 0x15E3):
        ops.append(f"UP{pu}")
    ops.append(ureg(urd))
    ops.append(ureg(urb))
    if opc == 0x13E3:
        urc = extract(lo64, hi64, list(range(71, 63, -1)))
        ops.append(ureg(urc))
    parts.append(", ".join(ops))
    return " ".join(parts)


if __name__ == "__main__":
    # Real vectors from the tcgen05.alloc/dealloc lowering (sm_100a, CUDA 13.1).
    test_vectors = [
        (0x00000006000675e3, 0x000e240008000800,
         "UTCATOMSWS.FIND_AND_SET.ALIGN UP0, UR6, UR6"),
        (0x0000000600ff79e3, 0x0005e20008000000,
         "UTCATOMSWS.AND URZ, UR6"),
        (0x00000004000475e3, 0x000e240008200800,
         "UTCATOMSWS.2CTA.FIND_AND_SET.ALIGN UP0, UR4, UR4"),
        (0x0000000400ff79e3, 0x0007e20008000000,
         "UTCATOMSWS.AND URZ, UR4"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_utcatomsws(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
