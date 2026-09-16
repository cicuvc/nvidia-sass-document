#!/usr/bin/env python3
"""Measure ADU-stream throughput across same/different GB202 subcores."""

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
CASES = ("bra", "brx_rz", "brx_reg", "ldc_imm", "ldc_reg", "bar")


def body(case: str, count: int, guard: str = "") -> list[str]:
    pfx = f"{guard} " if guard else ""
    lines: list[str] = []
    for i in range(count):
        rd = 40 + i % 40
        if case == "bra":
            lines += [f"    {pfx}BRA #label(b_{i});[7:7:{{}}:6:1]",
                      f"    #def_label(b_{i})"]
        elif case == "brx_rz":
            lines += [f"    {pfx}BRX RZ, #label(b_{i});[7:7:{{}}:6:1]",
                      f"    #def_label(b_{i})"]
        elif case == "brx_reg":
            lines += [
                f"    {pfx}BRX {{R24,R25}}, #label(b_{i});[7:7:{{}}:6:1]",
                f"    #def_label(b_{i})",
            ]
        elif case == "ldc_imm":
            lines.append(
                f"    {pfx}LDC R{rd}, c[0x0][0x0];[7:7:{{}}:1:1]")
        elif case == "ldc_reg":
            lines.append(
                f"    {pfx}LDC R{rd}, c[0x0][R24+0x0];[7:7:{{}}:1:1]")
        elif case == "bar":
            lines.append(f"    {pfx}BAR.SYNC 0;[7:7:{{}}:5:1]")
        else:
            raise ValueError(case)
    return lines


def source(case: str, actors: tuple[int, ...], count: int,
           pred_off: bool) -> str:
    lines = [
        "#fn aduscale(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        "    MOV32I R24, 0x0;[7:7:{}:5:1]",
        "    MOV32I R25, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for w in actors:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;[7:7:{{}}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:6:0]",
        ]
    lines += [
        "    BRA #label(done);[7:7:{}:6:0]",
        "    #def_label(work)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += body(case, count, "@P6" if pred_off else "")
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R22,R23};[7:1:{}:8:0]",
        "    #def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=CASES, required=True)
    p.add_argument("--actors", choices=ACTORS, default="one")
    p.add_argument("--count", type=int, default=256)
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--pred-off", action="store_true")
    ns = p.parse_args()
    if ns.count <= 0 or ns.reps <= 0:
        p.error("count and reps must be positive")

    actors = ACTORS[ns.actors]
    mod = CudaModule(assemble(source(ns.case, actors, ns.count, ns.pred_off),
                              check_deps=True))
    out = mod.devmem_alloc(256 * 16)
    per_warp = {w: [] for w in actors}
    spans = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("aduscale", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            if rep:
                raw = mod.device_read(out, 256 * 16)
                starts, ends = [], []
                for w in actors:
                    t0, t1 = struct.unpack_from("<QQ", raw, w * 32 * 16)
                    per_warp[w].append((t1 - t0) & ((1 << 64) - 1))
                    starts.append(t0)
                    ends.append(t1)
                spans.append(max(ends) - min(starts))
    finally:
        mod.devmem_free(out)

    med = {w: statistics.median(v) / ns.count for w, v in per_warp.items()}
    rate = len(actors) * ns.count / statistics.median(spans)
    print(f"{ns.case} actors={ns.actors} pred_off={ns.pred_off}: "
          f"cycles/op={med} aggregate_inst/cycle={rate:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
