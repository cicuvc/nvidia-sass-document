#!/usr/bin/env python3
"""UTCCP decoder — PTX tcgen05.cp (async shared-memory -> TMEM copy), sm100.

Opcode 0x19e7. Copies a matrix from shared memory (described by a 64-bit UMMA
matrix descriptor in URb) into Tensor Memory at tmem[URa+off], optionally
decompressing packed FP6/FP4 source formats to b8x16.

The PTX .shape and .multicast qualifiers are FUSED into the single `mode` field:
  128x256b               -> 128dp256bit
  4x256b                 -> 4dp256bit
  128x128b               -> 128dp128bit
  64x128b.warpx2::02_13  -> 2x64dp128bit_lw02_lw13
  64x128b.warpx2::01_23  -> 2x64dp128bit_lw01_lw23
  32x128b.warpx4         -> 4x32dp128bit

Validated against real sm_100a vectors (tests/utccp_test.cu).
"""

from typing import Optional

MODE = {
    0: "128dp256bit", 1: "INVALID1", 2: "4dp256bit", 3: "128dp128bit",
    4: "2x64dp128bit_lw02_lw13", 5: "2x64dp128bit_lw01_lw23",
    6: "4x32dp128bit", 7: "INVALID7",
}
SRC_FMT = {0: None, 1: "U4x16P64", 2: "U6x16P32", 3: "INVALID3"}
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


def decode_utccp(lo64: int, hi64: int) -> Optional[str]:
    if get_opcode(lo64, hi64) != 0x19E7:
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    ura = extract(lo64, hi64, list(range(31, 23, -1)))   # TMEM base addr reg
    urb = extract(lo64, hi64, list(range(39, 31, -1)))   # matrix-descriptor reg
    mode = (extract(lo64, hi64, [88]) << 2) | extract(lo64, hi64, [84, 83])
    cluster2 = extract(lo64, hi64, [85])                 # ignoreKill <= cluster_sz
    src_fmt = extract(lo64, hi64, [81, 80])
    off = extract(lo64, hi64, list(range(79, 71, -1)) + list(range(63, 39, -1)))
    off = s32(off)

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    # cuobjdump always prints the .T (dst=TMEM) and .S (src=shmem) role tags.
    mnem = "UTCCP.T.S"
    if cluster2:
        mnem += ".2CTA"
    if mode != 0:  # 128dp256bit default elided
        mnem += f".{MODE[mode]}"
    if SRC_FMT.get(src_fmt):
        mnem += f".{SRC_FMT[src_fmt]}"
    parts.append(mnem)

    addr = f"tmem[{ureg(ura)}]" if off == 0 else f"tmem[{ureg(ura)}+{off:#x}]"
    parts.append(f"{addr}, gdesc[{ureg(urb)}]")
    return " ".join(parts)


if __name__ == "__main__":
    # Vectors from tests/utccp_test.cubin (nvcc -arch=sm_100a, CUDA 13.1).
    test_vectors = [
        (0x00000008060079e7, 0x0011d80008000000, "UTCCP.T.S tmem[UR6], gdesc[UR8]"),
        (0x00000008060079e7, 0x0011d80008180000, "UTCCP.T.S.128dp128bit tmem[UR6], gdesc[UR8]"),
        (0x00000008060079e7, 0x0011d80008100000, "UTCCP.T.S.4dp256bit tmem[UR6], gdesc[UR8]"),
        (0x00000008060079e7, 0x0011d80009000000, "UTCCP.T.S.2x64dp128bit_lw02_lw13 tmem[UR6], gdesc[UR8]"),
        (0x00000008060079e7, 0x0011d80009080000, "UTCCP.T.S.2x64dp128bit_lw01_lw23 tmem[UR6], gdesc[UR8]"),
        (0x00000008060079e7, 0x0011d80009100000, "UTCCP.T.S.4x32dp128bit tmem[UR6], gdesc[UR8]"),
        (0x00000008060079e7, 0x0011d800081a0000, "UTCCP.T.S.128dp128bit.U6x16P32 tmem[UR6], gdesc[UR8]"),
        (0x00000008060079e7, 0x0011d80008190000, "UTCCP.T.S.128dp128bit.U4x16P64 tmem[UR6], gdesc[UR8]"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_utccp(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
