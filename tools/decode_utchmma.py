#!/usr/bin/env python3
"""UTCHMMA decoder — PTX tcgen05.mma.kind::f16 (5th-gen tensor-core MMA), sm100.

D = A*B + D, single-thread-issued, accumulator + operands in TMEM.
Two opcodes by A source:
  0x15ea  A from shared-memory matrix descriptor (gdesc)
  0x19ea  A from Tensor Memory (tmem), enables .ASHIFT

Operands (cuobjdump order):
  A[URa]  B[URb]  C/D[URc]  tmemE[URe]  idesc[URh]  UPp  [, scaleU4]
where URe/URh are encoded fused via TABLES_URa_0: field[47:40]=URe, URh=URe+1
(adjacent pair); URi rides field[55:48].

Validated against real sm_100a vectors (tests/utchmma_test.cu).
"""

from typing import Optional

UREG_ZERO = 0xFF
BUFFER = {0: None, 1: "BUFFER1", 2: "BUFFER2", 3: "BUFFER3"}


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


def decode_utchmma(lo64: int, hi64: int) -> Optional[str]:
    opc = get_opcode(lo64, hi64)
    if opc not in (0x15EA, 0x19EA):
        return None
    a_from_tmem = (opc == 0x19EA)

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])

    ura = extract(lo64, hi64, list(range(31, 23, -1)))    # A (gdesc or tmem)
    urb = extract(lo64, hi64, list(range(39, 31, -1)))    # B gdesc
    urc = extract(lo64, hi64, list(range(71, 63, -1)))    # C/D accumulator (tmem)
    ure = extract(lo64, hi64, list(range(47, 39, -1)))    # tmemE (URh = URe+1)
    urh = (ure + 1) & 0xFF                                 # idesc reg (adjacent)

    upp = extract(lo64, hi64, [89, 88, 87])               # enable-input-d pred
    upp_not = extract(lo64, hi64, [90])
    scaleU4 = extract(lo64, hi64, [78, 77, 76, 75])
    cluster2 = extract(lo64, hi64, [85])
    ws = extract(lo64, hi64, [83])
    reuse_a = extract(lo64, hi64, [86])
    keep_a = extract(lo64, hi64, [84])
    reuse_b = extract(lo64, hi64, [82])
    keep_b = extract(lo64, hi64, [81])
    buffer = extract(lo64, hi64, [80, 79])
    ashift = extract(lo64, hi64, [74]) if a_from_tmem else 0

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    mnem = "UTCHMMA"
    if cluster2:
        mnem += ".2CTA"
    if ws:
        mnem += ".WS"
    if ashift:
        mnem += ".ASHIFT"
    if reuse_a:
        mnem += ".A_REUSE"
    if keep_a:
        mnem += ".A_KEEP"
    if reuse_b:
        mnem += ".B_REUSE"
    if keep_b:
        mnem += ".B_KEEP"
    if BUFFER.get(buffer):
        mnem += f".{BUFFER[buffer]}"
    parts.append(mnem)

    a_op = f"tmem[{ureg(ura)}]" if a_from_tmem else f"gdesc[{ureg(ura)}]"
    ops = [
        a_op,
        f"gdesc[{ureg(urb)}]",
        f"tmem[{ureg(urc)}]",
        f"tmem[{ureg(ure)}]",
        f"idesc[{ureg(urh)}]",
        f"{'!' if upp_not else ''}UP{upp}" if upp != 7 or upp_not else "UPT",
    ]
    tail = ", ".join(ops)
    if scaleU4:
        tail += f", {scaleU4:#x}"
    parts.append(tail)
    return " ".join(parts)


if __name__ == "__main__":
    # Vectors from tests/utchmma_test.cubin (nvcc -arch=sm_100a, CUDA 13.1).
    test_vectors = [
        (0x00ff0408060075ea, 0x0011d8000ba0000a,
         "UTCHMMA.2CTA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UPT"),
        (0x00ff0408060075ea, 0x0011d8000b80180a,
         "UTCHMMA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UPT, 0x3"),
        (0x00ff0408070079ea, 0x01f9d8000b800006,
         "UTCHMMA tmem[UR7], gdesc[UR8], tmem[UR6], tmem[UR4], idesc[UR5], UPT"),
        (0x00ff0408060075ea, 0x0011d8000800000a,
         "UTCHMMA gdesc[UR6], gdesc[UR8], tmem[UR10], tmem[UR4], idesc[UR5], UP0"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_utchmma(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
