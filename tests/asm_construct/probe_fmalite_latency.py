#!/usr/bin/env python3
"""Consumer-specific RAW visibility for the sm_120 FMA-Lite leaf."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_alulite_latency as base  # noqa: E402


@dataclass(frozen=True)
class Producer:
    setup: tuple[str, ...]
    inst: str


PRODUCERS = {
    "FADD": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0"),
        "FADD R40, R24, R27"),
    "FADD32I": Producer(
        ("MOV32I R24, 0x3f800000",),
        "FADD32I R40, R24, 0f00000000"),
    "FFMA": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x3f800000",
         "MOV32I R28, 0"),
        "FFMA R40, R24, R27, R28"),
    "FFMA32I": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R28, 0"),
        "FFMA32I R40, R24, 0f3f800000, R28"),
    "FMUL": Producer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x3f800000"),
        "FMUL R40, R24, R27"),
    "FMUL32I": Producer(
        ("MOV32I R24, 0x3f800000",),
        "FMUL32I R40, R24, 0f3f800000"),
    # FHADD/FHFMA consume scalar FP16 values from the selected source halves,
    # but their scalar destination is a full FP32 representation.  These
    # inputs therefore also produce the common fresh marker 0x3f800000.
    "FHADD": Producer(
        ("MOV32I R24, 0x00003c00", "MOV32I R27, 0"),
        "FHADD.F16 R40, R24, R27"),
    "FHFMA": Producer(
        ("MOV32I R24, 0x00003c00", "MOV32I R27, 0x00003c00",
         "MOV32I R28, 0"),
        "FHFMA.F16 R40, R24, R27, R28"),
    "FHADD.BF16": Producer(
        ("MOV32I R24, 0x00003f80", "MOV32I R27, 0"),
        "FHADD.BF16 R40, R24, R27"),
    "FHFMA.BF16": Producer(
        ("MOV32I R24, 0x00003f80", "MOV32I R27, 0x00003f80",
         "MOV32I R28, 0"),
        "FHFMA.BF16 R40, R24, R27, R28"),
}


CONSUMERS = {
    "alulite": "MOV R50, R40",
    "aluheavy": "IADD3 R50, R40, RZ, RZ",
    "fmalite": "FADD R50, R40, RZ",
    # Integer multiply by one preserves all result bits while selecting the
    # FMA-Heavy leaf of the Shared FMA Heavy physical macro.
    "fmaheavy": "IMAD R50, R40, R60, RZ",
    # Packed add-zero preserves the two 16-bit lanes of the probe markers.
    "fp16": "HADD2 R50, R40, RZ",
}


def source(prod_name: str, consumer: str, coarse: bool) -> str:
    prod = PRODUCERS[prod_name]
    lines = base.prologue("flat")
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
        got = base.run_source(source(prod, consumer, coarse), "flat", reps)
        return base.states(got, base.FRESH, base.POISON)
    saved = list(base.GAPS)
    out = []
    try:
        for gap in saved:
            base.GAPS = [gap]
            got = base.run_source(source(prod, consumer, coarse), "flat", reps)
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
    from archutil import arch
    if arch() == "sm90":
        # FHADD/FHFMA are sm_120-only scalar half-precision forms.
        for k in ("FHADD", "FHFMA", "FHADD.BF16", "FHFMA.BF16"):
            PRODUCERS.pop(k, None)
    if ns.gaps:
        base.GAPS = [int(x) for x in ns.gaps.split(",")]
    gaps = list(base.GAPS)
    selected = {x.upper() for x in ns.producer} if ns.producer else None
    consumers = ns.consumer or list(CONSUMERS)
    print("gaps: " + " ".join(f"{x:2}" for x in gaps))
    print("\nFMA-Lite GPR result")
    ok = True
    for prod in PRODUCERS:
        if selected and prod not in selected:
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
