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
                use_sentinel: bool = True,
                sentinel_mode: str = "fmalite") -> tuple[str, int]:
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
    sentinel_ops = {
        "fmalite": "FFMA R30, RZ, RZ, R31",
        "fmaheavy": "IMAD R30, RZ, RZ, R31",
        "alulite": "IADD R30, PT, RZ, R31",
        "aluheavy": "IADD3 R30, RZ, RZ, R31",
    }
    if sentinel_mode not in sentinel_ops:
        raise ValueError(f"invalid sentinel mode: {sentinel_mode}")
    sentinel = sentinel_ops[sentinel_mode]
    marker0 = ([
        f"    {sentinel};[7:7:{{}}:13:1]",
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
        f"    {sentinel};[7:7:{{}}:13:1]",
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


def concurrent_source(prefix_count: int, marker_delay: int,
                      marker_mode: str) -> tuple[str, int]:
    """ALU fillers on warps 0/4; a visible marker on warps 8/12."""
    marker_ops = {
        "fmaheavy": "IMAD R30, RZ, RZ, R31",
        "alulite": "IADD R30, PT, RZ, R31",
    }
    marker = marker_ops[marker_mode]
    lines = [
        "#fn concurrenttopology(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(8)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    MOV32I R31, 0x3f800000;[7:7:{}:5:1]",
        "    STS [RZ], RZ;[7:7:{}:5:1]",
        "    STS [RZ+0x4], RZ;[7:7:{}:5:1]",
        "    MEMBAR.ALL.CTA;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for warp, label in ((0, "filler"), (4, "filler"),
                        (8, "marker0"), (12, "marker1"),
                        (1, "observer")):
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
            "[7:7:{}:13:1]",
            f"    @P0 BRA #label({label});[7:7:{{}}:5:1]",
        ]
    lines += [
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(filler)",
        "    BAR.SYNC 2, 0xa0;[7:7:{}:5:1]",
    ]
    lines += ["    IADD3 RZ, RZ, RZ, RZ;[7:7:{}:1:0:7]"
              for _ in range(prefix_count)]
    lines += [
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(marker0)",
        "    BAR.SYNC 2, 0xa0;[7:7:{}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(marker_delay)]
    lines += [
        f"    {marker};[7:7:{{}}:13:1]",
        "    STS [RZ], R30;[7:7:{}:1:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(marker1)",
        "    BAR.SYNC 2, 0xa0;[7:7:{}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(marker_delay)]
    lines += [
        f"    {marker};[7:7:{{}}:13:1]",
        "    STS [RZ+0x4], R30;[7:7:{}:1:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(observer)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    BAR.SYNC 2, 0xa0;[7:7:{}:5:1]",
        "#def_label(cpoll)",
        "    LDS R11, [RZ];[2:7:{}:1:0]",
        "    ISETP.NE.AND P1, PT, R11, RZ, PT;[7:7:{2}:13:1]",
        "    @!P1 BRA #label(cpoll);[7:7:{}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines), 416


@app.local_entrypoint()
def concurrent(prefix_counts: str = "0-20", marker_delays: str = "0-12",
               marker_modes: str = "fmaheavy,alulite",
               repetitions: int = 7) -> None:
    from assembler import assemble

    counts = parse_counts(prefix_counts)
    delays = parse_counts(marker_delays)
    modes = parse_csv(marker_modes)
    if (not counts or not delays or not modes or min(counts + delays) < 0
            or max(counts) > 100 or max(delays) > 64
            or any(mode not in {"fmaheavy", "alulite"} for mode in modes)):
        raise ValueError("invalid concurrent-probe arguments")
    cases = []
    for mode in modes:
        for count in counts:
            for delay in delays:
                src, block = concurrent_source(count, delay, mode)
                cubin = assemble(src, arch="sm100a", check_deps=True)
                label = f"{mode}:A={count}:D={delay}"
                cases.append((label, cubin, "concurrenttopology",
                              block, 16, (0,)))
    result_map = dict(run_cases.remote(cases, repetitions))
    for mode in modes:
        print(f"marker={mode}")
        print(f"A={','.join(map(str, counts))}")
        for delay in delays:
            values = [statistics.median(
                result_map[f"{mode}:A={count}:D={delay}"])
                      for count in counts]
            base = values[0]
            print(f"delay={delay:2d} base={base:g} "
                  f"dA={','.join(f'{v - base:g}' for v in values)}")


@app.local_entrypoint()
def topology(pairs: str = "aluheavy:fmaheavy",
             a_counts: str = "0,5,8,12,16",
             b_counts: str = "0-16", c_counts: str = "0",
             observer_delays: str = "0", repetitions: int = 7,
             active: bool = False, producer_delay: int = 12,
             marker_warp: int = 0, use_sentinel: bool = True,
             sentinel_mode: str = "fmalite") -> None:
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
                            marker_warp, use_sentinel, sentinel_mode)
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
