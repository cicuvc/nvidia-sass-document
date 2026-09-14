#!/usr/bin/env python3
"""Test whether UBLKCP.G.S and UBLKCP.S.G can run full duplex on Hopper.

Warp 0 issues shared-to-global copies and warp 5 issues global-to-shared copies,
placing the producers on different SMSPs.  Solo modes replace the other warp's
commands with NOPs.  The S.G result and mbarrier phase are both validated.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(size: int, copies: int, mode: str) -> str:
    if size % 16 or not 16 <= size <= 8192:
        raise ValueError("size must be 16..8192 and a multiple of 16")
    if mode not in ("solo_gs", "solo_sg", "dual"):
        raise ValueError("bad mode")
    run_gs = mode in ("solo_gs", "dual")
    run_sg = mode in ("solo_sg", "dual")
    lines = [
        "#fn ublkduplex(out<8>, gsrc<8>, gdst<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma SHARED(0x6000)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(gsrc);[1:7:{}:1:0]",
        "    LDC.64 {R16,R17}, #param(gdst);[2:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{3}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x18, {R2,R3};[7:7:{0,3}:5:1]",
        "    R2UR UR20, R14;[4:7:{1}:5:1]",
        "    R2UR UR21, R15;[4:7:{1}:5:1]",
        "    R2UR UR30, R16;[5:7:{2}:5:1]",
        "    R2UR UR31, R17;[5:7:{2}:5:1]",
        # G.S source, G.S size; S.G destination, mbarrier, and size.
        "    UMOV UR22, 0x1000;[7:7:{}:1:0]",
        f"    UMOV UR23, 0x{size // 16:x};[7:7:{{}}:1:0]",
        "    UMOV UR24, 0x3000;[7:7:{}:1:0]",
        "    UMOV UR25, 0x5f00;[7:7:{}:1:0]",
        f"    UMOV UR26, 0x{size // 16:x};[7:7:{{}}:1:0]",
        f"    MOV32I R0, 0x{size * copies:x};[7:7:{{}}:5:1]",
        "    ISETP.EQ.U32.AND P6, PT, R4, 0xa0, PT;[7:7:{3}:13:1]",
        "    UMOV UR40, 0x1;[7:7:{}:1:0]",
        "    UMOV UR43, 0x0;[7:7:{}:1:0]",
        "    UIADD3 UR40, UPT, UPT, -UR40, 0x100000, UR43;[7:7:{}:5:1]",
        "    USHF.L.U32 UR41, UR40, 0xb, UR43;[7:7:{}:5:1]",
        "    USHF.L.U32 UR40, UR40, 0x1, UR43;[7:7:{}:5:1]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    SYNCS.EXCH.64 {UR42,UR43}, [UR25], {UR40,UR41};[3:4:{}:5:1]",
        "    MEMBAR.ALL.CTA;[7:7:{3}:5:1]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.U32.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(gs_path);[7:7:{}:5:1]",
        "    ISETP.EQ.U32.AND P1, PT, R5, 0x5, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(sg_path);[7:7:{}:5:1]",
        "    BRA #label(exit);[7:7:{}:5:1]",
        "#def_label(gs_path)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_gs:
        lines += [
            "    UBLKCP.G.S {UR30,UR31}, [UR22], UR23;[7:0:{5}:1:0]"
            for _ in range(copies)
        ]
        lines += [
            "    UTMACMDFLUSH;[7:0:{5}:1:0]",
            "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        ]
    else:
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(copies + 2)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    BRA #label(record);[7:7:{}:5:1]",
        "#def_label(sg_path)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_sg:
        lines += [
            "    UBLKCP.S.G {UR24,UR25}, {UR20,UR21}, UR26;[7:0:{4}:1:0]"
            for _ in range(copies)
        ]
        lines += [
            "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR25], R0;[7:0:{0}:1:0]",
            "#def_label(poll)",
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR25], RZ;[4:7:{}:2:0]",
            "    @!P2 BRA #label(poll);[7:7:{4}:5:0]",
        ]
    else:
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(copies + 3)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_sg:
        lines += [
            "    LDS R30, [RZ+UR24];[5:7:{}:8:1]",
            "    STG.E [{R6,R7}+0x10], R30;[7:4:{5}:8:0]",
        ]
    lines += [
        "#def_label(record)",
        "    STG.E.64 [{R6,R7}], {R18,R19};[7:4:{}:8:0]",
        "    STG.E.64 [{R6,R7}+8], {R20,R21};[7:4:{}:8:0]",
        "#def_label(exit)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(size: int, copies: int, mode: str, reps: int) -> tuple[float, float]:
    cubin = assemble(source(size, copies, mode), arch="sm90", check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(256 * 24)
    gsrc = mod.devmem_alloc(0x8000)
    gdst = mod.devmem_alloc(0x8000)
    mod.device_write(gsrc, struct.pack("<8192I", *([0x12345678] * 8192)))
    times = {0: [], 160: []}
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 256 * 24 // 4)
            mod.devmem_set(gdst, 0, 0x8000 // 4)
            mod.launch("ublkduplex", grid=(1,), block=(256,),
                       args=[out, gsrc, gdst], shared_mem=0x6000)
            mod.synchronize()
            raw = mod.device_read(out, 256 * 24)
            if mode in ("solo_sg", "dual"):
                value, = struct.unpack_from("<I", raw, 160 * 24 + 0x10)
                if value != 0x12345678:
                    raise RuntimeError(f"S.G validation failed: {value:#x}")
            if rep:
                for tid in times:
                    a, b = struct.unpack_from("<QQ", raw, tid * 24)
                    times[tid].append((b - a) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(gdst)
        mod.devmem_free(gsrc)
        mod.devmem_free(out)
    return statistics.median(times[0]), statistics.median(times[160])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes", default="512,1024,4096,8192")
    p.add_argument("--copies", type=int, default=32)
    p.add_argument("--reps", type=int, default=13)
    ns = p.parse_args()
    print("size total_KiB GSsolo GSdual ratio SGsolo SGdual ratio")
    for size in (int(x, 0) for x in ns.sizes.split(",") if x):
        gs, _ = measure(size, ns.copies, "solo_gs", ns.reps)
        _, sg = measure(size, ns.copies, "solo_sg", ns.reps)
        gd, sd = measure(size, ns.copies, "dual", ns.reps)
        print(f"{size:5d} {size*ns.copies/1024:9.1f} "
              f"{gs:6.1f} {gd:6.1f} {gd/gs:5.3f} "
              f"{sg:6.1f} {sd:6.1f} {sd/sg:5.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
