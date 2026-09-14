#!/usr/bin/env python3
"""Measure Hopper tensor-TMA descriptor-cache hit and miss latency.

Each launch performs two sequential 256-byte UTMALDG.2D loads.  The first uses
a descriptor address never used by an earlier launch.  The second either
reuses that address (hit), uses another fresh but byte-identical descriptor
(miss), or invalidates and reuses the first address (invalidate).  Both maps
point at the same tensor, keeping the second data access equally cache-warm.
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


def source(mode: str, gap: int = 0) -> str:
    if mode not in ("hit", "miss", "miss-gap", "invalidate", "prefetch"):
        raise ValueError(f"bad mode: {mode}")
    if gap < 0:
        raise ValueError("gap must be non-negative")
    second_desc = 18 if mode in ("miss", "miss-gap", "prefetch") else 16
    control = ""
    if mode == "invalidate":
        control = "    UTMACCTL.IV [UR16];[7:3:{}:5:1]\n"
    elif mode == "prefetch":
        control = "    UTMACCTL.PF [UR18];[7:3:{}:5:1]\n"
    if mode in ("miss-gap", "invalidate", "prefetch"):
        control += "".join("    NOP;[7:7:{}:8:1]\n" for _ in range(gap))
    return f"""#fn utmadesc(desc0<8>, desc1<8>, out<8>) {{
    #pragma MAXREG_COUNT(48)
    #pragma NUM_MBARRIERS(2)
    #pragma SHARED(0x4000)
    LDC.64 {{R2,R3}}, #param(out);[5:7:{{}}:1:0]
    LDCU.64 {{UR16,UR17}}, #param(desc0);[1:7:{{}}:1:0]
    LDCU.64 {{UR18,UR19}}, #param(desc1);[2:7:{{}}:1:0]
    S2R R4, SR_TID.X;[4:7:{{}}:5:1]
    ISETP.EQ.U32.AND P1, PT, R4, RZ, PT;[7:7:{{4}}:13:1]
    @!P1 BRA #label(consumer1);[7:7:{{}}:5:1]
    UMOV UR40, 0x1;[7:7:{{}}:1:0]
    UMOV UR43, 0x0;[7:7:{{}}:1:0]
    UIADD3 UR40, UPT, UPT, -UR40, 0x100000, UR43;[7:7:{{}}:5:1]
    USHF.L.U32 UR41, UR40, 0xb, UR43;[7:7:{{}}:5:1]
    USHF.L.U32 UR40, UR40, 0x1, UR43;[7:7:{{}}:5:1]
    UMOV UR8, 0x400;[7:7:{{}}:1:0]
    UMOV UR9, 0x600;[7:7:{{}}:1:0]
    UMOV UR10, 0x0;[7:7:{{}}:1:0]
    UMOV UR11, 0x0;[7:7:{{}}:1:0]
    UMOV UR12, 0x800;[7:7:{{}}:1:0]
    UMOV UR13, 0x608;[7:7:{{}}:1:0]
    UMOV UR14, 0x0;[7:7:{{}}:1:0]
    UMOV UR15, 0x0;[7:7:{{}}:1:0]
    MOV32I R0, 0x100;[7:7:{{}}:5:1]
    FENCE.VIEW.ASYNC.S;[7:7:{{}}:5:1]
    SYNCS.EXCH.64 {{UR44,UR45}}, [UR9], {{UR40,UR41}};[3:1:{{}}:5:1]
    SYNCS.EXCH.64 {{UR44,UR45}}, [UR13], {{UR40,UR41}};[3:1:{{}}:5:1]
    MEMBAR.ALL.CTA;[7:7:{{3}}:5:1]
    FENCE.VIEW.ASYNC.S;[7:7:{{}}:5:1]
    CS2R {{R20,R21}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    SYNCS.ARRIVE.TRANS64 {{RZ,RZ}}, [RZ+UR9], R0;[7:0:{{}}:1:0]
    UTMALDG.2D [UR8], [UR16];[7:3:{{1}}:12:1]
#def_label(consumer1)
#def_label(poll1)
    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR9], RZ;[0:7:{{}}:2:0]
    @!P0 BRA #label(poll1);[7:7:{{0}}:5:0]
    CS2R {{R22,R23}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    @!P1 BRA #label(consumer2);[7:7:{{}}:5:1]
{control}    SYNCS.ARRIVE.TRANS64 {{RZ,RZ}}, [RZ+UR13], R0;[7:0:{{}}:1:0]
    UTMALDG.2D [UR12], [UR{second_desc}];[7:3:{{{2 if second_desc == 18 else 1}}}:12:1]
#def_label(consumer2)
#def_label(poll2)
    SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR13], RZ;[0:7:{{}}:2:0]
    @!P0 BRA #label(poll2);[7:7:{{0}}:5:0]
    CS2R {{R24,R25}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    @!P1 BRA #label(exit);[7:7:{{}}:5:1]
    LDS R30, [RZ+0x400];[3:7:{{}}:8:1]
    LDS R31, [RZ+0x800];[2:7:{{}}:8:1]
    STG.E.64 [{{R2,R3}}], {{R20,R21}};[7:0:{{5}}:8:0]
    STG.E.64 [{{R2,R3}}+8], {{R22,R23}};[7:0:{{5}}:8:0]
    STG.E.64 [{{R2,R3}}+0x10], {{R24,R25}};[7:0:{{5}}:8:0]
    STG.E [{{R2,R3}}+0x18], R30;[7:0:{{3,5}}:8:0]
    STG.E [{{R2,R3}}+0x1c], R31;[7:0:{{2,5}}:8:0]
#def_label(exit)
    EXIT;[7:7:{{}}:5:0]
}}"""


def make_map(global_addr: int) -> bytes:
    buf = ctypes.create_string_buffer(128)
    shape = (ctypes.c_uint64 * 2)(16, 16)
    stride = (ctypes.c_uint64 * 1)(32)
    box = (ctypes.c_uint32 * 2)(16, 8)
    elem = (ctypes.c_uint32 * 2)(1, 1)
    rc = cuTensorMapEncodeTiled(buf, 6, 2, global_addr, shape, stride,
                                box, elem, 0, 0, 0, 0)
    if rc:
        raise RuntimeError(f"cuTensorMapEncodeTiled failed: {rc}")
    return bytes(buf.raw)


def measure(mode: str, gap: int, reps: int) -> tuple[float, float, float]:
    mod = CudaModule(assemble(source(mode, gap), arch="sm90", check_deps=True))
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(512)
    # A 256-byte tile contains half values 1..128 in its first eight rows.
    mod.device_write(data, struct.pack("<256H", *range(1, 257)))
    desc_stride = 256
    maps = mod.devmem_alloc(2 * (reps + 1) * desc_stride)
    one = make_map(data)
    image = bytearray(2 * (reps + 1) * desc_stride)
    for slot in range(2 * (reps + 1)):
        off = slot * desc_stride
        image[off:off + 128] = one
    mod.device_write(maps, bytes(image))
    first, second, total = [], [], []
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 8)
            d0 = maps + (2 * rep) * desc_stride
            d1 = maps + (2 * rep + 1) * desc_stride
            mod.launch("utmadesc", grid=(1,), block=(32,),
                       args=[d0, d1, out], shared_mem=0x4000)
            mod.synchronize()
            raw = mod.device_read(out, 32)
            a, b, c = struct.unpack_from("<QQQ", raw)
            v0, v1 = struct.unpack_from("<II", raw, 0x18)
            if (v0, v1) != (0x00020001, 0x00020001):
                raise RuntimeError(f"data validation failed: {v0:#x}, {v1:#x}")
            if rep:
                first.append((b - a) & ((1 << 64) - 1))
                second.append((c - b) & ((1 << 64) - 1))
                total.append((c - a) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(maps)
        mod.devmem_free(data)
        mod.devmem_free(out)
    return (statistics.median(first), statistics.median(second),
            statistics.median(total))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--modes", default="hit,miss,invalidate")
    p.add_argument("--gap", type=int, default=0,
                   help="stall-8 NOPs after PF/IV or in miss-gap control")
    p.add_argument("--reps", type=int, default=21)
    ns = p.parse_args()
    print("mode first_cold second total second_minus_first")
    for mode in (x for x in ns.modes.split(",") if x):
        first, second, total = measure(mode, ns.gap, ns.reps)
        print(f"{mode:10s} {first:10.1f} {second:6.1f} {total:6.1f} "
              f"{second-first:18.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
