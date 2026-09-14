#!/usr/bin/env python3
"""Probe whether small and large Hopper UBLKCP.S.G requests share capacity.

Every case contains exactly the same multiset of requests; only their order is
changed.  Commands rotate over four disjoint global/shared 4-KiB windows so a
result cannot be explained solely by repeatedly copying one aliased range.
Clocks at start, a pattern-defined split, end-of-issue, and completion expose
both head-of-line effects and the final drain.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


SMALL = "S"
LARGE = "L"


def request_order(pattern: str, small_count: int, large_count: int) -> list[str]:
    if pattern == "small-first":
        return [SMALL] * small_count + [LARGE] * large_count
    if pattern == "large-first":
        return [LARGE] * large_count + [SMALL] * small_count
    if pattern != "interleave":
        raise ValueError(f"bad pattern: {pattern}")

    # Evenly distribute both populations.  This avoids leaving a long all-small
    # suffix when their counts differ (as simple pairwise alternation would).
    total = small_count + large_count
    order: list[str] = []
    old_large = 0
    for i in range(total):
        new_large = ((i + 1) * large_count) // total
        order.append(LARGE if new_large != old_large else SMALL)
        old_large = new_large
    assert order.count(SMALL) == small_count
    assert order.count(LARGE) == large_count
    return order


def split_index(pattern: str, small_count: int, large_count: int) -> int:
    if pattern == "small-first":
        return small_count
    if pattern == "large-first":
        return large_count
    return (small_count + large_count) // 2


def source(pattern: str, small_size: int, large_size: int,
           small_count: int, large_count: int, active: bool) -> str:
    for size in (small_size, large_size):
        if size % 16 or not 16 <= size <= 4096:
            raise ValueError("sizes must be 16..4096 and multiples of 16")
    if small_size >= large_size:
        raise ValueError("small-size must be less than large-size")
    order = request_order(pattern, small_count, large_count)
    if not order or sum(small_size if x == SMALL else large_size for x in order) >= (1 << 20):
        raise ValueError("empty request list or expect-tx exceeds 20-bit limit")
    split = split_index(pattern, small_count, large_count)

    lines = [
        "#fn ublkmix(out<8>, d0<8>, d1<8>, d2<8>, d3<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma SHARED(0x6000)",
        "    LDC.64 {R2,R3}, #param(out);[5:7:{}:1:0]",
        "    LDCU.64 {UR30,UR31}, #param(d0);[0:7:{}:1:0]",
        "    LDCU.64 {UR32,UR33}, #param(d1);[1:7:{}:1:0]",
        "    LDCU.64 {UR34,UR35}, #param(d2);[2:7:{}:1:0]",
        "    LDCU.64 {UR36,UR37}, #param(d3);[3:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        "    DEPBAR.LE SB1, 0x0;[7:7:{}:5:1]",
        "    DEPBAR.LE SB2, 0x0;[7:7:{}:5:1]",
        "    DEPBAR.LE SB3, 0x0;[7:7:{}:5:1]",
        "    UMOV UR20, 0x1000;[7:7:{}:1:0]",
        "    UMOV UR21, 0x500;[7:7:{}:1:0]",
        "    UMOV UR22, 0x2000;[7:7:{}:1:0]",
        "    UMOV UR23, 0x500;[7:7:{}:1:0]",
        "    UMOV UR24, 0x3000;[7:7:{}:1:0]",
        "    UMOV UR25, 0x500;[7:7:{}:1:0]",
        "    UMOV UR26, 0x4000;[7:7:{}:1:0]",
        "    UMOV UR27, 0x500;[7:7:{}:1:0]",
        f"    UMOV UR28, 0x{small_size // 16:x};[7:7:{{}}:1:0]",
        f"    UMOV UR29, 0x{large_size // 16:x};[7:7:{{}}:1:0]",
        "    UMOV UR40, 0x1;[7:7:{}:1:0]",
        "    UMOV UR43, 0x0;[7:7:{}:1:0]",
        "    UIADD3 UR40, UPT, UPT, -UR40, 0x100000, UR43;[7:7:{}:5:1]",
        "    USHF.L.U32 UR41, UR40, 0xb, UR43;[7:7:{}:5:1]",
        "    USHF.L.U32 UR40, UR40, 0x1, UR43;[7:7:{}:5:1]",
        f"    MOV32I R0, 0x{sum(small_size if x == SMALL else large_size for x in order):x};[7:7:{{}}:5:1]",
        "    ISETP.EQ.U32.AND P6, PT, R4, RZ, PT;[7:7:{4}:13:1]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    SYNCS.EXCH.64 {UR42,UR43}, [UR21], {UR40,UR41};[0:1:{}:5:1]",
        "    MEMBAR.ALL.CTA;[7:7:{0}:5:1]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    CS2R {R10,R11}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]

    shared_urs = (20, 22, 24, 26)
    global_urs = (30, 32, 34, 36)
    for i, kind in enumerate(order):
        if i == split:
            lines.append("    CS2R {R12,R13}, SR_CLOCKLO;[7:7:{}:5:0]")
        if active:
            su = shared_urs[i & 3]
            gu = global_urs[i & 3]
            zu = 28 if kind == SMALL else 29
            lines.append(
                f"    UBLKCP.S.G {{UR{su},UR{su + 1}}}, "
                f"{{UR{gu},UR{gu + 1}}}, UR{zu};[7:0:{{}}:1:0]"
            )
        else:
            lines.append("    NOP;[7:7:{}:1:0]")
    if split == len(order):
        lines.append("    CS2R {R12,R13}, SR_CLOCKLO;[7:7:{}:5:0]")
    lines += [
        "    CS2R {R14,R15}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if active:
        lines += [
            "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR21], R0;[7:0:{}:1:0]",
            "#def_label(poll)",
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR21], RZ;[1:7:{}:2:0]",
            "    @!P2 BRA #label(poll);[7:7:{1}:5:0]",
        ]
    lines += [
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64 [{R2,R3}], {R10,R11};[7:4:{5}:8:0]",
        "    STG.E.64 [{R2,R3}+8], {R12,R13};[7:4:{5}:8:0]",
        "    STG.E.64 [{R2,R3}+0x10], {R14,R15};[7:4:{5}:8:0]",
        "    STG.E.64 [{R2,R3}+0x18], {R16,R17};[7:4:{5}:8:0]",
    ]
    if active:
        for i, su in enumerate(shared_urs):
            lines += [
                f"    LDS R{20 + i}, [RZ+UR{su}];[2:7:{{}}:8:1]",
                f"    STG.E [{{R2,R3}}+0x{0x20 + 4 * i:x}], R{20 + i};[7:4:{{2,5}}:8:0]",
            ]
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def measure(pattern: str, small_size: int, large_size: int,
            small_count: int, large_count: int, active: bool,
            reps: int) -> tuple[float, float, float, float]:
    cubin = assemble(source(pattern, small_size, large_size, small_count,
                            large_count, active), arch="sm90", check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(64)
    data = mod.devmem_alloc(0x4000)
    patterns = (0x11111111, 0x22222222, 0x33333333, 0x44444444)
    payload = b"".join(struct.pack("<1024I", *([x] * 1024)) for x in patterns)
    mod.device_write(data, payload)
    samples = [[] for _ in range(4)]
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 16)
            args = [out] + [data + 0x1000 * i for i in range(4)]
            mod.launch("ublkmix", grid=(1,), block=(32,), args=args,
                       shared_mem=0x6000)
            mod.synchronize()
            raw = mod.device_read(out, 64)
            if active:
                got = struct.unpack_from("<4I", raw, 0x20)
                touched = {i & 3 for i in range(small_count + large_count)}
                bad = {i: (got[i], patterns[i]) for i in touched
                       if got[i] != patterns[i]}
                if bad:
                    raise RuntimeError(f"validation failed: {bad!r}")
            if rep:
                clocks = struct.unpack_from("<4Q", raw)
                spans = tuple((clocks[i + 1] - clocks[i]) & ((1 << 64) - 1)
                              for i in range(3))
                vals = spans + (((clocks[3] - clocks[0]) & ((1 << 64) - 1)),)
                for bucket, value in zip(samples, vals):
                    bucket.append(value)
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return tuple(statistics.median(x) for x in samples)  # type: ignore[return-value]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--small-size", type=int, default=1024)
    p.add_argument("--large-size", type=int, default=4096)
    p.add_argument("--small-count", type=int, default=128)
    p.add_argument("--large-count", type=int, default=48)
    p.add_argument("--patterns", default="small-first,large-first,interleave")
    p.add_argument("--reps", type=int, default=13)
    ns = p.parse_args()
    print("pattern split_cmd split_bytes phase1 phase2 tail total "
          "excess1 excess2 excess_total")
    for pattern in (x for x in ns.patterns.split(",") if x):
        order = request_order(pattern, ns.small_count, ns.large_count)
        split = split_index(pattern, ns.small_count, ns.large_count)
        split_bytes = sum(ns.small_size if x == SMALL else ns.large_size
                          for x in order[:split])
        nop = measure(pattern, ns.small_size, ns.large_size, ns.small_count,
                      ns.large_count, False, ns.reps)
        tma = measure(pattern, ns.small_size, ns.large_size, ns.small_count,
                      ns.large_count, True, ns.reps)
        print(f"{pattern:12s} {split:9d} {split_bytes:11d} "
              f"{tma[0]:6.1f} {tma[1]:6.1f} {tma[2]:6.1f} {tma[3]:7.1f} "
              f"{tma[0]-nop[0]:7.1f} {tma[1]-nop[1]:7.1f} "
              f"{tma[3]-nop[3]:12.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
