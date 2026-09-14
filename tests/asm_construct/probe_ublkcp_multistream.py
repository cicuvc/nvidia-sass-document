#!/usr/bin/env python3
"""Measure arbitration among independent same-direction UBLKCP streams.

One, two, or four warps (mapped to distinct SMSPs) issue equal command streams.
Each warp owns a disjoint 4-KiB shared window, 16-KiB global window, and (for
S.G) mbarrier.  Per-warp clocks expose aggregate throughput and fairness.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(direction: str, size: int, copies: int, streams: int) -> str:
    if direction not in ("gs", "sg"):
        raise ValueError("direction must be gs (S->G) or sg (G->S)")
    if size % 16 or not 16 <= size <= 4096:
        raise ValueError("size must be 16..4096 and a multiple of 16")
    if streams not in (1, 2, 4):
        raise ValueError("streams must be 1, 2, or 4")
    lines = [
        "#fn ublkmulti(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma NUM_MBARRIERS(4)",
        "    #pragma SHARED(0x6000)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{3}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x20, {R2,R3};[7:7:{0,3}:5:1]",
        # Per-warp global base = data + warp*0x4000.
        "    IMAD.WIDE.U32 {R12,R13}, R5, 0x4000, {R14,R15};[7:7:{1}:5:1]",
        "    R2UR UR20, R12;[2:7:{}:5:1]",
        "    R2UR UR21, R13;[2:7:{}:5:1]",
        # Per-warp shared base = 0x1000 + warp*0x1000.
        "    SHF.L.U32 R10, R5, 0xc, RZ;[7:7:{}:5:1]",
        "    IADD3 R10, R10, 0x1000, RZ;[7:7:{}:5:1]",
        "    R2UR UR22, R10;[4:7:{}:5:1]",
        # Per-warp mbarrier = 0x500 + warp*8.
        "    SHF.L.U32 R11, R5, 0x3, RZ;[7:7:{}:5:1]",
        "    IADD3 R11, R11, 0x500, RZ;[7:7:{}:5:1]",
        "    R2UR UR23, R11;[4:7:{}:5:1]",
        f"    UMOV UR24, 0x{size // 16:x};[7:7:{{}}:1:0]",
        f"    MOV32I R0, 0x{size * copies:x};[7:7:{{}}:5:1]",
        "    LOP3.LUT R8, R4, 0x1f, RZ, 0xc0;[7:7:{3}:5:1]",
        "    ISETP.EQ.U32.AND P6, PT, R8, RZ, PT;[7:7:{}:13:1]",
    ]
    if direction == "sg":
        lines += [
            "    UMOV UR26, 0x1;[7:7:{}:1:0]",
            "    UMOV UR29, 0x0;[7:7:{}:1:0]",
            "    UIADD3 UR26, UPT, UPT, -UR26, 0x100000, UR29;[7:7:{}:5:1]",
            "    USHF.L.U32 UR27, UR26, 0xb, UR29;[7:7:{}:5:1]",
            "    USHF.L.U32 UR26, UR26, 0x1, UR29;[7:7:{}:5:1]",
            "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
            "    SYNCS.EXCH.64 {UR28,UR29}, [UR23], {UR26,UR27};[3:5:{}:5:1]",
            "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]",
            "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        ]
    lines += [
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        f"    ISETP.LT.U32.AND P0, PT, R5, 0x{streams:x}, PT;[7:7:{{}}:13:1]",
        "    @!P0 BRA #label(exit);[7:7:{}:5:1]",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if direction == "gs":
        lines += [
            "    UBLKCP.G.S {UR20,UR21}, [UR22], UR24;[7:0:{2,4}:1:0]"
            for _ in range(copies)
        ]
        lines += [
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    UTMACMDFLUSH;[7:0:{2,4}:1:0]",
            "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        ]
    else:
        lines += [
            "    UBLKCP.S.G {UR22,UR23}, {UR20,UR21}, UR24;[7:0:{2,4}:1:0]"
            for _ in range(copies)
        ]
        lines += [
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR23], R0;[7:0:{0}:1:0]",
            "#def_label(poll)",
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR23], RZ;[4:7:{}:2:0]",
            "    @!P2 BRA #label(poll);[7:7:{4}:5:0]",
        ]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if direction == "sg":
        lines += [
            "    LDS R30, [RZ+UR22];[5:7:{}:8:1]",
            "    STG.E [{R6,R7}+0x18], R30;[7:4:{5}:8:0]",
        ]
    lines += [
        "    STG.E.64 [{R6,R7}], {R18,R19};[7:4:{}:8:0]",
        "    STG.E.64 [{R6,R7}+8], {R20,R21};[7:4:{}:8:0]",
        "    STG.E.64 [{R6,R7}+0x10], {R22,R23};[7:4:{}:8:0]",
        "#def_label(exit)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(direction: str, size: int, copies: int, streams: int,
            reps: int) -> tuple[list[float], list[float]]:
    cubin = assemble(source(direction, size, copies, streams), arch="sm90",
                     check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(256 * 32)
    data = mod.devmem_alloc(4 * 0x4000)
    mod.device_write(data, struct.pack("<16384I", *([0x12345678] * 16384)))
    issue_samples = [[] for _ in range(streams)]
    total_samples = [[] for _ in range(streams)]
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 256 * 32 // 4)
            mod.launch("ublkmulti", grid=(1,), block=(256,), args=[out, data],
                       shared_mem=0x6000)
            mod.synchronize()
            raw = mod.device_read(out, 256 * 32)
            for w in range(streams):
                tid = 32 * w
                if direction == "sg":
                    value, = struct.unpack_from("<I", raw, tid * 32 + 0x18)
                    if value != 0x12345678:
                        raise RuntimeError(f"warp {w} validation failed: {value:#x}")
                if rep:
                    a, b, c = struct.unpack_from("<QQQ", raw, tid * 32)
                    issue_samples[w].append((b - a) & ((1 << 64) - 1))
                    total_samples[w].append((c - a) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return ([statistics.median(x) for x in issue_samples],
            [statistics.median(x) for x in total_samples])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--direction", choices=("gs", "sg"), required=True)
    p.add_argument("--size", type=int, default=4096)
    p.add_argument("--copies", type=int, default=64)
    p.add_argument("--streams", default="1,2,4")
    p.add_argument("--reps", type=int, default=13)
    ns = p.parse_args()
    payload = ns.size * ns.copies
    print("streams issue_cycles total_cycles spread aggregate_B/c")
    for streams in (int(x) for x in ns.streams.split(",") if x):
        issues, times = measure(ns.direction, ns.size, ns.copies, streams,
                                ns.reps)
        aggregate = streams * payload / max(times)
        print(f"{streams:7d} {','.join(f'{t:.1f}' for t in issues):>24s} "
              f"{','.join(f'{t:.1f}' for t in times):>30s} "
              f"{max(times)-min(times):6.1f} {aggregate:13.2f} "
              )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
