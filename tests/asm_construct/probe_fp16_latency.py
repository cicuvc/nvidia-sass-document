#!/usr/bin/env python3
"""Consumer-specific RAW visibility for sm_120 packed-FP and HADD2.F32."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_alulite_latency as base  # noqa: E402
from probe_fmalite_latency import CONSUMERS  # noqa: E402


@dataclass(frozen=True)
class Producer:
    setup: tuple[str, ...]
    inst: str
    fresh: int


PRODUCERS = {
    "HADD2": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0"),
        "HADD2 R40, R24, R27", 0x3F800000),
    "HMUL2": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x3c003c00"),
        "HMUL2 R40, R24, R27", 0x3F800000),
    "HFMA2": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x3c003c00",
         "MOV32I R28, 0"),
        "HFMA2 R40, R24, R27, R28", 0x3F800000),
    "HFMA2.MMA": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x3c003c00",
         "MOV32I R28, 0"),
        "HFMA2.MMA R40, R24, R27, R28", 0x3F800000),
    "HADD2_32I": Producer(
        ("MOV32I R24, 0x3f803c00",),
        "HADD2_32I R40, R24, 0f3f800000, 0f3f800000", 0x3F803C00),
    "HMUL2_32I": Producer(
        ("MOV32I R24, 0x3f803c00",),
        "HMUL2_32I R40, R24, 0f3f800000, 0f3f800000", 0),
    "HFMA2_32I": Producer(
        ("MOV32I R24, 0x3f803c00", "MOV32I R28, 0x3f003c00"),
        "HFMA2_32I R40, R24, 0f3f800000, 0f3f800000, R28", 0x3F003C00),
    "HADD2.F32": Producer(
        ("MOV32I R24, 0x00003c00",),
        "HADD2.F32 R40, -RZ, R24.H0_H0", 0x3F800000),
}


def source(prod_name: str, consumer: str, coarse: bool) -> str:
    prod = PRODUCERS[prod_name]
    lines = base.prologue("fplat")
    for i, gap in enumerate(base.GAPS):
        lines.append("    MOV32I R60, 0x1;[7:7:{}:8:1]")
        for inst in prod.setup:
            lines.append(f"    {inst};[7:7:{{}}:8:1]")
        lines += [
            f"    MOV32I R40, 0x{base.POISON:08x};[7:7:{{}}:15:1]",
            "    NOP;[7:7:{}:15:1]",
            f"    {prod.inst};[7:7:{{}}:1:1]",
        ]
        lines += base.filler(gap, coarse)
        lines += [
            f"    {CONSUMERS[consumer]};[3:7:{{}}:8:1]",
            "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R51;[0:7:{{}}:1:0]",
        ]
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def measure(prod: str, consumer: str, coarse: bool, reps: int,
            isolated: bool) -> str:
    expected = PRODUCERS[prod].fresh
    if not isolated:
        return base.states(base.run_source(source(prod, consumer, coarse),
                                           "fplat", reps),
                           expected, base.POISON)
    saved = list(base.GAPS)
    out = []
    try:
        for gap in saved:
            base.GAPS = [gap]
            got = base.run_source(source(prod, consumer, coarse), "fplat", reps)
            out.append(base.states(got, expected, base.POISON)[0])
    finally:
        base.GAPS = saved
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--producer", action="append", choices=tuple(PRODUCERS))
    ap.add_argument("--consumer", action="append", choices=tuple(CONSUMERS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--isolated", action="store_true")
    ap.add_argument("--gaps", default="1,2,3,4,5,6,7,8,12,16")
    ns = ap.parse_args()
    base.GAPS = [int(x) for x in ns.gaps.split(",")]
    selected = ns.producer or list(PRODUCERS)
    consumers = ns.consumer or list(CONSUMERS)
    print("gaps: " + " ".join(f"{x:2}" for x in base.GAPS))
    for prod in selected:
        for consumer in consumers:
            for coarse in (False, True):
                pat = measure(prod, consumer, coarse, ns.reps, ns.isolated)
                print(f"{prod:12} -> {consumer:8} "
                      f"{'coarse' if coarse else 'fine':6} {pat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
