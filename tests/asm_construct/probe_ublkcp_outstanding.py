#!/usr/bin/env python3
"""Find UBLKCP outstanding-request capacity from producer backpressure.

A single warp emits N same-sized commands without an intervening wait.  Clocks
bracket the issue sequence and final completion separately.  A queue-capacity
knee appears when issue time stops following the instruction-only baseline and
begins following TMA service time.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(direction: str, size: int, count: int, active: bool,
           arrive_before: bool = False) -> str:
    if direction not in ("gs", "sg"):
        raise ValueError("direction must be gs or sg")
    if size % 16 or not 16 <= size <= 16384:
        raise ValueError("bad size")
    if count < 1 or size * count >= (1 << 20):
        raise ValueError("count/expect-tx exceeds conservative 20-bit limit")
    lines = [
        "#fn ublkdepth(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(40)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma SHARED(0x6000)",
        "    LDC.64 {R2,R3}, #param(out);[5:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    R2UR UR20, R14;[2:7:{1}:5:1]",
        "    R2UR UR21, R15;[2:7:{1}:5:1]",
        "    UMOV UR22, 0x1000;[7:7:{}:1:0]",
        "    UMOV UR23, 0x500;[7:7:{}:1:0]",
        f"    UMOV UR24, 0x{size // 16:x};[7:7:{{}}:1:0]",
        f"    MOV32I R0, 0x{size * count:x};[7:7:{{}}:5:1]",
        "    ISETP.EQ.U32.AND P6, PT, R4, RZ, PT;[7:7:{3}:13:1]",
    ]
    if direction == "sg":
        lines += [
            "    UMOV UR26, 0x1;[7:7:{}:1:0]",
            "    UMOV UR29, 0x0;[7:7:{}:1:0]",
            "    UIADD3 UR26, UPT, UPT, -UR26, 0x100000, UR29;[7:7:{}:5:1]",
            "    USHF.L.U32 UR27, UR26, 0xb, UR29;[7:7:{}:5:1]",
            "    USHF.L.U32 UR26, UR26, 0x1, UR29;[7:7:{}:5:1]",
            "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
            "    SYNCS.EXCH.64 {UR28,UR29}, [UR23], {UR26,UR27};[3:4:{}:5:1]",
            "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]",
            "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        ]
    lines += [
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if active and direction == "sg" and arrive_before:
        lines += [
            "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR23], R0;[7:1:{}:1:0]",
        ]
    lines += ["    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]"]
    if active:
        if direction == "gs":
            lines += [
                "    UBLKCP.G.S {UR20,UR21}, [UR22], UR24;[7:0:{2}:1:0]"
                for _ in range(count)
            ]
        else:
            lines += [
                "    UBLKCP.S.G {UR22,UR23}, {UR20,UR21}, UR24;[7:0:{2}:1:0]"
                for _ in range(count)
            ]
    else:
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(count)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if active and direction == "gs":
        lines += [
            "    UTMACMDFLUSH;[7:0:{2}:1:0]",
            "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        ]
    elif active and not arrive_before:
        lines += [
            "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR23], R0;[7:0:{0}:1:0]",
        ]
    if active and direction == "sg":
        lines += [
            "#def_label(poll)",
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR23], RZ;[4:7:{}:2:0]",
            "    @!P2 BRA #label(poll);[7:7:{4}:5:0]",
        ]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if active and direction == "sg":
        lines += [
            "    LDS R30, [RZ+UR22];[3:7:{}:8:1]",
            "    STG.E [{R2,R3}+0x18], R30;[7:4:{3,5}:8:0]",
        ]
    lines += [
        "    STG.E.64 [{R2,R3}], {R18,R19};[7:4:{5}:8:0]",
        "    STG.E.64 [{R2,R3}+8], {R20,R21};[7:4:{5}:8:0]",
        "    STG.E.64 [{R2,R3}+0x10], {R22,R23};[7:4:{5}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(direction: str, size: int, count: int, active: bool,
            arrive_before: bool, reps: int,
            arch: str = "sm90") -> tuple[float, float, float]:
    cubin = assemble(source(direction, size, count, active, arrive_before),
                     arch=arch,
                     check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(0x8000)
    mod.device_write(data, struct.pack("<8192I", *([0x12345678] * 8192)))
    issue, tail, total = [], [], []
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 8)
            mod.launch("ublkdepth", grid=(1,), block=(32,), args=[out, data],
                       shared_mem=0x6000)
            mod.synchronize()
            raw = mod.device_read(out, 32)
            if active and direction == "sg":
                value, = struct.unpack_from("<I", raw, 0x18)
                if value != 0x12345678:
                    raise RuntimeError(f"validation failed: {value:#x}")
            if rep:
                a, b, c = struct.unpack_from("<QQQ", raw)
                issue.append((b - a) & ((1 << 64) - 1))
                tail.append((c - b) & ((1 << 64) - 1))
                total.append((c - a) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return (statistics.median(issue), statistics.median(tail),
            statistics.median(total))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--direction", choices=("gs", "sg"), required=True)
    p.add_argument("--size", type=int, default=4096)
    p.add_argument("--counts", default="1,2,4,8,12,16,24,32,48,64,96,128")
    p.add_argument("--reps", type=int, default=13)
    p.add_argument("--arch", choices=("sm90", "sm120"), default="sm90")
    p.add_argument("--arrive-before", action="store_true",
                   help="arm S.G expect-tx before issuing UBLKCPs")
    ns = p.parse_args()
    print("count nop_issue tma_issue excess tail total issue_delta")
    prev_n = prev_issue = None
    for count in (int(x) for x in ns.counts.split(",") if x):
        ni, _, _ = measure(ns.direction, ns.size, count, False,
                           ns.arrive_before, ns.reps, ns.arch)
        ti, tail, total = measure(ns.direction, ns.size, count, True,
                                  ns.arrive_before, ns.reps, ns.arch)
        slope = ((ti - prev_issue) / (count - prev_n)
                 if prev_n is not None else float("nan"))
        print(f"{count:5d} {ni:9.1f} {ti:9.1f} {ti-ni:7.1f} "
              f"{tail:7.1f} {total:7.1f} {slope:11.2f}")
        prev_n, prev_issue = count, ti
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
