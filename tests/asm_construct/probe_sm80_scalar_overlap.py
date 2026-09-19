#!/usr/bin/env python3
"""Measure GA100 scalar-pipe throughput and cross-pipe overlap.

This deliberately uses the old sm70/sm80 timer/address skeleton from
probe_v100_rf_banks.py.  The newer sm90/sm120 structural-conflict harness has
scoreboard/control assumptions that are not valid for an Ampere cubin.
"""

from __future__ import annotations

import argparse
import os
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


# Every tuple is one repeated unit.  Sources are parity balanced and marked
# reusable so that the two-cycle GA100 execution floor, rather than RF bank
# collection, is exposed.  Destinations are substituted independently.
CASES: dict[str, tuple[str, ...]] = {
    "nop": ("NOP",),
    "mov": ("MOV R{d}, R4",),
    "iadd": ("IADD R{d}, PT, R4, R9",),
    "iadd3": ("IADD3 R{d}, R4, R9, R8",),
    "lop3": ("LOP3.LUT R{d}, R4, R9, R8, 0x96",),
    "imad": ("IMAD R{d}, R4, R9, R8",),
    "ffma": ("FFMA R{d}, R4, R9, R8",),
    "fadd": ("FADD R{d}, R4, R9",),
    "iadd_imad": (
        "IADD R{d}, PT, R4, R9",
        "IMAD R{d2}, R4, R9, R8",
    ),
    "mov_imad": (
        "MOV R{d}, R4",
        "IMAD R{d2}, R4, R9, R8",
    ),
    "iadd_ffma": (
        "IADD R{d}, PT, R4, R9",
        "FFMA R{d2}, R4, R9, R8",
    ),
    "lop3_imad": (
        "LOP3.LUT R{d}, R4, R9, R8, 0x96",
        "IMAD R{d2}, R4, R9, R8",
    ),
    "ffma_imad": (
        "FFMA R{d}, R4, R9, R8",
        "IMAD R{d2}, R4, R9, R8",
    ),
    "fadd_imad": (
        "FADD R{d}, R4, R9",
        "IMAD R{d2}, R4, R9, R8",
    ),
    "iadd_iadd": (
        "IADD R{d}, PT, R4, R9",
        "IADD R{d2}, PT, R4, R9",
    ),
    "imad_imad": (
        "IMAD R{d}, R4, R9, R8",
        "IMAD R{d2}, R4, R9, R8",
    ),
    "ffma_ffma": (
        "FFMA R{d}, R4, R9, R8",
        "FFMA R{d2}, R4, R9, R8",
    ),
}


def source(case: str, count: int) -> str:
    unit = CASES[case]
    lines = [
        f"#fn sm80_{case}(out<8>) {{",
        "    #pragma MAXREG_COUNT(96)",
        "    S2R R0, SR_CTAID.X;[7:7:{}:6:0]",
        # Keep the old-architecture probe independent of undocumented S2R
        # fixed latency.  A late CTAID write would make different CTAs alias
        # timestamp records and fabricate non-monotonic deltas.
        *["    NOP;[7:7:{}:6:0]" for _ in range(32)],
        "    MOV R6, 0x10;[7:7:{}:6:0]",
        # This exact address sequence is probe-verified on the A100.  Ampere
        # kernel parameters begin at c[0][0x160].
        "    IMAD.WIDE.U32 {R2,R3}, R0, R6, c[0x0][0x160];[7:7:{}:6:0]",
        "    MOV R4, 0x3f800000;[7:7:{}:6:0]",
        "    MOV R8, 0x3f000000;[7:7:{}:6:0]",
        "    MOV R9, 0x40000000;[7:7:{}:6:0]",
    ]
    for r in range(40, 80):
        lines.append(f"    MOV R{r}, RZ;[7:7:{{}}:6:0]")
    lines += [
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    inst_index = 0
    for _ in range(count):
        for inst in unit:
            d = 40 + inst_index % 40
            d2 = 40 + (inst_index + 1) % 40
            reuse = 0 if inst == "NOP" else 7
            lines.append(
                f"    {inst.format(d=d, d2=d2)};[7:7:{{}}:1:0:{reuse}]"
                if reuse else "    NOP;[7:7:{}:1:0]")
            inst_index += 1
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def fit(points: list[tuple[int, float]]) -> tuple[float, float]:
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    den = sum((x - xm) ** 2 for x, _ in points)
    slope = sum((x - xm) * (y - ym) for x, y in points) / den
    return slope, ym - slope * xm


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--counts", default="128,256,512,1024")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--grid", type=int, default=108,
                    help="CTA count; default covers all 108 A100 SMs so the "
                         "measured launch does not land on a cold I-cache")
    ns = ap.parse_args()
    cases = [x.strip() for x in ns.cases.split(",") if x.strip()]
    counts = [int(x) for x in ns.counts.split(",") if x.strip()]
    bad = set(cases) - set(CASES)
    if bad:
        ap.error(f"unknown cases: {sorted(bad)}")
    if (len(counts) < 2 or min(counts) <= 0 or ns.reps <= 0 or
            ns.grid <= 0):
        ap.error("need at least two positive counts and positive reps/grid")

    for case in cases:
        points: list[tuple[int, float]] = []
        for count in counts:
            cubin = assemble(source(case, count), arch=os.environ.get("PROBE_ARCH", "sm80"),
                             check_deps=False)
            mod = CudaModule(cubin)
            out = mod.devmem_alloc(ns.grid * 16)
            try:
                # Each CTA writes its own timestamp pair.  A full-SM launch
                # makes the following repetitions hot on every instruction
                # cache rather than depending on which SM receives one CTA.
                mod.launch(f"sm80_{case}", grid=(ns.grid,), block=(1,),
                           args=[out])
                mod.synchronize()
                samples = []
                for _ in range(ns.reps):
                    mod.launch(f"sm80_{case}", grid=(ns.grid,), block=(1,),
                               args=[out])
                    mod.synchronize()
                    raw = mod.device_read(out, ns.grid * 16)
                    cta_samples = []
                    for off in range(0, len(raw), 16):
                        t0, t1 = struct.unpack_from("<QQ", raw, off)
                        cta_samples.append(
                            float((t1 - t0) & ((1 << 64) - 1)))
                    # A rare late CTAID read can alias one record.  Use the
                    # launch median to reject isolated bad slots, then the
                    # minimum across hot launches as in the older RF probe.
                    samples.append(statistics.median(cta_samples))
                best = min(samples)
                points.append((count, best))
                print(f"{case},N={count},cycles={best:.0f}", flush=True)
            finally:
                mod.devmem_free(out)
        slope, intercept = fit(points)
        print(f"FIT,{case},cycles_per_unit={slope:.6f},"
              f"intercept={intercept:.3f},insts_per_unit={len(CASES[case])}",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
