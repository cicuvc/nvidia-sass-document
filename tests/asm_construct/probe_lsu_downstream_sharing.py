#!/usr/bin/env python3
"""Test shared/global downstream backpressure in both directions.

Warp 0 issues a short LDS burst.  The request count is held fixed while the
address pattern changes from one to 32 shared-data wavefronts per request.
Warp 1 (a different subcore) delays by a selectable number of NOPs and times
a dead-result victim burst.  The reverse mode uses coalesced versus scattered
LDG floods and an LDS victim.  Extra victim *issue-span* caused specifically
by downstream work is backpressure rather than local LSU queue occupancy or
the number of MIOC instructions presented by the contender.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(prefix: int, conflict: int, delay: int, victim: int,
           direction: str) -> str:
    lds_addr = "RZ" if conflict == 0 else "R26"
    if direction in ("lds_to_ldg", "lds_to_shfl"):
        flood = [f"    LDS R{40 + i}, [{lds_addr}];[7:7:{{}}:1:1]"
                 for i in range(prefix)]
        if direction == "lds_to_ldg":
            tested = [f"    LDG.E.STRONG.GPU R{100 + i}, [{{R10,R11}}];"
                      "[7:7:{}:1:1]" for i in range(victim)]
        else:
            # RZ eliminates late GPR collection, isolating downstream LSU
            # admission from the separate ~0.5-GPR-operand/clock limit.
            tested = [f"    SHFL.BFLY PT, R{100 + i}, RZ, 0x1, 0x1f;"
                      "[7:7:{}:1:1]" for i in range(victim)]
    elif direction == "ldg_to_lds":
        # conflict=1: consecutive lanes (four 32-B sectors/request).
        # conflict=32: one 128-B line/lane (32 sectors and lines/request).
        flood = [
            f"    LDG.E.STRONG.GPU R{40 + i}, "
            f"[{{R12,R13}}+0x{i * 0x1000:x}];[7:7:{{}}:1:1]"
            for i in range(prefix)
        ]
        tested = [f"    LDS R{100 + i}, [RZ];[7:7:{{}}:1:1]"
                  for i in range(victim)]
    else:
        raise ValueError(direction)
    return "\n".join([
        "#fn shareprobe(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(160)",
        "    #pragma SHARED(4096)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R10,R11}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    LOP3.LUT R26, R4, 0x1f, RZ, 0xc0;[7:7:{2}:5:1]",
        "    LOP3.LUT R27, R4, 0x1f, RZ, 0xc0;[7:7:{2}:5:1]",
        f"    IMAD.U32 R26, R26, 0x{4 * max(conflict, 1):x}, RZ;"
        "[7:7:{}:5:1]",
        f"    IMAD.WIDE.U32 {{R12,R13}}, R27, 0x{4 if conflict == 1 else 128:x}, "
        "{R10,R11};[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R5, 0x10, {R2,R3};"
        "[7:7:{0,2}:5:1]",
        "    BAR.SYNC 0;[7:7:{1}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(flood);[7:7:{}:5:1]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(delay)],
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *tested,
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    BRA #label(record);[7:7:{}:5:1]",
        "#def_label(flood)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *flood,
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "#def_label(record)",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:0:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:0:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def measure(prefix: int, conflict: int, delay: int, victim: int, reps: int,
            direction: str) -> tuple[float, float, tuple[int, int], tuple[int, int]]:
    mod = CudaModule(assemble(source(prefix, conflict, delay, victim, direction),
                              check_deps=True))
    out = mod.devmem_alloc(32)
    data_size = max(128, prefix * 0x1000 + 4096)
    data = mod.devmem_alloc(data_size)
    mod.devmem_set(data, 0x12345678, data_size // 4)
    flood_spans: list[int] = []
    victim_spans: list[int] = []
    try:
        for _ in range(reps + 1):
            mod.launch("shareprobe", grid=(1,), block=(64,), args=[out, data])
            mod.synchronize()
            raw = mod.device_read(out, 32)
            f0, f1, v0, v1 = struct.unpack("<QQQQ", raw)
            flood_spans.append(f1 - f0)
            victim_spans.append(v1 - v0)
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    fs = flood_spans[1:]
    vs = victim_spans[1:]
    return (statistics.median(fs), statistics.median(vs),
            (min(fs), max(fs)), (min(vs), max(vs)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix", type=int, default=24)
    p.add_argument("--victim", type=int, default=8)
    p.add_argument("--delays", default="0,4,8,12,16,20,24,28,32")
    p.add_argument("--conflicts", default="1,32")
    p.add_argument("--direction",
                   choices=("lds_to_ldg", "ldg_to_lds", "lds_to_shfl"),
                   default="lds_to_ldg")
    p.add_argument("--reps", type=int, default=9)
    ns = p.parse_args()
    delays = [int(x) for x in ns.delays.split(",") if x.strip()]
    conflicts = [int(x) for x in ns.conflicts.split(",") if x.strip()]
    print("conflict delay flood_med[min,max] victim_med[min,max]")
    for conflict in conflicts:
        for delay in delays:
            fm, vm, fr, vr = measure(ns.prefix, conflict, delay, ns.victim,
                                     ns.reps, ns.direction)
            print(f"{conflict:8d} {delay:5d} {fm:9g}{fr!s:>12} "
                  f"{vm:10g}{vr!s:>12}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
