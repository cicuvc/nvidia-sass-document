#!/usr/bin/env python3
"""RAW visibility of sm_120 FMA-Heavy HI/WIDE GPR and predicate results."""

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
    lo: int
    hi: int | None


# Every architectural output differs from Ra=2 and from the poison value.
# The addends are chosen so that the final WIDE pair is
# 0x2468ace0_3f800000; HI produces 0x3f800000.
PRODUCERS = {
    "IMAD.WIDE": Producer(
        ("MOV32I R24, 0x2", "MOV32I R27, 0x3",
         "MOV32I R28, 0x3f7ffffa", "MOV32I R29, 0x2468ace0"),
        "IMAD.WIDE.U32 {R40,R41}, P0, R24, R27, {R28,R29}",
        0x3F800000, 0x2468ACE0),
    "IMAD.HI": Producer(
        ("MOV32I R24, 0x2", "MOV32I R27, 0x3",
         "MOV32I R28, 0", "MOV32I R29, 0x3f800000"),
        "IMAD.HI R40, P0, R24, R27, {R28,R29}",
        0x3F800000, None),
    "IMUL32I.WIDE": Producer(
        ("MOV32I R24, 0x1fc00000",),
        "IMUL32I.WIDE.U32 {R40,R41}, P0, R24, 0x2",
        0x3F800000, 0),
}


def source(prod_name: str, half: str, consumer: str, coarse: bool) -> str:
    prod = PRODUCERS[prod_name]
    src = "R41" if half == "hi" else "R40"
    lines = base.prologue("hwide")
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
            f"    {CONSUMERS[consumer].replace('R40', src)};[3:7:{{}}:8:1]",
            "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R51;[0:7:{{}}:1:0]",
        ]
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def pred_source(prod_name: str, consumer: str, initial: int, final: int,
                coarse: bool) -> str:
    prod = PRODUCERS[prod_name]
    lines = base.prologue("hpred")
    for i, gap in enumerate(base.GAPS):
        lines.append(f"    MOV32I R30, 0x{initial:x};[7:7:{{}}:8:1]")
        lines += [
            "    R2P PR, R30, 0x1;[7:7:{}:13:1]",
            "    NOP;[7:7:{}:15:1]",
            "    MOV32I R30, 0x1;[7:7:{}:8:1]",
            "    MOV32I R32, 0x2;[7:7:{}:8:1]",
            f"    MOV32I R50, 0x{base.STALE_MARK:08x};[7:7:{{}}:8:1]",
        ]
        for inst in prod.setup:
            lines.append(f"    {inst};[7:7:{{}}:8:1]")
        lines += [
            f"    {prod.inst};[7:7:{{}}:1:1]",
        ]
        lines += base.filler(gap, coarse)
        if consumer == "p2r":
            lines += [
                "    P2R R50, PR, RZ, 0x1;[3:7:{}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            ]
        elif consumer == "selector":
            lines += [
                "    SEL R50, R30, R32, P0;[3:7:{}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            ]
        elif consumer == "guard":
            guard = "@P0" if final else "@!P0"
            lines += [
                f"    {guard} MOV32I R50, 0x{base.FRESH_MARK:08x};[3:7:{{}}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            ]
        elif consumer == "branch":
            guard = "@P0" if final else "@!P0"
            t, d = f"true{i}", f"done{i}"
            lines += [
                f"    {guard} BRA #label({t});[7:7:{{}}:5:1]",
                f"    MOV32I R51, 0x{base.STALE_MARK:08x};[7:7:{{}}:5:1]",
                f"    BRA #label({d});[7:7:{{}}:5:1]",
                f"    #def_label({t})",
                f"    MOV32I R51, 0x{base.FRESH_MARK:08x};[7:7:{{}}:5:1]",
                f"    #def_label({d})",
            ]
        else:
            raise ValueError(consumer)
        lines.append(
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R51;[0:7:{{}}:1:0]")
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def run_one(src: str, fn: str, reps: int) -> list[tuple[int, ...]]:
    return base.run_source(src, fn, reps)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--producer", action="append", choices=tuple(PRODUCERS))
    ap.add_argument("--consumer", action="append", choices=tuple(CONSUMERS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--gaps", default="1,2,3,4,5,6,7,8,12,16")
    ns = ap.parse_args()
    base.GAPS = [int(x) for x in ns.gaps.split(",")]
    selected = ns.producer or list(PRODUCERS)
    consumers = ns.consumer or list(CONSUMERS)
    print("gaps: " + " ".join(f"{x:2}" for x in base.GAPS))
    for name in selected:
        prod = PRODUCERS[name]
        for half, final in (("lo", prod.lo), ("hi", prod.hi)):
            if final is None:
                continue
            for consumer in consumers:
                for coarse in (False, True):
                    got = run_one(source(name, half, consumer, coarse),
                                  "hwide", ns.reps)
                    pat = base.states(got, final, base.POISON)
                    print(f"{name:13} {half} -> {consumer:8} "
                          f"{'coarse' if coarse else 'fine':6} {pat}")
        # First calibrate the architectural Pu value at the largest gap, then
        # rerun with the inverse initial predicate to expose its RAW boundary.
        old = list(base.GAPS)
        base.GAPS = [max(old)]
        final_p = run_one(pred_source(name, "p2r", 0, 0, False),
                          "hpred", ns.reps)[0][0] & 1
        base.GAPS = old
        initial = final_p ^ 1
        for consumer in ("selector", "p2r", "guard", "branch"):
            if consumer == "selector":
                fresh, stale = (1 if final_p else 2), (1 if initial else 2)
            elif consumer == "p2r":
                fresh, stale = final_p, initial
            else:
                fresh, stale = base.FRESH_MARK, base.STALE_MARK
            for coarse in (False, True):
                got = run_one(pred_source(name, consumer, initial, final_p,
                                          coarse), "hpred", ns.reps)
                pat = base.states(got, fresh, stale)
                print(f"{name:13} Pu -> {consumer:8} "
                      f"{'coarse' if coarse else 'fine':6} {pat} final={final_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
