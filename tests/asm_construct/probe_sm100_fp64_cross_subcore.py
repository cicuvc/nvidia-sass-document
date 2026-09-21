#!/usr/bin/env python3
"""B200 one-shot FP64 admission arbitration across subcores.

Actor warps rendezvous immediately before one test instruction.  Per-warp
CS2R timestamps around that instruction expose a one-cycle arbitration delay
which a sustained-throughput span can hide.  ``off`` preserves the DADD
encoding/dispatch path while disabling execution; ``nop`` is the frontend
baseline.
"""

from __future__ import annotations

import argparse
import collections
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.arch import current  # noqa: E402


ACTORS = {
    "one": (0,),
    "diff2": (0, 1),
    "pair02": (0, 2),
    "pair03": (0, 3),
    "diff3": (0, 1, 2),
    "diff4": (0, 1, 2, 3),
}

OPS = {
    "nop": "NOP",
    "off": "@P6 DADD {R40,R41}, {R24,R25}, {R26,R27}",
    "dadd": "DADD {R40,R41}, {R24,R25}, {R26,R27}",
    "dfma": "DFMA {R40,R41}, {R24,R25}, {R26,R27}, {R28,R29}",
}

RAW_GAPS = (1, 2, 3, 4)


def source(actors: tuple[int, ...], op: str) -> str:
    lines = [
        "#fn fp64x(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{0,1}:5:1]",
        "    MOV32I R24, 0x3ff00000;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3ff00000;[7:7:{}:5:1]",
        "    MOV32I R26, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3ff00000;[7:7:{}:5:1]",
        "    MOV32I R29, 0x3ff00000;[7:7:{}:5:1]",
        "    ISETP.F P6, RZ, RZ;[7:7:{}:13:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if actors != tuple(range(max(actors) + 1)):
        for warp in actors:
            lines += [
                f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
                "[7:7:{}:13:1]",
                "    @P0 BRA #label(actor);[7:7:{}:5:1]",
            ]
        lines += ["    BRA #label(done);[7:7:{}:5:1]", "#def_label(actor)"]
    lines += [
        # Counted rendezvous removes path/arrival skew before the measurement.
        f"    BAR.SYNC 1, 0x{len(actors) * 32:x};[7:7:{{}}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:1:0]",
        f"    {OPS[op]};[7:7:{{}}:1:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:1:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:0:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{0}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def raw_source(actors: tuple[int, ...]) -> str:
    """Read DADD's high result half at the solo forwarding boundary."""
    lines = [
        "#fn fp64raw(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{0,1}:5:1]",
        # 1.0 + 1.0 -> high half 0x40000000.  Source A is 0x3ff00000
        # and poison is 0x40100000, so early operand exposure is distinct.
        "    MOV32I R24, 0;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3ff00000;[7:7:{}:5:1]",
        "    MOV32I R26, 0;[7:7:{}:5:1]",
        "    MOV32I R27, 0x3ff00000;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if actors != tuple(range(max(actors) + 1)):
        for warp in actors:
            lines += [
                f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
                "[7:7:{}:13:1]",
                "    @P0 BRA #label(raw_actor);[7:7:{}:5:1]",
            ]
        lines += ["    BRA #label(raw_done);[7:7:{}:5:1]",
                  "#def_label(raw_actor)"]
    for i, gap in enumerate(RAW_GAPS):
        lines += [
            f"    BAR.SYNC 1, 0x{len(actors) * 32:x};[7:7:{{}}:5:1]",
            # Match the established latency probe's producer preamble after
            # rendezvous; placing BAR immediately before DADD changes the
            # coupled scheduling packet and makes every tested gap look safe.
            "    MOV32I R40, 0x40100000;[7:7:{}:15:1]",
            "    MOV32I R41, 0x40100000;[7:7:{}:15:1]",
            "    NOP;[7:7:{}:15:1]",
            "    DADD {R40,R41}, {R24,R25}, {R26,R27};[7:7:{}:1:1]",
        ]
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap - 1)]
        lines += [
            "    IADD3 R50, R41, RZ, RZ;[3:7:{}:8:1]",
            f"    STG.E.32.STRONG.GPU [{{R6,R7}}+0x{4 * i:x}], R50;"
            "[0:7:{3}:1:0]",
        ]
    lines += [
        "#def_label(raw_done)",
        "    EXIT;[7:7:{0}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reps", type=int, default=101)
    p.add_argument("--placements", default=",".join(ACTORS))
    p.add_argument("--ops", default=",".join(OPS))
    p.add_argument("--raw", action="store_true",
                   help="probe result visibility at gaps 1 through 4")
    ns = p.parse_args()
    placements = [x for x in ns.placements.split(",") if x]
    ops = [x for x in ns.ops.split(",") if x]
    if ns.reps <= 0 or any(x not in ACTORS for x in placements):
        p.error("bad repetitions or placement")
    if any(x not in OPS for x in ops):
        p.error("bad op")

    print(f"FP64 cross-subcore one-shot arbitration ({current().name})")
    if ns.raw:
        for placement in placements:
            actors = ACTORS[placement]
            mod = CudaModule(assemble(raw_source(actors), check_deps=True))
            size = (max(actors) + 1) * 32 * 16
            out = mod.devmem_alloc(size)
            samples = {w: [[] for _ in RAW_GAPS] for w in actors}
            try:
                for rep in range(ns.reps + 1):
                    mod.launch("fp64raw", grid=(1,),
                               block=((max(actors) + 1) * 32,), args=[out])
                    mod.synchronize()
                    if rep == 0:
                        continue
                    raw = mod.device_read(out, size)
                    for w in actors:
                        vals = struct.unpack_from("<IIII", raw, w * 32 * 16)
                        for i, value in enumerate(vals):
                            samples[w][i].append(value)
            finally:
                mod.devmem_free(out)
            fields = []
            for w in actors:
                pats = []
                for gap, values in zip(RAW_GAPS, samples[w]):
                    hist = {f"{k:08x}": v for k, v in
                            sorted(collections.Counter(values).items())}
                    pats.append(f"g{gap}={hist}")
                fields.append(f"w{w}:" + ",".join(pats))
            print(f"{placement:5s} raw   " + "  ".join(fields))
        return 0
    for placement in placements:
        actors = ACTORS[placement]
        for op in ops:
            mod = CudaModule(assemble(source(actors, op), check_deps=True))
            size = (max(actors) + 1) * 32 * 16
            out = mod.devmem_alloc(size)
            samples = {w: [] for w in actors}
            starts = {w: [] for w in actors}
            try:
                for rep in range(ns.reps + 1):
                    mod.launch("fp64x", grid=(1,),
                               block=((max(actors) + 1) * 32,), args=[out])
                    mod.synchronize()
                    if rep == 0:
                        continue
                    raw = mod.device_read(out, size)
                    ts = {}
                    for w in actors:
                        t0, t1 = struct.unpack_from("<QQ", raw, w * 32 * 16)
                        samples[w].append((t1 - t0) & ((1 << 64) - 1))
                        ts[w] = t0
                    base = min(ts.values())
                    for w in actors:
                        starts[w].append(ts[w] - base)
            finally:
                mod.devmem_free(out)
            fields = []
            for w in actors:
                hist = dict(sorted(collections.Counter(samples[w]).items()))
                shist = dict(sorted(collections.Counter(starts[w]).items()))
                fields.append(
                    f"w{w}:dt={statistics.median(samples[w]):g}"
                    f" hist={hist} start={shist}")
            print(f"{placement:5s} {op:4s}  " + "  ".join(fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
