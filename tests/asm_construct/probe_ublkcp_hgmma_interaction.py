#!/usr/bin/env python3
"""Measure UBLKCP directionality against HGMMA shared-operand reads.

Warpgroup 0 executes an SS HGMMA chain.  Warp 4 issues either UBLKCP.G.S or
UBLKCP.S.G; the remaining warps exit.  Independent clocks cover HGMMA issue and
drain, and TMA completion.  The S.G path additionally validates copied data.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from tests.asm_construct.probe_hgmma_mio_interaction import hgmma_body  # noqa: E402


def source(direction: str, size: int, copies: int, hn: int, mode: str,
           operand: str = "ss") -> str:
    if direction not in ("gs", "sg") or mode not in ("solo_h", "solo_t", "overlay"):
        raise ValueError("bad direction/mode")
    if size % 16 or not 16 <= size <= 16384:
        raise ValueError("bad UBLKCP size")
    run_h = mode in ("solo_h", "overlay")
    run_t = mode in ("solo_t", "overlay")
    lines = [
        "#fn ublkhgmma(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma SHARED(0x6000)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{3}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x20, {R2,R3};[7:7:{0,3}:5:1]",
        "    R2UR UR20, R14;[2:7:{1}:5:1]",
        "    R2UR UR21, R15;[2:7:{1}:5:1]",
        # HGMMA A/B raw descriptors: shared 0x400 and 0xc00.
        "    UMOV UR4, 0x400040;[7:7:{}:1:0]",
        "    UMOV UR5, 0x0;[7:7:{}:1:0]",
        "    UMOV UR6, 0x4000c0;[7:7:{}:1:0]",
        "    UMOV UR7, 0x0;[7:7:{}:1:0]",
        # TMA shared address and load-completion mbarrier.
        "    UMOV UR22, 0x2000;[7:7:{}:1:0]",
        "    UMOV UR23, 0x5f00;[7:7:{}:1:0]",
        f"    UMOV UR24, 0x{size // 16:x};[7:7:{{}}:1:0]",
        f"    MOV32I R0, 0x{size * copies:x};[7:7:{{}}:5:1]",
        "    ISETP.EQ.U32.AND P6, PT, R4, 0x80, PT;[7:7:{3}:13:1]",
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
        "    ISETP.LT.U32.AND P0, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(hpath);[7:7:{}:5:1]",
        "    ISETP.EQ.U32.AND P1, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(tpath);[7:7:{}:5:1]",
        "    BRA #label(exit);[7:7:{}:5:1]",
        "#def_label(hpath)",
        "    WARPGROUP.ARRIVE;[7:7:{}:5:1]",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_h:
        lines += hgmma_body(hn, shape=16, operand=operand)
    else:
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(hn)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_h:
        lines += ["    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]"]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    BRA #label(record);[7:7:{}:5:1]",
        "#def_label(tpath)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if run_t and direction == "gs":
        lines += [
            "    UBLKCP.G.S {UR20,UR21}, [UR22], UR24;[7:0:{2}:1:0]"
            for _ in range(copies)
        ]
        lines += [
            "    UTMACMDFLUSH;[7:0:{2}:1:0]",
            "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        ]
    elif run_t:
        lines += [
            "    UBLKCP.S.G {UR22,UR23}, {UR20,UR21}, UR24;[7:0:{2}:1:0]"
            for _ in range(copies)
        ]
        lines += [
            "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR23], R0;[7:0:{0}:1:0]",
            "#def_label(poll)",
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR23], RZ;[4:7:{}:2:0]",
            "    @!P2 BRA #label(poll);[7:7:{4}:5:0]",
        ]
    else:
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(copies)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    MOV R22, R20;[7:7:{}:5:1]",
        "    MOV R23, R21;[7:7:{}:5:1]",
    ]
    if run_t and direction == "sg":
        lines += [
            "    LDS R30, [RZ+UR22];[5:7:{}:8:1]",
            "    STG.E [{R6,R7}+0x18], R30;[7:4:{5}:8:0]",
        ]
    lines += [
        "#def_label(record)",
        "    STG.E.64 [{R6,R7}], {R18,R19};[7:4:{}:8:0]",
        "    STG.E.64 [{R6,R7}+8], {R20,R21};[7:4:{}:8:0]",
        "    STG.E.64 [{R6,R7}+0x10], {R22,R23};[7:4:{}:8:0]",
        "#def_label(exit)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(direction: str, size: int, copies: int, hn: int, mode: str,
            operand: str, reps: int) -> tuple[float, float, float]:
    cubin = assemble(source(direction, size, copies, hn, mode, operand), arch="sm90",
                     check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(256 * 32)
    data = mod.devmem_alloc(0x8000)
    mod.device_write(data, struct.pack("<8192I", *([0x12345678] * 8192)))
    hi: list[float] = []
    hd: list[float] = []
    tt: list[int] = []
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0, 256 * 32 // 4)
            mod.launch("ublkhgmma", grid=(1,), block=(256,), args=[out, data],
                       shared_mem=0x6000)
            mod.synchronize()
            raw = mod.device_read(out, 256 * 32)
            if direction == "sg" and mode in ("solo_t", "overlay"):
                value, = struct.unpack_from("<I", raw, 128 * 32 + 0x18)
                if value != 0x12345678:
                    raise RuntimeError(f"S.G validation failed: {value:#x}")
            if rep:
                h_issue, h_drain = [], []
                for tid in (0, 32, 64, 96):
                    a, b, c = struct.unpack_from("<QQQ", raw, tid * 32)
                    h_issue.append((b - a) & ((1 << 64) - 1))
                    h_drain.append((c - a) & ((1 << 64) - 1))
                a, b = struct.unpack_from("<QQ", raw, 128 * 32)
                hi.append(statistics.median(h_issue))
                hd.append(statistics.median(h_drain))
                tt.append((b - a) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return statistics.median(hi), statistics.median(hd), statistics.median(tt)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--direction", choices=("gs", "sg"), required=True)
    p.add_argument("--sizes", default="1024,4096,8192")
    p.add_argument("--copies", type=int, default=32)
    p.add_argument("--hn", type=int, default=256)
    p.add_argument("--operand", choices=("ss", "rs"), default="ss")
    p.add_argument("--reps", type=int, default=11)
    ns = p.parse_args()
    print("size Hsolo_issue Hover_issue delta_i Hsolo_drain Hover_drain delta_d Tsolo Tover")
    for size in (int(x, 0) for x in ns.sizes.split(",") if x):
        hs_i, hs_d, _ = measure(ns.direction, size, ns.copies, ns.hn,
                                "solo_h", ns.operand, ns.reps)
        _, _, ts = measure(ns.direction, size, ns.copies, ns.hn,
                           "solo_t", ns.operand, ns.reps)
        ho_i, ho_d, to = measure(ns.direction, size, ns.copies, ns.hn,
                                 "overlay", ns.operand, ns.reps)
        print(f"{size:5d} {hs_i:11.1f} {ho_i:11.1f} {ho_i-hs_i:7.1f} "
              f"{hs_d:11.1f} {ho_d:11.1f} {ho_d-hs_d:7.1f} "
              f"{ts:6.1f} {to:6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
