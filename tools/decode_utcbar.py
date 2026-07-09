#!/usr/bin/env python3
"""UTCBAR decoder — tcgen05 tensor-core barrier, sm100.

Two opcodes:
  0x13e9  mbarrier-arrive form  <- PTX tcgen05.commit (mbarrier::arrive::one)
  0x9e9   flush form            <- tcgen05 barrier flush

The commit form makes an mbarrier (URa) track completion of prior async tcgen05
ops. Operands: [URa] mbar, URb (param/count), URc (ctaMask for .MULTICAST).
Modifiers: .2CTA (bit85), .MULTICAST (bit75), WAKEUP (bit76), paramtype (bit77).

Validated against real sm_100a vectors (tests/tcgen05_commit_test.cu).
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


def ureg(v: int) -> str:
    return "URZ" if v == UREG_ZERO else f"UR{v}"


def decode_utcbar(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in (0x13E9, 0x9E9):
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    if opc == 0x9E9:  # flush form
        parts.append("UTCBAR.FLUSH")
        return " ".join(parts)

    # commit / mbarrier-arrive form (0x13e9)
    ura = extract(lo64, hi64, list(range(31, 23, -1)))   # mbar address
    urb = extract(lo64, hi64, list(range(39, 31, -1)))   # param / count
    urc = extract(lo64, hi64, list(range(71, 63, -1)))   # ctaMask (MULTICAST)
    cluster2 = extract(lo64, hi64, [85])                 # .2CTA
    multicast = extract(lo64, hi64, [75])                # .MULTICAST
    wakeup = extract(lo64, hi64, [76])
    paramtype = extract(lo64, hi64, [77])                # BAR_TYPE A1T0/A0TX

    mnem = "UTCBAR"
    if cluster2:
        mnem += ".2CTA"
    if paramtype:
        mnem += ".A0TX"      # BAR_TYPE 1; default A1T0 elided
    if wakeup:
        mnem += ".WAKEUP"
    if multicast:
        mnem += ".MULTICAST"
    parts.append(mnem)

    ops = [f"[{ureg(ura)}]", ureg(urb)]
    if multicast:
        ops.append(ureg(urc))
    parts.append(", ".join(ops))
    return " ".join(parts)


if __name__ == "__main__":
    # Real vectors from tcgen05.commit lowering (sm_100a, CUDA 13.1).
    test_vectors = [
        (0x000000ff040073e9, 0x0011d800080000ff, "UTCBAR [UR4], URZ"),
        (0x000000ff040073e9, 0x0011d800082000ff, "UTCBAR.2CTA [UR4], URZ"),
        (0x000000ff040073e9, 0x0011d8000800080a, "UTCBAR.MULTICAST [UR4], URZ, UR10"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_utcbar(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
