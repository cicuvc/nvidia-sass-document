#!/usr/bin/env python3
"""Measure UBLKCP.S.G occupancy of Hopper shared read/write services.

Warp 0 launches global-to-shared bulk copies completed by one transaction-count
mbarrier.  Warps 4..7 concurrently run LDS or STS, one warp per SMSP.  A
matched control performs the same mbarrier setup but omits the copies.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(size: int, copies: int, contender_count: int, mode: str,
           contender_op: str, addr_shift: int) -> str:
    if size % 16 or not 16 <= size <= 16384:
        raise ValueError("size must be 16..16384 and a multiple of 16")
    if copies < 1 or size * copies >= (1 << 32):
        raise ValueError("invalid copies/total transaction count")
    if mode not in ("solo_t", "solo_c", "overlay", "control"):
        raise ValueError("invalid mode")
    if contender_op not in ("sts", "lds", "shfl"):
        raise ValueError("contender_op must be sts, lds, or shfl")
    if addr_shift not in (2, 3, 4, 5):
        raise ValueError("addr_shift must be 2..5")

    run_t = mode in ("solo_t", "overlay")
    run_c = mode in ("solo_c", "overlay", "control")
    lines = [
        "#fn ublkload(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma SHARED(0x6000)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{3}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x18, {R2,R3};[7:7:{0,3}:5:1]",
        "    R2UR UR10, R14;[2:7:{1}:5:1]",
        "    R2UR UR11, R15;[2:7:{1}:5:1]",
        "    UMOV UR6, 0x1000;[7:7:{}:1:0]",
        "    UMOV UR7, 0x500;[7:7:{}:1:0]",
        f"    UMOV UR8, 0x{size // 16:x};[7:7:{{}}:1:0]",
        "    UMOV UR12, 0x1;[7:7:{}:1:0]",
        "    UMOV UR15, 0x0;[7:7:{}:1:0]",
        "    UIADD3 UR12, UPT, UPT, -UR12, 0x100000, UR15;[7:7:{}:5:1]",
        "    USHF.L.U32 UR13, UR12, 0xb, UR15;[7:7:{}:5:1]",
        "    USHF.L.U32 UR12, UR12, 0x1, UR15;[7:7:{}:5:1]",
        "    LOP3.LUT R43, R4, 0x1f, RZ, 0xc0;[7:7:{3}:5:1]",
        f"    SHF.L.U32 R43, R43, 0x{addr_shift:x}, RZ;[7:7:{{}}:5:1]",
        "    MOV32I R40, 0x89abcdef;[7:7:{}:5:1]",
        f"    MOV32I R0, 0x{size * copies:x};[7:7:{{}}:5:1]",
        "    ISETP.EQ.U32.AND P6, PT, R4, RZ, PT;[7:7:{3}:13:1]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        # Every warp writes the same init token before the CTA barrier.  The
        # uniform SYNCS variant cannot use a lane predicate; repeated atomic
        # exchanges are harmless because no arrive/copy can precede the BAR.
        "    SYNCS.EXCH.64 {UR0,UR1}, [UR7], {UR12,UR13};[3:4:{}:5:1]",
        "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
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
        lines += [
            "    UBLKCP.S.G {UR6,UR7}, {UR10,UR11}, UR8;[7:0:{2}:1:0]"
            for _ in range(copies)
        ]
        lines += [
            "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR7], R0;[7:0:{0}:1:0]",
            "#def_label(poll)",
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR7], RZ;[4:7:{}:2:0]",
            "    @!P2 BRA #label(poll);[7:7:{4}:5:0]",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    LDS R30, [RZ+UR6];[5:7:{}:8:1]",
            "    STG.E [{R6,R7}+0x10], R30;[7:4:{5}:8:0]",
        ]
    else:
        lines += ["    NOP;[7:7:{}:5:1]" for _ in range(copies)]
        lines += [
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    MOV R30, RZ;[7:7:{}:5:1]",
            "    STG.E [{R6,R7}+0x10], R30;[7:4:{}:8:0]",
        ]
    lines += [
        "    STG.E.64 [{R6,R7}], {R18,R19};[7:4:{}:8:0]",
        "    STG.E.64 [{R6,R7}+8], {R20,R21};[7:4:{}:8:0]",
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
        "    STG.E.64 [{R6,R7}], {R24,R25};[7:4:{}:8:0]",
        "    STG.E.64 [{R6,R7}+8], {R26,R27};[7:4:{}:8:0]",
        "#def_label(exit)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(size: int, copies: int, contender_count: int, mode: str,
            contender_op: str, addr_shift: int, arch: str,
            reps: int) -> tuple[float, float]:
    cubin = assemble(source(size, copies, contender_count, mode, contender_op,
                            addr_shift), arch=arch, check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(256 * 24)
    data = mod.devmem_alloc(0x8000)
    pattern = struct.pack("<8192I", *([0x12345678] * 8192))
    mod.device_write(data, pattern)
    tma: list[int] = []
    contender: list[int] = []
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 256 * 24 // 4)
            mod.launch("ublkload", grid=(1,), block=(256,), args=[out, data],
                       shared_mem=0x6000)
            mod.synchronize()
            raw = mod.device_read(out, 256 * 24)
            if mode in ("solo_t", "overlay"):
                copied, = struct.unpack_from("<I", raw, 16)
                if copied != 0x12345678:
                    raise RuntimeError(f"copy validation failed: {copied:#x}")
            if rep:
                starts_ends = [struct.unpack_from("<QQ", raw, tid * 24)
                               for tid in range(256)]
                start, end = starts_ends[0]
                tma.append((end - start) & ((1 << 64) - 1))
                spans = [((starts_ends[tid][1] - starts_ends[tid][0]) &
                          ((1 << 64) - 1)) for tid in (128, 160, 192, 224)]
                contender.append(statistics.median(spans))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return statistics.median(tma), statistics.median(contender)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes", default="128,512,1024,4096,8192,16384")
    p.add_argument("--copies", type=int, default=16)
    p.add_argument("--contender-count", type=int, default=512)
    p.add_argument("--contender-op", choices=("sts", "lds", "shfl"),
                   default="sts")
    p.add_argument("--addr-shift", type=int, choices=(2, 3, 4, 5), default=4)
    p.add_argument("--arch", choices=("sm90", "sm120"), default="sm90")
    p.add_argument("--reps", type=int, default=11)
    ns = p.parse_args()
    sizes = [int(x, 0) for x in ns.sizes.split(",") if x]
    print(f"copies={ns.copies} contender={ns.contender_op} shift={ns.addr_shift}")
    print("size total_KiB Tsolo Tover Cctrl Cover delta bytes/dcycle")
    for size in sizes:
        args = (size, ns.copies, ns.contender_count)
        opts = (ns.contender_op, ns.addr_shift, ns.arch, ns.reps)
        ts, _ = measure(*args, "solo_t", *opts)
        _, cc = measure(*args, "control", *opts)
        to, co = measure(*args, "overlay", *opts)
        delta = co - cc
        total = size * ns.copies
        rate = total / delta if delta > 0 else float("inf")
        print(f"{size:5d} {total / 1024:9.1f} {ts:5.1f} {to:5.1f} "
              f"{cc:5.1f} {co:5.1f} {delta:5.1f} {rate:12.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
