#!/usr/bin/env python3
"""Build B200 multi-warp UTCHMMA accumulator-scheduler probes.

Each participating warp owns one legal native tcgen05 epoch: a naked MMA burst,
one UTCBAR, and one private mbarrier.  D tiles are disjoint and 128-column
aligned.  This avoids the unresolved rule for issuing a second MMA epoch after
an in-warp UTCBAR while exposing several independent accumulator contexts to
the SM-level tensor scheduler at once.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _epoch(warp: int, barrier_slot: int, count: int,
           d_indices: list[int], reuse_a: bool,
           accumulate: bool, n: int = 128) -> list[str]:
    idesc = (1 << 4) | (1 << 7) | (1 << 10) | ((n >> 3) << 17) | (8 << 24)
    lines = [
        f"    #def_label(warp{warp}_path)",
        f"    UMOV UR15, {idesc:#x};[7:7:{{}}:1:0]",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    UMOV UR18, {0x600 + 8 * barrier_slot:#x};[7:7:{{}}:5:1]",
    ]
    for i in range(count):
        dreg = 30 + d_indices[i % len(d_indices)]
        modifier = ""
        if reuse_a:
            if i == 0:
                modifier = ".A_KEEP"
            elif i + 1 == count:
                modifier = ".A_REUSE"
            else:
                modifier = ".A_REUSE.A_KEEP"
        lines += [
            f"    UTCHMMA.1CTA{modifier} "
            "gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
            f"tmem[UR{dreg}], tmem[UR14], "
            f"idesc[{{UR15,UR16}}], URZ, "
            f"{'UPT' if accumulate else '!UPT'};[7:0:{{}}:12:1]"
        ]
    lines += [
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
        "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
        "    BRA #label(work_done);[7:7:{1}:5:0]",
    ]
    return lines


def source(name: str, counts: list[int], d_per_warp: int,
           reuse_a: bool, accumulate: bool,
           warp_ids: list[int] | None = None,
           ns: list[int] | None = None) -> str:
    warps = len(counts)
    warp_ids = list(range(warps)) if warp_ids is None else warp_ids
    ns = [128] * warps if ns is None else ns
    if not 1 <= warps <= 4:
        raise ValueError("probe supports one to four issuing warps")
    if len(warp_ids) != warps or len(set(warp_ids)) != warps:
        raise ValueError("warp_ids must be distinct and match counts")
    if len(ns) != warps or any(n not in (8, 16, 32, 64, 128, 256)
                               for n in ns):
        raise ValueError("ns must match counts and contain supported N shapes")
    if min(warp_ids) < 0:
        raise ValueError("warp_ids must be non-negative")
    if not 1 <= d_per_warp <= 4:
        raise ValueError("d_per_warp must be between one and four")
    if any(c < 1 for c in counts):
        raise ValueError("each epoch needs at least one MMA")
    if any(n != 128 for n in ns) and d_per_warp != 1:
        raise ValueError("heterogeneous N probes require d_per_warp=1")
    if all(n == 128 for n in ns):
        d_offsets = [i * d_per_warp * 128 for i in range(warps)]
        total_columns = warps * d_per_warp * 128
    else:
        d_offsets = []
        total_columns = 0
        for n in ns:
            d_offsets.append(total_columns)
            total_columns += max(128, n)
    if total_columns > 512:
        raise ValueError("D tiles exceed the 512-column TMEM allocation")

    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(112)",
        "    #pragma SHARED(0x4000)",
        f"    #pragma NUM_MBARRIERS({warps})",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R8,R9}, R5, 0x10, {R2,R3};[7:7:{0}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_wait);[7:7:{}:5:0]",
        "    #!tmem_alloc_1cta(UR5, 512)",
    ]
    for barrier_slot in range(warps):
        lines += [
            f"    UMOV UR18, {0x600 + 8 * barrier_slot:#x};[7:7:{{}}:1:0]",
            "    #!mbarrier_init(UR18, 1)",
        ]
    lines += [
        "    #def_label(setup_wait)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        "    UMOV UR20, 0x100080;[7:7:{}:1:0]",
        "    UMOV UR21, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR22, 0x100180;[7:7:{}:1:0]",
        "    UMOV UR23, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR14, 0x0;[7:7:{}:1:0]",
        "    UMOV UR15, 0x8200490;[7:7:{}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
    ]
    if all(n == 128 for n in ns):
        reg_offsets = [tile * 128 for tile in range(warps * d_per_warp)]
    else:
        reg_offsets = d_offsets
    for tile, offset in enumerate(reg_offsets):
        lines += [
            f"    UIADD3 UR{30 + tile}, UPT, UPT, UR10, {offset:#x}, "
            "URZ;[7:7:{}:5:1]"
        ]
    lines += [
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for warp in warp_ids:
        lines += [
            f"    ISETP.EQ.AND P1, PT, R5, {warp:#x}, PT;"
            "[7:7:{}:13:1]",
            f"    @P1 BRA #label(warp{warp}_path);[7:7:{{}}:5:0]",
        ]
    lines += ["    BRA #label(work_done);[7:7:{}:5:0]"]
    for barrier_slot, (warp, count, n) in enumerate(
            zip(warp_ids, counts, ns)):
        first = barrier_slot * d_per_warp if all(x == 128 for x in ns) else barrier_slot
        d_indices = list(range(first, first + d_per_warp))
        lines += _epoch(warp, barrier_slot, count, d_indices, reuse_a,
                        accumulate, n)
    lines += [
        "    #def_label(work_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(dealloc_done);[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    #def_label(dealloc_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", default="64",
                    help="comma-separated MMA count for each issuing warp")
    ap.add_argument("--d-per-warp", type=int, choices=range(1, 5), default=1)
    ap.add_argument("--no-collector-reuse", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="set scaleD=0 (!UPT): do not read/accumulate old D")
    ap.add_argument("--warp-ids",
                    help="comma-separated physical warp ids (default 0..N-1)")
    ap.add_argument("--ns",
                    help="comma-separated logical N for each warp (default 128)")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    counts = [int(x, 0) for x in ns.counts.split(",")]
    warp_ids = ([int(x, 0) for x in ns.warp_ids.split(",")]
                if ns.warp_ids else list(range(len(counts))))
    n_shapes = ([int(x, 0) for x in ns.ns.split(",")]
                if ns.ns else [128] * len(counts))
    suffix = "ow" if ns.overwrite else "acc"
    warp_suffix = "_w" + "_".join(str(x) for x in warp_ids)
    n_suffix = "_n" + "_".join(str(x) for x in n_shapes)
    name = (f"utchmma_mw{len(counts)}_d{ns.d_per_warp}_{suffix}"
            f"{warp_suffix}{n_suffix}")
    src = source(name, counts, ns.d_per_warp, not ns.no_collector_reuse,
                 not ns.overwrite, warp_ids, n_shapes)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
