#!/usr/bin/env python3
"""Consumer-specific RAW visibility for sm_120 FMA-Heavy 32-bit results."""

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


PRODUCERS = {
    "FSWZADD": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0"),
        "FSWZADD.NDV R40, R24, R27, PPPPPPPP"),
    "IDP.4A": Producer(
        ("MOV32I R24, 0x01010101", "MOV32I R27, 0x01010101",
         "MOV32I R28, 0x3f7ffffc"),
        "IDP.4A.U8.U8 R40, R24, R27, R28"),
    "IDP.2A": Producer(
        ("MOV32I R24, 0x00010001", "MOV32I R27, 0x00000101",
         "MOV32I R28, 0x3f7ffffe"),
        "IDP.2A.LO.U16.U8 R40, R24, R27, R28"),
    "IMAD": Producer(
        ("MOV32I R24, 0x2", "MOV32I R27, 0x3",
         "MOV32I R28, 0x3f7ffffa"),
        "IMAD R40, R24, R27, R28"),
    "IMUL": Producer(
        ("MOV32I R24, 0x2", "MOV32I R27, 0x1fc00000"),
        "IMUL.U32 R40, R24, R27"),
    "IMUL32I": Producer(
        ("MOV32I R24, 0x1fc00000",),
        "IMUL32I.U32 R40, R24, 0x2"),
}


def source(prod_name: str, consumer: str, coarse: bool) -> str:
    prod = PRODUCERS[prod_name]
    lines = base.prologue("hflat")
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
    if not isolated:
        got = base.run_source(source(prod, consumer, coarse), "hflat", reps)
        return base.states(got, base.FRESH, base.POISON)
    saved = list(base.GAPS)
    out = []
    try:
        for gap in saved:
            base.GAPS = [gap]
            got = base.run_source(source(prod, consumer, coarse), "hflat", reps)
            out.append(base.states(got, base.FRESH, base.POISON)[0])
    finally:
        base.GAPS = saved
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--producer", action="append")
    ap.add_argument("--consumer", action="append", choices=tuple(CONSUMERS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--isolated", action="store_true")
    ap.add_argument("--gaps", default=None)
    ns = ap.parse_args()
    if ns.gaps:
        base.GAPS = [int(x) for x in ns.gaps.split(",")]
    gaps = list(base.GAPS)
    selected = {x.upper() for x in ns.producer} if ns.producer else None
    consumers = ns.consumer or list(CONSUMERS)
    print("gaps: " + " ".join(f"{x:2}" for x in gaps))
    print("\nFMA-Heavy 32-bit GPR result")
    ok = True
    for prod in PRODUCERS:
        if selected and prod.upper() not in selected:
            continue
        for consumer in consumers:
            for coarse in (False, True):
                pat = measure(prod, consumer, coarse, ns.reps, ns.isolated)
                boundary = next((gaps[i] for i in range(len(gaps))
                                 if all(x == "F" for x in pat[i:])), None)
                print(f"{prod:9} -> {consumer:8} "
                      f"{'coarse' if coarse else 'fine':6} {pat} permanent={boundary}")
                ok &= boundary is not None
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
