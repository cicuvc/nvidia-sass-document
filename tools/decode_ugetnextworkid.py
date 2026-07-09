#!/usr/bin/env python3
"""UGETNEXTWORKID decoder — PTX clusterlaunchcontrol.try_cancel, sm100.

Opcode 0x13ca (udp_pipe, $VQ_WORKID=43). The work-stealing API that communicates
with the hardware work distributor (WD) to atomically cancel a not-yet-launched
cluster CTA and steal its work.

[URa] = shared-memory addr for the 16B opaque response
[URb] = mbarrier address (URb = URa+1, fused via TABLES_URa_0)
cast = SELFCAST(0) / BROADCAST(1) at bit[72]

SELFCAST writes the response to one CTA, BROADCAST to all in the cluster.
Validated against real sm_100a vectors (tests/ldtm_test.cubin — alloc lowering).
"""

from typing import Optional


def extract(lo64: int, hi64: int, bits: list[int]) -> int:
    val = 0
    for bit in bits:
        bv = ((hi64 >> (bit - 64)) if bit >= 64 else (lo64 >> bit)) & 1
        val = (val << 1) | bv
    return val


def get_opcode(lo64: int, hi64: int) -> int:
    return extract(lo64, hi64, [91] + list(range(11, -1, -1)))


def decode_ugetnextworkid(lo64: int, hi64: int) -> Optional[str]:
    if get_opcode(lo64, hi64) != 0x13CA:
        return None

    pg = extract(lo64, hi64, [14, 13, 12])
    pg_not = extract(lo64, hi64, [15])
    # TABLES_URa_0(URa,URb) -> URa = field, URb = URa+1
    ra_field = extract(lo64, hi64, list(range(31, 23, -1)))
    ura = ra_field
    urb = ra_field + 1
    cast = extract(lo64, hi64, [72])          # 0=SELFCAST, 1=BROADCAST

    parts = []
    if pg != 7:
        parts.append(f"@{'!' if pg_not else ''}UP{pg}")

    mnem = "UGETNEXTWORKID"
    if cast:
        mnem += ".BROADCAST"
    else:
        mnem += ".SELFCAST"
    parts.append(mnem)
    parts.append(f"[UR{ura}], [UR{urb}]")
    return " ".join(parts)


if __name__ == "__main__":
    # Vector from the clusterlaunchcontrol.try_cancel lowering (sm_100a, CUDA 13.1).
    test_vectors = [
        (0x00000000060073ca, 0x000fd80008000000,
         "UGETNEXTWORKID.SELFCAST [UR6], [UR7]"),
    ]

    all_ok = True
    for lo, hi, expected in test_vectors:
        result = decode_ugetnextworkid(lo, hi)
        status = "OK" if result == expected else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"{lo:#018x} {hi:#018x}  =>  {result}")
        print(f"  expected: {expected}  [{status}]")

    print()
    print("ALL PASS" if all_ok else "SOME FAILED")
