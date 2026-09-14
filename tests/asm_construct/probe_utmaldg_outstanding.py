#!/usr/bin/env python3
"""Measure tensor-mode TMA G->S issue backpressure and completion throughput.

One elected lane issues repeated UTMALDG.2D requests using one descriptor and
one destination.  UTMACCTL.PF plus a 320-cycle gap warms the descriptor cache
before the timed region, isolating request generation/data service from the
descriptor-miss path.  End-of-issue and mbarrier-completion clocks match the
non-tensor UBLKCP outstanding probe.
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
    if count < 1 or tile_bytes * count >= (1 << 20):
        raise ValueError("empty request list or expect-tx exceeds 20-bit limit")
    ops = []
    for _ in range(count):
        if active:
            ops.append("    UTMALDG.2D [UR8], [UR16];[7:3:{}:12:1]")
        else:
            ops.append("    NOP;[7:7:{}:12:1]")
    issue = "\n".join(ops)
    warmup_gap = "".join("    NOP;[7:7:{}:8:1]\n" for _ in range(40))
    completion = """
    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR9], RZ;[0:7:{}:2:0]
    @!P0 BRA #label(poll);[7:7:{0}:5:0]
""" if active else ""
    return f"""#fn utmadepth(desc<8>, out<8>) {{
    #pragma MAXREG_COUNT(40)
    #pragma NUM_MBARRIERS(1)
    #pragma SHARED(0x6000)
    LDC.64 {{R2,R3}}, #param(out);[5:7:{{}}:1:0]
    LDCU.64 {{UR16,UR17}}, #param(desc);[1:7:{{}}:1:0]
    S2R R4, SR_TID.X;[4:7:{{}}:5:1]
    ISETP.EQ.U32.AND P1, PT, R4, RZ, PT;[7:7:{{4}}:13:1]
    @!P1 BRA #label(consumer);[7:7:{{}}:5:1]
    UMOV UR8, 0x1000;[7:7:{{}}:1:0]
    UMOV UR9, 0x500;[7:7:{{}}:1:0]
    UMOV UR10, 0x0;[7:7:{{}}:1:0]
    UMOV UR11, 0x0;[7:7:{{}}:1:0]
    UMOV UR20, 0x1;[7:7:{{}}:1:0]
    UMOV UR23, 0x0;[7:7:{{}}:1:0]
    UIADD3 UR20, UPT, UPT, -UR20, 0x100000, UR23;[7:7:{{}}:5:1]
    USHF.L.U32 UR21, UR20, 0xb, UR23;[7:7:{{}}:5:1]
    USHF.L.U32 UR20, UR20, 0x1, UR23;[7:7:{{}}:5:1]
    MOV32I R0, 0x{tile_bytes * count:x};[7:7:{{}}:5:1]
    FENCE.VIEW.ASYNC.S;[7:7:{{}}:5:1]
    SYNCS.EXCH.64 {{UR22,UR23}}, [UR9], {{UR20,UR21}};[3:0:{{}}:5:1]
    MEMBAR.ALL.CTA;[7:7:{{3}}:5:1]
    FENCE.VIEW.ASYNC.S;[7:7:{{}}:5:1]
    UTMACCTL.PF [UR16];[7:3:{{1}}:5:1]
{warmup_gap}    CS2R {{R20,R21}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    SYNCS.ARRIVE.TRANS64 {{RZ,RZ}}, [RZ+UR9], R0;[7:0:{{}}:1:0]
{issue}
    CS2R {{R22,R23}}, SR_CLOCKLO;[7:7:{{}}:5:0]
#def_label(consumer)
#def_label(poll)
{completion}    CS2R {{R24,R25}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    @!P1 BRA #label(exit);[7:7:{{}}:5:1]
    STG.E.64 [{{R2,R3}}], {{R20,R21}};[7:0:{{5}}:8:0]
    STG.E.64 [{{R2,R3}}+8], {{R22,R23}};[7:0:{{5}}:8:0]
    STG.E.64 [{{R2,R3}}+0x10], {{R24,R25}};[7:0:{{5}}:8:0]
    LDS R30, [RZ+0x1000];[2:7:{{}}:8:1]
    STG.E [{{R2,R3}}+0x18], R30;[7:0:{{2,5}}:8:0]
#def_label(exit)
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
            reps: int) -> tuple[float, float, float]:
    mod = CudaModule(assemble(source(tile_bytes, count, active), arch="sm90",
                              check_deps=True))
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(tile_bytes)
    mod.device_write(data, struct.pack("<I", 0x12345678) +
                     bytes(tile_bytes - 4))
    desc = mod.devmem_alloc(128)
    mod.device_write(desc, make_map(data, tile_bytes))
    issue, tail, total = [], [], []
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 8)
            mod.launch("utmadepth", grid=(1,), block=(32,), args=[desc, out],
                       shared_mem=0x6000)
            mod.synchronize()
            raw = mod.device_read(out, 32)
            if active:
                value, = struct.unpack_from("<I", raw, 0x18)
                if value != 0x12345678:
                    raise RuntimeError(f"validation failed: {value:#x}")
            if rep:
                a, b, c = struct.unpack_from("<QQQ", raw)
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
    ns = p.parse_args()
    print("count nop_issue tma_issue excess tail total issue_delta")
    prev_n = prev_issue = None
    for count in (int(x) for x in ns.counts.split(",") if x):
        ni, _, _ = measure(ns.tile_bytes, count, False, ns.reps)
        ti, tail, total = measure(ns.tile_bytes, count, True, ns.reps)
        slope = ((ti - prev_issue) / (count - prev_n)
                 if prev_n is not None else float("nan"))
        print(f"{count:5d} {ni:9.1f} {ti:9.1f} {ti-ni:7.1f} "
              f"{tail:7.1f} {total:7.1f} {slope:11.2f}")
        prev_n, prev_issue = count, ti
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
