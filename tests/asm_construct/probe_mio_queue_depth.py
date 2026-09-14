#!/usr/bin/env python3
"""Estimate effective MIO queue credits from short-burst absorption.

The XU mode emits active ``MUFU.RCP Rd,RZ`` instructions with unique dead
destinations.  RZ removes late-RF collection demand.  The ending clock read
does not wait for results, so T(N) measures how quickly the frontend/queue can
accept N requests.  Before the queue fills the slope is the issue rate; after
it fills the slope approaches the XU backend drain rate.  The knee/intercept
estimate usable queue credits rather than claiming a physical SRAM depth.
"""

from __future__ import annotations

import argparse
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
    "all8": tuple(range(8)),
}


def source(n: int, mode: str, actors: tuple[int, ...], conflict: int,
           mix_shfl: int = 0) -> str:
    if mode == "xu":
        ops = [f"    MUFU.RCP R{40 + i}, RZ;[7:7:{{}}:1:1]"
               for i in range(n)]
    elif mode == "cbu":
        ops = [f"    BMOV.32 R{40 + i}, MACTIVE;[7:7:{{}}:1:1]"
               for i in range(n)]
    elif mode == "ldg":
        global_step = 128 if conflict <= 1 else 4096
        ops = [f"    LDG.E.STRONG.GPU R{40 + i}, "
               f"[{{R30,R31}}+0x{0x1000 + i * global_step:x}];"
               "[7:7:{}:1:1]"
               for i in range(n)]
    elif mode == "lsu":
        addr = "RZ" if conflict == 0 else "R26"
        ops = [f"    LDS R{40 + i}, [{addr}];[7:7:{{}}:1:1]"
               for i in range(n)]
    elif mode == "lsu128":
        addr = "RZ" if conflict == 0 else "R26"
        # Keep each 128-bit destination quad aligned.  Twenty-four distinct
        # groups are enough to cover the useful short-burst knee without
        # introducing a destination WAW into the measured range.
        ops = []
        for i in range(n):
            r = 40 + 4 * (i % 24)
            ops.append(
                f"    LDS.128 {{R{r},R{r + 1},R{r + 2},R{r + 3}}}, "
                f"[{addr}];[7:7:{{}}:1:1]")
    elif mode == "lsu_shfl_mix":
        # The first long LDS blocks downstream drain.  If SHFL consumes the
        # same request credits, inserting M SHFLs here must advance the knee
        # of the remaining long-LDS burst by approximately M entries.
        ops = []
        if n:
            ops.append("    LDS R40, [R26];[7:7:{}:1:1]")
        ops += [f"    SHFL.BFLY PT, R{80 + i}, RZ, 0x1, 0x1f;"
                "[7:7:{}:1:1]" for i in range(mix_shfl)]
        ops += [f"    LDS R{40 + i}, [R26];[7:7:{{}}:1:1]"
                for i in range(1, n)]
    else:
        raise ValueError(mode)
    lines = [
        "#fn mioburst(out<8>) {",
        "    #pragma MAXREG_COUNT(160)",
        "    #pragma SHARED(4096)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R5, 0x10, {R2,R3};[7:7:{0,1}:5:1]",
        f"    IMAD.WIDE.U32 {{R30,R31}}, R4, "
        f"0x{4 * max(conflict, 1):x}, {{R2,R3}};"
        "[7:7:{0,1}:5:1]",
        "    LOP3.LUT R26, R4, 0x1f, RZ, 0xc0;[7:7:{1}:5:1]",
        f"    IMAD.U32 R26, R26, 0x{(16 if mode == 'lsu128' else 4) * max(conflict, 1):x}, RZ;"
        "[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    all_warps = actors == tuple(range(max(actors) + 1))
    if all_warps:
        lines += ["    BRA #label(work);[7:7:{}:5:1]"]
    elif actors == (0, 4):
        # Select warp_id % 4 == 0 with one identical-length path for every
        # warp, avoiding the large warp-0/warp-4 skew of a comparison chain.
        lines += [
            "    LOP3.LUT R8, R5, 0x3, RZ, 0xc0;[7:7:{}:5:1]",
            "    ISETP.EQ.AND P0, PT, R8, RZ, PT;[7:7:{}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:5:1]",
            "    BRA #label(done);[7:7:{}:5:1]",
        ]
    else:
        for w in actors:
            lines += [
                f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;[7:7:{{}}:13:1]",
                "    @P0 BRA #label(work);[7:7:{}:5:1]",
            ]
        lines += ["    BRA #label(done);[7:7:{}:5:1]"]
    lines += [
        "#def_label(work)",
        "    NOP;[7:7:{}:8:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *ops,
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:0:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",
                   choices=("xu", "cbu", "ldg", "lsu", "lsu128",
                            "lsu_shfl_mix"),
                   default="xu")
    p.add_argument("--actors", choices=ACTORS, default="one")
    p.add_argument("--conflict", type=int, choices=(0, 1, 2, 4, 8, 16, 32),
                   default=0, help=(
                       "LDS address stride: scalar gives that conflict degree; "
                       "LDS.128 gives 2 merged wavefronts for 0, otherwise "
                       "4*stride wavefronts"))
    p.add_argument("--counts", default="0-32",
                   help="inclusive range A-B or comma-separated counts")
    p.add_argument("--mix-shfl", type=int, default=0,
                   help="SHFL requests inserted after the first long LDS")
    p.add_argument("--reps", type=int, default=9)
    ns = p.parse_args()
    if "-" in ns.counts:
        lo, hi = (int(x) for x in ns.counts.split("-", 1))
        counts = list(range(lo, hi + 1))
    else:
        counts = [int(x) for x in ns.counts.split(",") if x.strip()]
    if (not counts or min(counts) < 0 or max(counts) > 100 or ns.reps <= 0
            or ns.mix_shfl < 0 or ns.mix_shfl > 40):
        p.error("counts must be 0..100, mix-shfl 0..40, and reps positive")
    actors = ACTORS[ns.actors]
    print(f"mode={ns.mode} actors={ns.actors} conflict={ns.conflict} "
          f"mix_shfl={ns.mix_shfl}")
    print("N span_median min max delta")
    previous = None
    for n in counts:
        out_size = (max(actors) + 1) * 16
        if ns.mode == "ldg":
            global_step = 128 if ns.conflict <= 1 else 4096
            out_size = max(out_size, 0x1000 + n * global_step
                           + (max(actors) + 1) * 32
                           * 4 * max(ns.conflict, 1))
        mod = CudaModule(assemble(
            source(n, ns.mode, actors, ns.conflict, ns.mix_shfl),
            check_deps=True))
        out = mod.devmem_alloc(out_size)
        vals = []
        try:
            for _ in range(ns.reps + 1):
                mod.launch("mioburst", grid=(1,),
                           block=((max(actors) + 1) * 32,), args=[out])
                mod.synchronize()
                raw = mod.device_read(out, out_size)
                times = [struct.unpack_from("<QQ", raw, w * 16)
                         for w in actors]
                vals.append(max(t1 for _, t1 in times) -
                            min(t0 for t0, _ in times))
        finally:
            mod.devmem_free(out)
        med = statistics.median(vals[1:])
        delta = "-" if previous is None else f"{med - previous:g}"
        print(f"{n:2d} {med:6g} {min(vals[1:]):3d} {max(vals[1:]):3d} {delta}")
        previous = med
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
