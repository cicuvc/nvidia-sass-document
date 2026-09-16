#!/usr/bin/env python3
"""Classify and scale GB202 CBU state/control operations.

``--profile`` emits a one-warp parameter-free kernel for clean NCU counts.
The default timed mode selects warp sets whose ids establish same/different
subcore placement and reports aggregate warp-instruction throughput.  A
``bssy_sync`` item is one BSSY+BSYNC pair (two CBU instructions).
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
    "same4": (0, 4, 8, 12),
    "same8": tuple(range(0, 32, 4)),
    "diff2": (0, 1),
    "diff4": (0, 1, 2, 3),
    "all8": tuple(range(8)),
    "all16": tuple(range(16)),
    "all32": tuple(range(32)),
}
CASES = (
    "nop", "bmov_read", "bmov_write", "bssy_burst", "bssy_sync", "warpsync_all",
    "warpsync_reg", "yield", "nanosleep", "bra", "brx_reg",
)


def body(case: str, count: int, guard: str = "") -> list[str]:
    pfx = f"{guard} " if guard else ""
    lines: list[str] = []
    for i in range(count):
        rd = 32 + i % 8
        if case == "nop":
            lines.append(f"    {pfx}NOP;[7:7:{{}}:1:1]")
        elif case == "bmov_read":
            lines.append(
                f"    {pfx}BMOV.32 R{rd}, MACTIVE;[7:7:{{}}:1:1]")
        elif case == "bmov_write":
            lines.append(
                f"    {pfx}BMOV.32 OPT_STACK, R26;[7:7:{{}}:1:1]")
        elif case == "bssy_sync":
            lines += [
                f"    {pfx}BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                f"    #def_label(join_{i})",
                f"    {pfx}BSYNC B0;[7:7:{{}}:5:1]",
            ]
        elif case == "bssy_burst":
            if count > 16:
                raise ValueError("bssy_burst supports at most 16 barrier slots")
            lines += [
                f"    {pfx}BSSY B{i}, #label(armed_{i});[7:7:{{}}:1:1]",
                f"    #def_label(armed_{i})",
            ]
        elif case == "warpsync_all":
            lines.append(f"    {pfx}WARPSYNC.ALL;[7:7:{{}}:5:1]")
        elif case == "warpsync_reg":
            lines.append(f"    {pfx}WARPSYNC R24;[7:7:{{}}:5:1]")
        elif case == "yield":
            lines.append(f"    {pfx}YIELD;[7:7:{{}}:5:1]")
        elif case == "nanosleep":
            lines.append(f"    {pfx}NANOSLEEP 0x0;[7:7:{{}}:5:1]")
        elif case == "bra":
            lines += [f"    {pfx}BRA #label(join_{i});[7:7:{{}}:6:1]",
                      f"    #def_label(join_{i})"]
        elif case == "brx_reg":
            lines += [
                f"    {pfx}BRX {{R26,R27}}, #label(join_{i});"
                "[7:7:{}:6:1]",
                f"    #def_label(join_{i})",
            ]
        else:
            raise ValueError(case)
    return lines


def profile_source(case: str, count: int, pred_off: bool) -> str:
    lines = [
        "#fn cbuprobe() {",
        "    #pragma MAXREG_COUNT(48)",
        "    MOV32I R24, 0xffffffff;[7:7:{}:5:1]",
        "    MOV32I R25, 0x0;[7:7:{}:5:1]",
        "    MOV32I R26, 0x0;[7:7:{}:5:1]",
        "    MOV32I R27, 0x0;[7:7:{}:5:1]",
    ]
    lines += body(case, count, "@P6" if pred_off else "")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def timed_source(case: str, actors: tuple[int, ...], count: int,
                 pred_off: bool) -> str:
    lines = [
        "#fn cbuscale(out<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        "    MOV32I R24, 0xffffffff;[7:7:{}:5:1]",
        "    MOV32I R25, 0x0;[7:7:{}:5:1]",
        "    MOV32I R26, 0x0;[7:7:{}:5:1]",
        "    MOV32I R27, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if actors == tuple(range(max(actors) + 1)):
        lines += ["    BRA #label(work);[7:7:{}:6:0]"]
    elif actors == tuple(range(0, max(actors) + 1, 4)):
        lines += [
            "    LOP3.LUT R8, R5, 0x3, RZ, 0xc0;[7:7:{}:5:1]",
            "    ISETP.EQ.AND P0, PT, R8, RZ, PT;[7:7:{}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:6:0]",
            "    BRA #label(done);[7:7:{}:6:0]",
        ]
    else:
        for warp in actors:
            lines += [
                f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
                "[7:7:{}:13:1]",
                "    @P0 BRA #label(work);[7:7:{}:6:0]",
            ]
        lines += ["    BRA #label(done);[7:7:{}:6:0]"]
    lines += [
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
    p.add_argument("--profile", action="store_true")
    ns = p.parse_args()
    if ns.count <= 0 or ns.reps <= 0:
        p.error("count and reps must be positive")

    if ns.profile:
        mod = CudaModule(assemble(profile_source(ns.case, ns.count,
                                                 ns.pred_off),
                                  check_deps=True))
        for _ in range(ns.reps):
            mod.launch("cbuprobe", grid=(1,), block=(32,), args=[])
            mod.synchronize()
        print(f"{ns.case}: count={ns.count} pred_off={ns.pred_off} ok")
        return 0

    actors = ACTORS[ns.actors]
    mod = CudaModule(assemble(timed_source(ns.case, actors, ns.count,
                                           ns.pred_off),
                              check_deps=True))
    block_threads = (max(actors) + 1) * 32
    out_size = block_threads * 16
    out = mod.devmem_alloc(out_size)
    samples = {warp: [] for warp in actors}
    spans = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("cbuscale", grid=(1,), block=(block_threads,),
                       args=[out])
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

    instructions = count_instructions(ns.case, ns.count)
    per_warp = {w: statistics.median(v) / instructions
                for w, v in samples.items()}
    rate = len(actors) * instructions / statistics.median(spans)
    print(f"{ns.case} actors={ns.actors} pred_off={ns.pred_off}: "
          f"cycles/CBU-inst={per_warp} aggregate_CBU-inst/cycle={rate:.4f}")
    return 0


def count_instructions(case: str, count: int) -> int:
    return count * (2 if case == "bssy_sync" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
