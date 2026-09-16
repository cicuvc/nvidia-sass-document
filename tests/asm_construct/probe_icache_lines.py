#!/usr/bin/env python3
"""Probe GB202 instruction-cache capacity as a count of 128-byte lines.

The hot loop visits one instruction in every 128-byte-aligned code block. The
blocks are traversed in a deterministic shuffled order, defeating sequential
fall-through while retaining an exactly known number of resident cache lines.
All seven other instruction slots in a normal block are unreachable padding.
"""

from __future__ import annotations

import argparse
import random
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(nlines: int, iterations: int) -> str:
    order = list(range(1, nlines - 1))
    random.Random(0x1CAC4E).shuffle(order)
    order = [0, *order, nlines - 1]
    successor = dict(zip(order, order[1:]))

    # Eight preamble instructions make block_0 begin on a 128-byte boundary.
    lines = [
        "#fn iclines(out<8>) {",
        "    #pragma MAXREG_COUNT(32)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        f"    MOV32I R10, 0x{iterations:x};[7:7:{{}}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:1:1]",
        "    NOP;[7:7:{}:1:1]",
        "    NOP;[7:7:{}:1:1]",
    ]
    for block in range(nlines):
        lines.append(f"    #def_label(block_{block})")
        if block == nlines - 1:
            lines += [
                "    IADD3 R10, R10, -0x1, RZ;[7:7:{}:5:1]",
                "    ISETP.NE.AND P0, PT, R10, RZ, PT;[7:7:{}:13:1]",
                "    @P0 BRA #label(block_0);[7:7:{}:6:0]",
                *["    NOP;[7:7:{}:1:1]" for _ in range(5)],
            ]
        else:
            lines += [
                f"    BRA #label(block_{successor[block]});[7:7:{{}}:6:0]",
                *["    NOP;[7:7:{}:1:1]" for _ in range(7)],
            ]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R22,R23};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lines", default="480,496,500,504,508,512,516,528,544")
    p.add_argument("--iterations", type=int, default=64)
    p.add_argument("--reps", type=int, default=5)
    ns = p.parse_args()
    counts = [int(x) for x in ns.lines.split(",") if x.strip()]
    if (not counts or min(counts) <= 1 or ns.iterations <= 1
            or ns.reps <= 0):
        p.error("line counts and iterations must exceed one; reps must be positive")

    print("lines bytes iterations median_cycles cycles_per_line")
    for nlines in counts:
        mod = CudaModule(assemble(source(nlines, ns.iterations),
                                  check_deps=True))
        out = mod.devmem_alloc(16)
        samples = []
        try:
            for rep in range(ns.reps + 1):
                mod.launch("iclines", grid=(1,), block=(32,), args=[out])
                mod.synchronize()
                if rep:
                    raw = mod.device_read(out, 16)
                    t0, t1 = struct.unpack("<QQ", raw)
                    samples.append((t1 - t0) & ((1 << 64) - 1))
        finally:
            mod.devmem_free(out)
        cycles = statistics.median(samples)
        print(f"{nlines} {nlines * 128} {ns.iterations} {cycles:g} "
              f"{cycles / (ns.iterations * nlines):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
