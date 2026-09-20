#!/usr/bin/env python3
"""HGMMA admission burst-window probe (sm_90/H100).

One warpgroup (128 threads) issues a burst of N HGMMAs between CS2R reads
and reports per-thread issue span plus post-DEPBAR drain span.  T_issue(N)
linear from N=1 at the steady rate means the TC command FIFO admits at the
pipe rate with no burst window; a fast initial segment of length K would
mark an admission buffer of depth K.

--pred squashes the HGMMAs with @P6 (front-end admission cost only).
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from probe_hgmma_mio_interaction import hgmma_body  # noqa: E402


def source(n: int, shape: int, operand: str, pred: bool,
           stall: int = 4) -> str:
    lines = [
        "#fn hgburst(out<8>) {",
        "    #pragma MAXREG_COUNT(128)",
        "    #pragma SHARED(16384)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x20, {R2,R3};[7:7:{0,2}:5:1]",
        "    LOP3.LUT R42, R4, 0x1f, RZ, 0xc0;[7:7:{2}:5:1]",
        "    IMAD.U32 R42, R42, 0x80, RZ;[7:7:{}:5:1]",
        "    LOP3.LUT R43, R4, 0x1f, RZ, 0xc0;[7:7:{2}:5:1]",
        "    IMAD.U32 R43, R43, 0x10, RZ;[7:7:{}:5:1]",
        "    IADD3 R43, R43, 0x1000, RZ;[7:7:{}:5:1]",
        "    MOV32I R40, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R56, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R57, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R58, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R59, 0x3f803f80;[7:7:{}:5:1]",
        "    UMOV UR4, 0x400040;[7:7:{}:5:1]",
        "    UMOV UR5, 0x0;[7:7:{}:5:1]",
        "    UMOV UR6, 0x4000c0;[7:7:{}:5:1]",
        "    UMOV UR7, 0x0;[7:7:{}:5:1]",
        "    UMOV UR8, 0x4000c0;[7:7:{}:5:1]",
        "    UMOV UR9, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    WARPGROUP.ARRIVE;[7:7:{}:5:1]",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += [ln.replace(";[7:7:{}:4:0]", f";[7:7:{{}}:{stall}:0]")
              if "HGMMA" in ln else ln
              for ln in hgmma_body(n, shape, operand, pred_off=pred)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if not pred:
        lines += ["    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]"]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R18,R19};[7:3:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R20,R21};[7:3:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x10], {R22,R23};[7:3:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(n: int, shape: int, operand: str, pred: bool,
            reps: int, stall: int = 4) -> tuple[float, float]:
    cubin = assemble(source(n, shape, operand, pred, stall), arch="sm90",
                     check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(128 * 32)
    issue: list[int] = []
    drain: list[int] = []
    try:
        for rep in range(reps + 1):
            mod.launch("hgburst", grid=(1,), block=(128,), args=[out])
            mod.synchronize()
            if rep:
                t0, t1, t2 = struct.unpack("<QQQ", mod.device_read(out, 24))
                issue.append((t1 - t0) & ((1 << 64) - 1))
                drain.append((t2 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return statistics.median(issue), statistics.median(drain)


def parse_counts(text: str) -> list[int]:
    if "-" in text:
        lo, hi = text.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in text.split(",")]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--shape", type=int, choices=(8, 16, 64), default=16)
    p.add_argument("--operand", choices=("ss", "rs"), default="rs")
    p.add_argument("--pred", action="store_true")
    p.add_argument("--counts", default="0-24")
    p.add_argument("--reps", type=int, default=7)
    p.add_argument("--stall", type=int, default=4)
    ns = p.parse_args()
    for n in parse_counts(ns.counts):
        issue, drain = measure(n, ns.shape, ns.operand, ns.pred, ns.reps,
                           ns.stall)
        print(f"N={n:3d} issue={issue:9.1f} drain={drain:9.1f} "
              f"{'pred' if ns.pred else 'active'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
