#!/usr/bin/env python3
"""Consumer-specific RAW visibility for sm_100 FFMA2/FADD2/FMUL2 halves."""

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


# Every lane produces 1.0f (0x3f800000).  Both destination halves can use the
# same poison/fresh detector and are scanned independently.
PRODUCERS = {
    "FADD2": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R25, 0x3f800000",
         "MOV32I R26, 0", "MOV32I R27, 0"),
        "FADD2.F32x2.F32x2 {R40,R41}, {R24,R25}, {R26,R27}"),
    "FMUL2": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R25, 0x3f800000",
         "MOV32I R26, 0x3f800000", "MOV32I R27, 0x3f800000"),
        "FMUL2.F32x2.F32x2 {R40,R41}, {R24,R25}, {R26,R27}"),
    "FFMA2": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R25, 0x3f800000",
         "MOV32I R26, 0x3f800000", "MOV32I R27, 0x3f800000",
         "MOV32I R28, 0", "MOV32I R29, 0"),
        ("FFMA2.F32x2.F32x2.F32x2 {R40,R41}, {R24,R25}, "
         "{R26,R27}, {R28,R29}")),
}


def source(prod_name: str, half: str, consumer: str, coarse: bool) -> str:
    prod = PRODUCERS[prod_name]
    src = "R40" if half == "lo" else "R41"
    consumer_inst = CONSUMERS[consumer].replace("R40", src)
    lines = base.prologue("p2lat")
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
            "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R51;[0:7:{{}}:1:0]",
        ]
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--producer", action="append", choices=tuple(PRODUCERS))
    ap.add_argument("--consumer", action="append", choices=tuple(CONSUMERS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--gaps", default="1,2,3,4,5,6,7,8,12,16")
    ns = ap.parse_args()
    base.GAPS = [int(x) for x in ns.gaps.split(",")]
    print("gaps: " + " ".join(f"{x:2}" for x in base.GAPS))
    for name in ns.producer or list(PRODUCERS):
        for half in ("lo", "hi"):
            for consumer in ns.consumer or list(CONSUMERS):
                for coarse in (False, True):
                    got = base.run_source(source(name, half, consumer, coarse),
                                          "p2lat", ns.reps)
                    pat = base.states(got, base.FRESH, base.POISON)
                    print(f"{name:6} {half} -> {consumer:8} "
                          f"{'coarse' if coarse else 'fine':6} {pat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
