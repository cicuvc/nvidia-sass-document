#!/usr/bin/env python3
"""Place two warps on same/different subcores and locate cp.async group credits."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402


def source(n: int, head_copies: int, actors: tuple[int, int]) -> str:
    select = []
    for warp in actors:
        select += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;[7:7:{{}}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:5:1]",
        ]
    ops = []
    for i in range(head_copies):
        ops.append(
            f"    LDGSTS.E.32 [R31], desc[{{UR4,UR5}}]"
            f"[{{R20,R21}}+0x{i * 0x1000:x}];[7:2:{{}}:1:1]"
        )
    ops.append("    LDGDEPBAR;[0:7:{}:1:1]")
    for i in range(1, n):
        ops += [
            f"    LDGSTS.E.32 [R30+0x{0x100 + (i % 48) * 0x100:x}], "
            "desc[{UR4,UR5}][{R22,R23}];[7:2:{}:1:1]",
            "    LDGDEPBAR;[0:7:{}:1:1]",
        ]
    return "\n".join([
        "#fn groupshare(out<8>, src<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma SHARED(0x4000)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(src);[2:7:{}:1:0]",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[4:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[5:7:{}:5:1]",
        "    SHR.U32 R5, R4, 0x5;[7:7:{5}:5:1]",
        "    LOP3.LUT R8, R4, 0x1f, RZ, 0xc0;[7:7:{5}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R5, 0x20, {R2,R3};[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R12,R13}, R5, 0x40000, {R6,R7};[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R20,R21}, R8, 0x80, {R12,R13};[7:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R22,R23}, R8, 0x4, {R12,R13};[7:7:{}:5:1]",
        "    SHF.L.U32 R30, R8, 0x2, RZ;[7:7:{}:5:1]",
        "    SHF.L.U32 R31, R8, 0x7, RZ;[7:7:{}:5:1]",
        "    LDG.E.STRONG.GPU R40, desc[{UR4,UR5}][{R22,R23}];[3:7:{4}:1:1]",
        "    MOV RZ, R40;[7:7:{3}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        *select,
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(work)",
        "    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{}:5:0]",
        *ops,
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    DEPBAR.LE SB0, 0x{n - 1:x};[7:7:{{}}:5:1]",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        "    CS2R {R28,R29}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R24,R25};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x8], {R26,R27};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x10], {R32,R33};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x18], {R28,R29};[7:7:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def measure(n: int, actors: tuple[int, int], head_copies: int,
            reps: int) -> list[tuple[float, float, float, tuple[int, int]]]:
    mod = CudaModule(assemble(source(n, head_copies, actors), arch="sm120",
                              check_deps=False))
    out = mod.devmem_alloc(5 * 32)
    stride = 0x180000
    src = mod.devmem_alloc(reps * stride)
    mod.devmem_set(src, 0x12345678, reps * stride // 4)
    samples = {w: [] for w in actors}
    heads = {w: [] for w in actors}
    totals = {w: [] for w in actors}
    try:
        for rep in range(reps):
            mod.devmem_set(out, 0, 5 * 8)
            mod.launch("groupshare", grid=(1,), block=(32 * (max(actors) + 1),),
                       args=[out, src + rep * stride], shared_mem=0x4000)
            mod.synchronize()
            raw = mod.device_read(out, 5 * 32)
            for warp in actors:
                t0, t1, th, t2 = struct.unpack_from("<QQQQ", raw, warp * 32)
                samples[warp].append(t1 - t0)
                heads[warp].append(th - t0)
                totals[warp].append(t2 - t0)
    finally:
        mod.devmem_free(src)
        mod.devmem_free(out)
    return [(statistics.median(samples[w]), statistics.median(heads[w]),
             statistics.median(totals[w]),
             (min(samples[w]), max(samples[w])))
            for w in actors]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--placement", choices=("same", "diff"), default="same")
    ap.add_argument("--ns", default="20,24,26,27,28,32,40,48,54,55")
    ap.add_argument("--head-copies", type=int, default=32)
    ap.add_argument("--reps", type=int, default=21)
    args = ap.parse_args()
    actors = (0, 4) if args.placement == "same" else (0, 1)
    print(f"placement={args.placement} actors={actors} head={args.head_copies}")
    for n in (int(x) for x in args.ns.split(",") if x):
        result = measure(n, actors, args.head_copies, args.reps)
        print(f"N={n:2d} " + " ".join(
            f"w{w}={med:.0f}/{head:.0f}/{total:.0f}[{span[0]}..{span[1]}]"
            for w, (med, head, total, span) in zip(actors, result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
