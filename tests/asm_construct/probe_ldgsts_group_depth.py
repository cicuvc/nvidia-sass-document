#!/usr/bin/env python3
"""Find LDGSTS committed-group backpressure by timing commit-per-copy."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402


def source(n: int, style: str, head_copies: int) -> str:
    ops = []
    if style in ("split", "split3"):
        nsb = 2 if style == "split" else 3
        for sb in range(nsb):
            for i in range(head_copies):
                off = (sb * head_copies + i) * 0x1000
                ops.append(
                    f"    LDGSTS.E.32 [R30], desc[{{UR4,UR5}}]"
                    f"[{{R20,R21}}+0x{off:x}];[7:2:{{}}:1:1]"
                )
            ops.append(f"    LDGDEPBAR;[{sb}:7:{{}}:1:1]")
        for i in range(nsb, n):
            sb = i % nsb
            ops += [
                f"    LDGSTS.E.32 [R30+0x{0x100 + (i % 48) * 0x100:x}], "
                "desc[{UR4,UR5}][{R22,R23}];[7:2:{}:1:1]",
                f"    LDGDEPBAR;[{sb}:7:{{}}:1:1]",
            ]
    elif style == "headslow":
        # Keep group 0 open until sixteen scattered copies close, then place
        # many quick one-copy groups behind it.  Ordered retirement prevents
        # the younger records from draining around the deliberately long head.
        for i in range(head_copies):
            ops.append(
                f"    LDGSTS.E.32 [R30], desc[{{UR4,UR5}}]"
                f"[{{R20,R21}}+0x{i * 0x1000:x}];[7:2:{{}}:1:1]"
            )
        ops.append("    LDGDEPBAR;[0:7:{}:1:1]")
        for i in range(1, n):
            ops += [
                f"    LDGSTS.E.32 [R30+0x{0x100 + i * 0x100:x}], "
                "desc[{UR4,UR5}][{R22,R23}];[7:2:{}:1:1]",
                "    LDGDEPBAR;[0:7:{}:1:1]",
            ]
    else:
        for i in range(n):
            ops.append(
                f"    LDGSTS.E.32 [R30+0x{0x100 + i * 0x100:x}], "
                f"desc[{{UR4,UR5}}][{{R20,R21}}+0x{i * 0x1000:x}];"
                "[7:2:{}:1:1]"
            )
            if style == "many":
                ops.append("    LDGDEPBAR;[0:7:{}:1:1]")
    if style == "one":
        ops.append("    LDGDEPBAR;[0:7:{}:1:1]")
    return "\n".join([
        "#fn groupdepth(out<8>, src<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma SHARED(0x4000)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(src);[2:7:{}:1:0]",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[4:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[5:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R4, 0x18, {R2,R3};[7:7:{1,5}:5:1]",
        # Thirty-two independent source lines per copy make completion slow.
        "    IMAD.WIDE.U32 {R20,R21}, R4, 0x80, {R6,R7};[7:7:{2,5}:5:1]",
        "    IMAD.WIDE.U32 {R22,R23}, R4, 0x4, {R6,R7};[7:7:{2,5}:5:1]",
        "    SHF.L.U32 R30, R4, 0x2, RZ;[7:7:{5}:5:1]",
        *( ["    LDG.E.STRONG.GPU R40, desc[{UR4,UR5}][{R22,R23}];[3:7:{4}:1:1]",
            "    MOV RZ, R40;[7:7:{3}:5:1]"]
           if style in ("headslow", "split", "split3") else [] ),
        "    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{4}:5:0]",
        *ops,
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        *( ["    DEPBAR.LE SB1, 0x0;[7:7:{}:5:1]"]
           if style in ("split", "split3") else [] ),
        *( ["    DEPBAR.LE SB2, 0x0;[7:7:{}:5:1]"] if style == "split3" else [] ),
        "    CS2R {R28,R29}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R24,R25};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x8], {R26,R27};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x10], {R28,R29};[7:7:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def measure(n: int, style: str, head_copies: int,
            reps: int) -> tuple[float, float, tuple[int, int]]:
    mod = CudaModule(assemble(source(n, style, head_copies), arch="sm120",
                              check_deps=False))
    out = mod.devmem_alloc(32 * 24)
    stride = (n * 0x1000 + 0xffff) & ~0xffff
    src = mod.devmem_alloc(reps * stride)
    mod.devmem_set(src, 0x12345678, reps * stride // 4)
    issue, total = [], []
    try:
        for rep in range(reps):
            mod.launch("groupdepth", grid=(1,), block=(32,),
                       args=[out, src + rep * stride], shared_mem=0x4000)
            mod.synchronize()
            t0, t1, t2 = struct.unpack_from("<QQQ", mod.device_read(out, 24), 0)
            issue.append(t1 - t0)
            total.append(t2 - t0)
    finally:
        mod.devmem_free(src)
        mod.devmem_free(out)
    return statistics.median(issue), statistics.median(total), (min(issue), max(issue))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ns", default="1,2,3,4,5,6,7,8,9,10,12,16,20,24")
    ap.add_argument("--reps", type=int, default=15)
    ap.add_argument("--styles", default="one,many,headslow")
    ap.add_argument("--head-copies", type=int, default=16)
    args = ap.parse_args()
    print("N style issue_med total_med issue_range")
    for n in (int(x) for x in args.ns.split(",") if x):
        for style in (x for x in args.styles.split(",") if x):
            issue, total, span = measure(n, style, args.head_copies, args.reps)
            print(f"{n:2d} {style:4s} {issue:9.0f} {total:9.0f} {span[0]}..{span[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
