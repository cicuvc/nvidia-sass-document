#!/usr/bin/env python3
"""Distinguish shared-exclusive from per-domain B200 scalar queues.

Unlike the counted-BAR probe, completion is marked by producer STS flags.
The clean-subcore observer timestamps when both stores become visible.  This
is intended to observe issue/admission progress without draining the fixed
pipelines at the measurement boundary.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path


HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT))

from probe_sm100_scalar_admission_modal import (  # noqa: E402
    BARRIER_OPS,
    app,
    parse_counts,
    parse_csv,
    run_cases,
)


def flag_source(segments: list[tuple[str, int]], active: bool = False,
                producer_delay: int = 12, observer_delay: int = 0,
                marker_warp: int = 0,
                use_sentinel: bool = True) -> tuple[str, int]:
    """Return a two-producer burst with a non-draining shared flag marker."""
    ops = []
    for mode, count in segments:
        op = BARRIER_OPS[mode]
        if active:
            op = op.removeprefix("@P6 ")
        ops += [f"    {op};[7:7:{{}}:1:0:7]" for _ in range(count)]

    lines = [
        "#fn queuetopology(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(8)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    MOV32I R10, 0x1;[7:7:{}:5:1]",
        "    MOV32I R31, 0x3f800000;[7:7:{}:5:1]",
        "    STS [RZ], RZ;[7:7:{}:5:1]",
        "    STS [RZ+0x4], RZ;[7:7:{}:5:1]",
        "    MEMBAR.ALL.CTA;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.F P6, RZ, RZ;[7:7:{}:13:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(producer0);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(producer1);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, 0x1, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(observer);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(producer0)",
        "    BAR.SYNC 2, 0x60;[7:7:{}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(producer_delay)]
    lines += ops
    marker0 = ([
        "    FFMA R30, RZ, RZ, R31;[7:7:{}:13:1]",
        "    STS [RZ], R30;[7:7:{}:1:0]",
    ] if use_sentinel else ["    STS [RZ], R10;[7:7:{}:1:0]"])
    lines += marker0
    lines += [
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(producer1)",
        "    BAR.SYNC 2, 0x60;[7:7:{}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(producer_delay)]
    lines += ops
    marker1 = ([
        "    FFMA R30, RZ, RZ, R31;[7:7:{}:13:1]",
        "    STS [RZ+0x4], R30;[7:7:{}:1:0]",
    ] if use_sentinel else ["    STS [RZ+0x4], R10;[7:7:{}:1:0]"])
    lines += marker1
    lines += [
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(observer)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    BAR.SYNC 2, 0x60;[7:7:{}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:0]" for _ in range(observer_delay)]
    marker_offset = 0 if marker_warp == 0 else 4
    lines += [
        "#def_label(poll)",
        f"    LDS R11, [RZ+0x{marker_offset:x}];[2:7:{{}}:1:0]",
        "    ISETP.NE.AND P1, PT, R11, RZ, PT;[7:7:{2}:13:1]",
        "    @!P1 BRA #label(poll);[7:7:{}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines), 160


@app.local_entrypoint()
def topology(pairs: str = "aluheavy:fmaheavy",
             a_counts: str = "0,5,8,12,16",
             b_counts: str = "0-16", c_counts: str = "0",
             observer_delays: str = "0", repetitions: int = 7,
             active: bool = False, producer_delay: int = 12,
             marker_warp: int = 0, use_sentinel: bool = True) -> None:
    from assembler import assemble

    selected_pairs = []
    for item in parse_csv(pairs):
        names = item.split(":", 1)
        if len(names) != 2 or any(name not in BARRIER_OPS for name in names):
            raise ValueError(f"invalid pair: {item!r}")
        selected_pairs.append(tuple(names))
    ac = parse_counts(a_counts)
    bc = parse_counts(b_counts)
    cc = parse_counts(c_counts)
    od = parse_counts(observer_delays)
    if (not selected_pairs or not ac or not bc or not cc
            or not od or min(ac + bc + cc + od) < 0
            or max(ac + bc + cc) > 100 or max(od) > 64
            or repetitions <= 0 or not 0 <= producer_delay <= 64
            or marker_warp not in {0, 4}):
        raise ValueError("invalid counts or repetitions")

    cases = []
    for first, second in selected_pairs:
        for a in ac:
            for b in bc:
                for c in cc:
                    for delay in od:
                        segments = [(first, a), (second, b), (first, c)]
                        src, block = flag_source(
                            segments, active, producer_delay, delay,
                            marker_warp, use_sentinel)
                        cubin = assemble(src, arch="sm100a", check_deps=True)
                        label = (f"{first}:{second}:A={a}:B={b}:C={c}:"
                                 f"D={delay}")
                        cases.append((label, cubin, "queuetopology",
                                      block, 16, (0,)))

    result_map = dict(run_cases.remote(cases, repetitions))
    for first, second in selected_pairs:
        print(f"pair={first}->{second} active={active}")
        for c in cc:
            print(f"C={c} B={','.join(map(str, bc))}")
            for a in ac:
                medians = []
                for b in bc:
                    by_phase = []
                    for delay in od:
                        label = (f"{first}:{second}:A={a}:B={b}:C={c}:"
                                 f"D={delay}")
                        by_phase.append(statistics.median(result_map[label]))
                    medians.append(min(by_phase))
                base = medians[0]
                delta = [value - base for value in medians]
                print(f"A={a:2d} base={base:g} "
                      f"dB={','.join(f'{x:g}' for x in delta)}")
        if len(cc) > 1:
            print(f"C={','.join(map(str, cc))}")
            for a in ac:
                for b in bc:
                    medians = []
                    for c in cc:
                        by_phase = []
                        for delay in od:
                            label = (f"{first}:{second}:A={a}:B={b}:C={c}:"
                                     f"D={delay}")
                            by_phase.append(
                                statistics.median(result_map[label]))
                        medians.append(min(by_phase))
                    base = medians[0]
                    delta = [value - base for value in medians]
                    print(f"A={a:2d} B={b:2d} base={base:g} "
                          f"dC={','.join(f'{x:g}' for x in delta)}")


if __name__ == "__main__":
    print("Run with: modal run probe_sm100_scalar_queue_topology_modal.py::topology")
