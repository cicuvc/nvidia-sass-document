#!/usr/bin/env python3
"""Sweep a repeated SASS loop to expose GB202 instruction-cache capacities.

Each generated NOP is a real 16-byte SASS instruction.  The loop-control tail
adds three instructions (IADD3/ISETP/BRA), reported separately.  Repetitions
occur inside one kernel launch, so all but the first traversal measure steady
state.  The script warms each module once before collecting timing samples;
NCU can select the following launch with ``--launch-skip 1``.
"""

from __future__ import annotations

import argparse
import math
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


DEFAULT_SIZES_KIB = (
    0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64,
    96, 128, 192, 256,
)


def source(nops: int, iterations: int) -> str:
    lines = [
        "#fn icacheprobe(out<8>) {",
        "    #pragma MAXREG_COUNT(32)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        f"    MOV32I R10, 0x{iterations:x};[7:7:{{}}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    #def_label(loop)",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(nops)]
    lines += [
        "    IADD3 R10, R10, -0x1, RZ;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R10, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(loop);[7:7:{}:6:0]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R22,R23};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def parse_sizes(raw: str) -> list[float]:
    vals = [float(x) for x in raw.split(",") if x.strip()]
    if not vals or min(vals) <= 0:
        raise ValueError("sizes must be positive comma-separated KiB values")
    return vals


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes-kib", default=",".join(map(str, DEFAULT_SIZES_KIB)))
    p.add_argument("--total-nops", type=int, default=1 << 20,
                   help="minimum dynamic NOPs per measured launch")
    p.add_argument("--min-iters", type=int, default=16)
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--warps", type=int, default=1)
    p.add_argument("--skip-depcheck", action="store_true",
                   help="skip the quadratic CFG check for very large NOP bodies")
    ns = p.parse_args()
    try:
        sizes = parse_sizes(ns.sizes_kib)
    except ValueError as exc:
        p.error(str(exc))
    if min(ns.total_nops, ns.min_iters, ns.reps, ns.warps) <= 0:
        p.error("total-nops, min-iters, reps, and warps must be positive")
    if ns.warps > 32:
        p.error("warps must be <= 32")

    print("requested_KiB loop_bytes nops iterations median_cycles "
          "cycles_per_iter cycles_per_nop")
    for size_kib in sizes:
        requested = int(round(size_kib * 1024))
        nops = max(1, requested // 16 - 3)
        loop_bytes = (nops + 3) * 16
        iterations = max(ns.min_iters,
                         math.ceil(ns.total_nops / nops))
        mod = CudaModule(assemble(source(nops, iterations),
                                  check_deps=not ns.skip_depcheck))
        out_size = ns.warps * 32 * 16
        out = mod.devmem_alloc(out_size)
        vals = []
        try:
            for rep in range(ns.reps + 1):
                mod.launch("icacheprobe", grid=(1,),
                           block=(ns.warps * 32,), args=[out])
                mod.synchronize()
                if rep:
                    raw = mod.device_read(out, out_size)
                    t0, t1 = struct.unpack_from("<QQ", raw, 0)
                    vals.append((t1 - t0) & ((1 << 64) - 1))
        finally:
            mod.devmem_free(out)
        cycles = statistics.median(vals)
        print(f"{size_kib:g} {loop_bytes} {nops} {iterations} "
              f"{cycles:g} {cycles / iterations:.4f} "
              f"{cycles / (iterations * nops):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
