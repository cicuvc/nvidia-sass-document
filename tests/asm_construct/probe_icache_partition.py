#!/usr/bin/env python3
"""Use disjoint per-warp loops to determine GB202 I-cache sharing scope."""

from __future__ import annotations

import argparse
import math
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


ACTORS = {
    "one": (0,),
    "same2": (0, 4),
    "diff2": (0, 1),
    "diff4": (0, 1, 2, 3),
}


def source(actors: tuple[int, ...], nops: int, iterations: int) -> str:
    lines = [
        "#fn icpart(out<8>) {",
        "    #pragma MAXREG_COUNT(32)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
    ]
    for warp in actors:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
            "[7:7:{}:13:1]",
            f"    @P0 BRA #label(path_{warp});[7:7:{{}}:6:0]",
        ]
    lines += ["    BRA #label(done);[7:7:{}:6:0]"]
    for path_index, warp in enumerate(actors):
        start = 12 + path_index * 4
        end = start + 2
        lines += [
            f"    #def_label(path_{warp})",
            f"    MOV32I R10, 0x{iterations:x};[7:7:{{}}:5:1]",
            f"    CS2R {{R{start},R{start + 1}}}, SR_CLOCKLO;"
            "[7:7:{}:5:0]",
            f"    #def_label(loop_{warp})",
        ]
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(nops)]
        lines += [
            "    IADD3 R10, R10, -0x1, RZ;[7:7:{}:5:1]",
            "    ISETP.NE.AND P0, PT, R10, RZ, PT;[7:7:{}:13:1]",
            f"    @P0 BRA #label(loop_{warp});[7:7:{{}}:6:0]",
            f"    CS2R {{R{end},R{end + 1}}}, SR_CLOCKLO;"
            "[7:7:{}:5:0]",
            *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
            f"    STG.E.64.STRONG.GPU [{{R6,R7}}], "
            f"{{R{start},R{start + 1}}};[7:1:{{}}:8:0]",
            f"    STG.E.64.STRONG.GPU [{{R6,R7}}+8], "
            f"{{R{end},R{end + 1}}};[7:1:{{}}:8:0]",
            "    BRA #label(done);[7:7:{}:6:0]",
        ]
    lines += ["    #def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--actors", choices=ACTORS, required=True)
    p.add_argument("--path-kib", type=float, required=True)
    p.add_argument("--total-nops", type=int, default=1 << 19)
    p.add_argument("--min-iters", type=int, default=16)
    p.add_argument("--reps", type=int, default=5)
    ns = p.parse_args()
    if min(ns.path_kib, ns.total_nops, ns.min_iters, ns.reps) <= 0:
        p.error("all numeric arguments must be positive")

    actors = ACTORS[ns.actors]
    nops = max(1, int(round(ns.path_kib * 1024)) // 16 - 3)
    loop_bytes = (nops + 3) * 16
    iterations = max(ns.min_iters, math.ceil(ns.total_nops / nops))
    mod = CudaModule(assemble(source(actors, nops, iterations),
                              check_deps=True))
    block_threads = (max(actors) + 1) * 32
    out_size = block_threads * 16
    out = mod.devmem_alloc(out_size)
    samples = {warp: [] for warp in actors}
    spans = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("icpart", grid=(1,), block=(block_threads,), args=[out])
            mod.synchronize()
            if rep:
                raw = mod.device_read(out, out_size)
                starts, ends = [], []
                for warp in actors:
                    t0, t1 = struct.unpack_from("<QQ", raw,
                                                warp * 32 * 16)
                    samples[warp].append((t1 - t0) & ((1 << 64) - 1))
                    starts.append(t0)
                    ends.append(t1)
                spans.append(max(ends) - min(starts))
    finally:
        mod.devmem_free(out)

    med = {warp: statistics.median(vals) / (iterations * nops)
           for warp, vals in samples.items()}
    dynamic_nops = len(actors) * iterations * nops
    aggregate = dynamic_nops / statistics.median(spans)
    print(f"actors={ns.actors} path_bytes={loop_bytes} iterations={iterations} "
          f"cycles/NOP={med} aggregate_NOP/cycle={aggregate:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
