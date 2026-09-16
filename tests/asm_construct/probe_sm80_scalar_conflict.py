#!/usr/bin/env python3
"""Two-warp GA100 scalar-pipe structural-conflict probe.

Warp 0 is the timed victim.  Warp 4 is the same-subcore contender and warp 1
is the different-subcore control (Ampere warp-to-scheduler mapping is warp-id
modulo four).  The source uses the sm70/sm80 direct-parameter address skeleton
rather than the newer scoreboard-sensitive sm90/sm120 harness.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assembler import CudaModule, assemble  # noqa: E402
from probe_subcore_compute_conflict import OPS, Op, body  # noqa: E402


PLACEMENTS = {"solo": None, "same": 4, "different": 1}


def source(a: Op, b: Op, count: int, contender_warp: int | None,
           factor: int, force_reuse: bool = False) -> str:
    lines = [
        "#fn sm80_conf(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    S2R R0, SR_TID.X;[7:7:{}:6:0]",
        "    MOV R6, 0x10;[7:7:{}:6:0]",
        "    IMAD.WIDE.U32 {R2,R3}, R0, R6, c[0x0][0x160];[7:7:{}:6:0]",
        "    SHR R5, R0, 0x5;[7:7:{}:6:0]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:12:1]",
    ]
    if contender_warp is not None:
        lines += [
            f"    ISETP.EQ.AND P1, PT, R5, 0x{contender_warp:x}, PT;"
            "[7:7:{}:12:1]",
        ]
    lines += [
        "    MOV R24, 0x3f803c00;[7:7:{}:6:0]",
        "    MOV R25, 0x3f803c00;[7:7:{}:6:0]",
        "    MOV R26, 0x40003c00;[7:7:{}:6:0]",
        "    MOV R27, 0x40003c00;[7:7:{}:6:0]",
        "    MOV R28, 0x3f003c00;[7:7:{}:6:0]",
        "    MOV R29, 0x3f003c00;[7:7:{}:6:0]",
    ]
    for r in range(40, 80):
        lines.append(f"    MOV R{r}, RZ;[7:7:{{}}:6:0]")
    lines += [
        "    BAR.SYNC 0;[7:7:{}:6:0]",
        "    @P0 BRA #label(victim);[7:7:{}:6:0]",
    ]
    if contender_warp is not None:
        lines += [
            "    @P1 BRA #label(contender);[7:7:{}:6:0]",
        ]
    lines += [
        "    EXIT;[7:7:{}:5:0]",
        "#def_label(victim)",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    def tested_body(op: Op, n: int) -> list[str]:
        if not force_reuse:
            return body(op, n)
        return [f"    {op.instruction(i)};[7:7:{{}}:1:0:7]"
                for i in range(n)]

    lines += tested_body(a, count)
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
    ]
    if contender_warp is not None:
        lines += ["#def_label(contender)"]
        lines += tested_body(b, count * factor)
        lines += ["    EXIT;[7:7:{}:5:0]"]
    lines += ["}"]
    return "\n".join(lines)


def fit(points: list[tuple[int, float]]) -> float:
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    den = sum((x - xm) ** 2 for x, _ in points)
    return sum((x - xm) * (y - ym) for x, y in points) / den


def pair_arg(text: str) -> tuple[str, str]:
    a, b = (x.strip().lower() for x in text.split(",", 1))
    if a not in OPS or b not in OPS:
        raise argparse.ArgumentTypeError(f"unknown pair {text!r}")
    return a, b


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair", action="append", type=pair_arg, required=True)
    ap.add_argument("--counts", default="128,256,512")
    ap.add_argument("--placements", default="solo,same,different")
    ap.add_argument("--factor", type=int, default=4)
    ap.add_argument("--warm", type=int, default=32,
                    help="single-CTA launches used to warm code on many SMs")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--force-reuse", action="store_true",
                    help="mark all A/B/C source slots reusable")
    ns = ap.parse_args()
    counts = [int(x) for x in ns.counts.split(",") if x.strip()]
    placements = [x for x in ns.placements.split(",") if x]
    if set(placements) - set(PLACEMENTS):
        ap.error("bad placement")

    for a_name, b_name in ns.pair:
        slopes = {}
        for placement in placements:
            points = []
            for count in counts:
                cubin = assemble(
                    source(OPS[a_name], OPS[b_name], count,
                           PLACEMENTS[placement], ns.factor,
                           ns.force_reuse),
                    arch="sm80", check_deps=False)
                mod = CudaModule(cubin)
                out = mod.devmem_alloc(256 * 16)
                try:
                    for _ in range(ns.warm):
                        mod.launch("sm80_conf", grid=(1,), block=(256,),
                                   args=[out])
                    mod.synchronize()
                    samples = []
                    for _ in range(ns.reps):
                        mod.launch("sm80_conf", grid=(1,), block=(256,),
                                   args=[out])
                        mod.synchronize()
                        t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                        samples.append(float((t1 - t0) & ((1 << 64) - 1)))
                    best = min(samples)
                    points.append((count, best))
                    print(f"{a_name}<-{b_name},{placement},N={count},"
                          f"cycles={best:.0f}", flush=True)
                finally:
                    mod.devmem_free(out)
            slopes[placement] = fit(points)
        print("FIT," + f"{a_name}<-{b_name}," + ",".join(
            f"{p}={slopes[p]:.6f}" for p in placements), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
