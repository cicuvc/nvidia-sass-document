#!/usr/bin/env python3
"""Measure tensor-mode TMA S->G issue backpressure and group completion.

One elected lane issues repeated same-descriptor UTMASTG.2D operations.  The
descriptor is prefetched before timing.  Clocks bracket instruction issue and
UTMACMDFLUSH/DEPBAR completion, making the result directly comparable with the
UBLKCP.G.S outstanding probe.
"""

from __future__ import annotations

import argparse
import ctypes
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from tools.tma_helper import cuTensorMapEncodeTiled  # noqa: E402


def source(tile_bytes: int, count: int, active: bool) -> str:
    if tile_bytes % 256 or not 256 <= tile_bytes <= 16384:
        raise ValueError("tile-bytes must be a multiple of 256 in [256,16384]")
    if count < 1:
        raise ValueError("count must be positive")
    op = ("    UTMASTG.2D [UR8], [UR16];[7:2:{}:1:0]" if active
          else "    NOP;[7:7:{}:1:0]")
    issue = "\n".join(op for _ in range(count))
    warmup_gap = "".join("    NOP;[7:7:{}:8:1]\n" for _ in range(40))
    drain = """
    UTMACMDFLUSH;[7:0:{}:1:0]
    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]
""" if active else ""
    return f"""#fn utmastgdepth(desc<8>, out<8>) {{
    #pragma MAXREG_COUNT(40)
    #pragma SHARED(0x6000)
    LDC.64 {{R2,R3}}, #param(out);[5:7:{{}}:1:0]
    LDCU.64 {{UR16,UR17}}, #param(desc);[1:7:{{}}:1:0]
    S2R R4, SR_TID.X;[4:7:{{}}:5:1]
    ISETP.EQ.U32.AND P1, PT, R4, RZ, PT;[7:7:{{4}}:13:1]
    @!P1 BRA #label(consumer);[7:7:{{}}:5:1]
    MOV32I R0, 0x12345678;[7:7:{{}}:5:1]
    STS [RZ+0x1000], R0;[3:7:{{}}:8:1]
    UMOV UR8, 0x1000;[7:7:{{}}:1:0]
    UMOV UR9, 0x0;[7:7:{{}}:1:0]
    UMOV UR10, 0x0;[7:7:{{}}:1:0]
    MEMBAR.ALL.CTA;[7:7:{{3}}:5:1]
    FENCE.VIEW.ASYNC.S;[7:7:{{}}:5:1]
    UTMACCTL.PF [UR16];[7:3:{{1}}:5:1]
{warmup_gap}    CS2R {{R20,R21}}, SR_CLOCKLO;[7:7:{{}}:5:0]
{issue}
    CS2R {{R22,R23}}, SR_CLOCKLO;[7:7:{{}}:5:0]
{drain}    CS2R {{R24,R25}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    STG.E.64 [{{R2,R3}}], {{R20,R21}};[7:0:{{5}}:8:0]
    STG.E.64 [{{R2,R3}}+8], {{R22,R23}};[7:0:{{5}}:8:0]
    STG.E.64 [{{R2,R3}}+0x10], {{R24,R25}};[7:0:{{5}}:8:0]
#def_label(consumer)
    EXIT;[7:7:{{}}:5:0]
}}"""


def make_map(global_addr: int, tile_bytes: int) -> bytes:
    rows = tile_bytes // 256
    buf = ctypes.create_string_buffer(128)
    shape = (ctypes.c_uint64 * 2)(256, rows)
    stride = (ctypes.c_uint64 * 1)(256)
    box = (ctypes.c_uint32 * 2)(256, rows)
    elem = (ctypes.c_uint32 * 2)(1, 1)
    rc = cuTensorMapEncodeTiled(buf, 0, 2, global_addr, shape, stride,
                                box, elem, 0, 0, 0, 0)
    if rc:
        raise RuntimeError(f"cuTensorMapEncodeTiled failed: {rc}")
    return bytes(buf.raw)


def measure(tile_bytes: int, count: int, active: bool,
            reps: int, arch: str) -> tuple[float, float, float]:
    mod = CudaModule(assemble(source(tile_bytes, count, active), arch=arch,
                              check_deps=True))
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(tile_bytes)
    desc = mod.devmem_alloc(128)
    mod.device_write(desc, make_map(data, tile_bytes))
    issue, tail, total = [], [], []
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 8)
            mod.devmem_set(data, 0, tile_bytes // 4)
            mod.launch("utmastgdepth", grid=(1,), block=(32,),
                       args=[desc, out], shared_mem=0x6000)
            mod.synchronize()
            if active:
                value, = struct.unpack("<I", mod.device_read(data, 4))
                if value != 0x12345678:
                    raise RuntimeError(f"validation failed: {value:#x}")
            if rep:
                a, b, c = struct.unpack_from("<QQQ", mod.device_read(out, 24))
                issue.append((b - a) & ((1 << 64) - 1))
                tail.append((c - b) & ((1 << 64) - 1))
                total.append((c - a) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(desc)
        mod.devmem_free(data)
        mod.devmem_free(out)
    return (statistics.median(issue), statistics.median(tail),
            statistics.median(total))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tile-bytes", type=int, default=4096)
    p.add_argument("--counts", default="1,2,4,8,12,16,24,32,48,64")
    p.add_argument("--reps", type=int, default=13)
    p.add_argument("--arch", choices=("sm90", "sm120"), default="sm90")
    ns = p.parse_args()
    print("count nop_issue tma_issue excess tail total issue_delta")
    prev_n = prev_issue = None
    for count in (int(x) for x in ns.counts.split(",") if x):
        ni, _, _ = measure(ns.tile_bytes, count, False, ns.reps, ns.arch)
        ti, tail, total = measure(ns.tile_bytes, count, True, ns.reps, ns.arch)
        slope = ((ti - prev_issue) / (count - prev_n)
                 if prev_n is not None else float("nan"))
        print(f"{count:5d} {ni:9.1f} {ti:9.1f} {ti-ni:7.1f} "
              f"{tail:7.1f} {total:7.1f} {slope:11.2f}")
        prev_n, prev_issue = count, ti
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
