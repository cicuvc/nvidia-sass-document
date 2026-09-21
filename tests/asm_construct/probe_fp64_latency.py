#!/usr/bin/env python3
"""Unsafe-schedule RAW visibility of sm_120 FP64/CLMAD result halves."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_alulite_latency as base  # noqa: E402
from probe_fmalite_latency import CONSUMERS as BASE_CONSUMERS  # noqa: E402


CONSUMERS = dict(BASE_CONSUMERS)
CONSUMERS["fp64"] = "DADD {R50,R51}, {R40,R41}, {RZ,RZ}"


@dataclass(frozen=True)
class Producer:
    setup: tuple[str, ...]
    inst: str
    lo: int
    hi: int


PRODUCERS = {
    "DADD": Producer(
        ("MOV32I R24, 0", "MOV32I R25, 0x3ff00000",
         "MOV32I R26, 0", "MOV32I R27, 0"),
        "DADD {R40,R41}, {R24,R25}, {R26,R27}", 0, 0x3FF00000),
    "DMUL": Producer(
        ("MOV32I R24, 0", "MOV32I R25, 0x3ff00000",
         "MOV32I R26, 0", "MOV32I R27, 0x3ff00000"),
        "DMUL {R40,R41}, {R24,R25}, {R26,R27}", 0, 0x3FF00000),
    "DFMA": Producer(
        ("MOV32I R24, 0", "MOV32I R25, 0x3ff00000",
         "MOV32I R26, 0", "MOV32I R27, 0x3ff00000",
         "MOV32I R28, 0", "MOV32I R29, 0"),
        "DFMA {R40,R41}, {R24,R25}, {R26,R27}, {R28,R29}",
        0, 0x3FF00000),
    "CLMAD.LO": Producer(
        ("MOV32I R24, 1", "MOV32I R25, 0",
         "MOV32I R26, 1", "MOV32I R27, 0",
         "MOV32I R28, 0x3f800001", "MOV32I R29, 0x2468ace0"),
        "CLMAD.LO {R40,R41}, {R24,R25}, {R26,R27}, {R28,R29}",
        0x3F800000, 0x2468ACE0),
}


def source(prod_name: str, half: str, consumer: str, coarse: bool) -> str:
    prod = PRODUCERS[prod_name]
    src = "R40" if half == "lo" else "R41"
    lines = base.prologue("dlat")
    consumer_inst = CONSUMERS[consumer]
    detector_src = "R50"
    if consumer == "fp64":
        detector_src = "R50" if half == "lo" else "R51"
    else:
        consumer_inst = consumer_inst.replace("R40", src)
    for i, gap in enumerate(base.GAPS):
        lines.append("    MOV32I R60, 0x1;[7:7:{}:8:1]")
        for inst in prod.setup:
            lines.append(f"    {inst};[7:7:{{}}:8:1]")
        lines += [
            f"    MOV32I R40, 0x{base.POISON:08x};[7:7:{{}}:15:1]",
            f"    MOV32I R41, 0x{base.POISON:08x};[7:7:{{}}:15:1]",
            "    NOP;[7:7:{}:15:1]",
            f"    {prod.inst};[7:7:{{}}:1:1]",
        ]
        lines += base.filler(gap, coarse)
        lines += [
            f"    {consumer_inst};[3:7:{{}}:8:1]",
            f"    IADD3 R52, {detector_src}, RZ, RZ;[7:7:{{3}}:8:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R52;[0:7:{{}}:1:0]",
        ]
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--producer", action="append", choices=tuple(PRODUCERS))
    ap.add_argument("--consumer", action="append", choices=tuple(CONSUMERS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--isolated", action="store_true",
                    help="put one producer/gap in each fresh CUDA context")
    ap.add_argument("--gaps", default="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,20,24,30")
    ns = ap.parse_args()
    base.GAPS = [int(x) for x in ns.gaps.split(",")]
    for name in ns.producer or list(PRODUCERS):
        prod = PRODUCERS[name]
        for half, final in (("lo", prod.lo), ("hi", prod.hi)):
            for consumer in ns.consumer or list(CONSUMERS):
                for coarse in (False, True):
                    if not ns.isolated:
                        got = base.run_source(
                            source(name, half, consumer, coarse),
                            "dlat", ns.reps)
                        pat = base.states(got, final, base.POISON)
                    else:
                        saved = list(base.GAPS)
                        chars = []
                        try:
                            for gap in saved:
                                base.GAPS = [gap]
                                got = base.run_source(
                                    source(name, half, consumer, coarse),
                                    "dlat", ns.reps)
                                chars.append(base.states(
                                    got, final, base.POISON)[0])
                        finally:
                            base.GAPS = saved
                        pat = "".join(chars)
                    print(f"{name:8} {half} -> {consumer:8} "
                          f"{'coarse' if coarse else 'fine':6} {pat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
