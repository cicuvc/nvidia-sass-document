#!/usr/bin/env python3
"""Measure UBLKCP.G.S consumption of the Hopper shared-data service.

Warp 0 issues a sequence of shared->global bulk copies and waits after each.
Warps 4..7 concurrently issue an LDS or STS stream (one warp per subcore).
Independent clock spans let the increase in contender time be converted to
service cycles per UBLKCP.  ``control`` keeps the same CTA, branches, clocks,
and address setup but omits the copy, so size slopes reject scheduler offsets.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


MODES = ("solo_t", "solo_c", "overlay", "control")


def source(size: int, copies: int, contender_count: int, mode: str,
           contender_op: str, commit: str, addr_shift: int) -> str:
    if size % 16 or not 16 <= size <= 16384:
        raise ValueError("UBLKCP size must be 16..16384 and a multiple of 16")
    if copies < 1:
        raise ValueError("copies must be positive")
    if contender_op not in ("sts", "lds", "shfl"):
        raise ValueError("contender_op must be sts, lds, or shfl")
    if commit not in ("each", "all"):
        raise ValueError("commit must be each or all")
    if addr_shift not in (2, 3, 4, 5):
        raise ValueError("addr_shift must be 2..5")
    units = size // 16
    run_t = mode in ("solo_t", "overlay")
    run_c = mode in ("solo_c", "overlay", "control")
    lines = [
        "#fn ublkserv(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma SHARED(0x6000)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{3}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{0,3}:5:1]",
        "    R2UR UR8, R14;[2:7:{1}:5:1]",
        "    R2UR UR9, R15;[2:7:{1}:5:1]",
        "    UMOV UR10, 0x1000;[7:7:{}:1:0]",
        f"    UMOV UR11, 0x{units:x};[7:7:{{}}:1:0]",
        "    LOP3.LUT R43, R4, 0x1f, RZ, 0xc0;[7:7:{3}:5:1]",
        f"    SHF.L.U32 R43, R43, 0x{addr_shift:x}, RZ;[7:7:{{}}:5:1]",
        "    MOV32I R40, 0x12345678;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.U32.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(tpath);[7:7:{}:5:1]",
        "    ISETP.GE.U32.AND P1, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(cpath);[7:7:{}:5:1]",
        "    BRA #label(exit);[7:7:{}:5:1]",
        "#def_label(tpath)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_t:
        for _ in range(copies):
            lines.append(
                "    UBLKCP.G.S [UR8], [UR10], UR11;[7:0:{2}:5:1]")
            if commit == "each":
                lines += [
                    "    UTMACMDFLUSH;[7:0:{2}:5:1]",
                    "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
                ]
        if commit == "all":
            lines += [
                "    UTMACMDFLUSH;[7:0:{2}:5:1]",
                "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
            ]
    else:
        # Preserve a little uniform/control work without touching shared data.
        for _ in range(copies):
            lines += [
                "    NOP;[7:7:{}:5:1]",
                "    NOP;[7:7:{}:5:1]",
                "    NOP;[7:7:{}:5:1]",
            ]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R18,R19};[7:4:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R20,R21};[7:4:{}:8:0]",
        "    BRA #label(exit);[7:7:{}:5:1]",
        "#def_label(cpath)",
        "    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_c:
        if contender_op == "sts":
            op = "    STS [R43], R40;[7:7:{}:1:1]"
        elif contender_op == "lds":
            op = "    LDS RZ, [R43];[7:7:{}:1:1]"
        else:
            op = "    SHFL.BFLY PT, RZ, RZ, 0x1, 0x1f;[7:7:{}:1:1]"
        lines += [op for _ in range(contender_count)]
    lines += [
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R24,R25};[7:4:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R26,R27};[7:4:{}:8:0]",
        "#def_label(exit)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(size: int, copies: int, contender_count: int, mode: str,
            contender_op: str, commit: str, arch: str,
            addr_shift: int, reps: int) -> tuple[float, float]:
    cubin = assemble(source(size, copies, contender_count, mode, contender_op,
                            commit, addr_shift),
                     arch=arch, check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(256 * 16)
    data = mod.devmem_alloc(0x8000)
    mod.devmem_set(data, 0, 0x8000 // 4)
    tma: list[int] = []
    contender: list[int] = []
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 256 * 16 // 4)
            mod.launch("ublkserv", grid=(1,), block=(256,), args=[out, data],
                       shared_mem=0x6000)
            mod.synchronize()
            if rep:
                vals = struct.unpack("<512Q", mod.device_read(out, 256 * 16))
                # vals are [start,end] pairs.  Lane 0 represents the uniform
                # TMA warp; the leaders of warps 4..7 represent four SMSPs.
                tma.append((vals[1] - vals[0]) & ((1 << 64) - 1))
                spans = []
                for tid in (128, 160, 192, 224):
                    spans.append((vals[2 * tid + 1] - vals[2 * tid]) &
                                 ((1 << 64) - 1))
                contender.append(statistics.median(spans))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return statistics.median(tma), statistics.median(contender)


def parse_sizes(text: str) -> list[int]:
    return [int(x, 0) for x in text.split(",") if x]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes", default="128,256,512,1024,2048,4096,8192,16384")
    p.add_argument("--contender-count", type=int, default=512)
    p.add_argument("--copies", type=int, default=32,
                   help="serialized UBLKCPs (amplifies shared-service demand)")
    p.add_argument("--contender-op", choices=("sts", "lds", "shfl"),
                   default="sts")
    p.add_argument("--commit", choices=("each", "all"), default="each",
                   help="commit/wait each copy, or put all copies in one group")
    p.add_argument("--arch", choices=("sm90", "sm120"), default="sm90")
    p.add_argument("--addr-shift", type=int, choices=(2, 3, 4, 5), default=4,
                   help="contender lane byte stride is 1<<shift (2=no conflict)")
    p.add_argument("--reps", type=int, default=11)
    ns = p.parse_args()
    print(f"copies={ns.copies} contender_count={ns.contender_count}")
    print("size total_KiB Tsolo Tover Csolo Cctrl Cover delta bytes/dcycle")
    for size in parse_sizes(ns.sizes):
        args = (size, ns.copies, ns.contender_count)
        opts = (ns.contender_op, ns.commit, ns.arch, ns.addr_shift, ns.reps)
        ts, _ = measure(*args, "solo_t", *opts)
        _, cs = measure(*args, "solo_c", *opts)
        _, cc = measure(*args, "control", *opts)
        to, co = measure(*args, "overlay", *opts)
        delta = co - cc
        total = size * ns.copies
        rate = total / delta if delta > 0 else float("inf")
        print(f"{size:5d} {total / 1024:9.1f} {ts:5.1f} {to:5.1f} "
              f"{cs:5.1f} {cc:5.1f} {co:5.1f} {delta:5.1f} {rate:12.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
