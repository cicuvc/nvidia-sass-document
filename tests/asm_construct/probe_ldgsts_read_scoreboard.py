#!/usr/bin/env python3
"""Measure LDGSTS read-scoreboard release versus copy completion."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402


def source(prefix: int, operand: str, size: int) -> str:
    shift = {4: 2, 8: 3, 16: 4}[size]
    flood = [
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}+0x{i * 0x1000:x}], "
        "{R32,R33,R34,R35};[7:7:{3}:1:1]"
        for i in range(prefix)
    ]
    overwrite = (
        "    IADD3 R20, R20, 0x100, RZ;[7:7:{2}:1:1]"
        if operand == "gaddr" else
        "    IADD3 R30, R30, 0x400, RZ;[7:7:{2}:1:1]"
    )
    return "\n".join([
        "#fn readrelease(out<8>, target<8>, flood<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(0x2000)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(target);[1:7:{}:1:0]",
        "    LDC.64 {R8,R9}, #param(flood);[3:7:{}:1:0]",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[4:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[5:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R4, 0x20, {R2,R3};[7:7:{0,5}:5:1]",
        f"    IMAD.WIDE.U32 {{R20,R21}}, R4, 0x{size:x}, {{R6,R7}};"
        "[7:7:{1,5}:5:1]",
        f"    SHF.L.U32 R30, R4, 0x{shift:x}, RZ;[7:7:{{5}}:5:1]",
        "    IADD3 R30, R30, 0x1000, RZ;[7:7:{}:5:1]",
        "    MOV32I R32, 0xaaaaaaaa;[7:7:{}:5:1]",
        "    MOV32I R33, 0xbbbbbbbb;[7:7:{}:5:1]",
        "    MOV32I R34, 0xcccccccc;[7:7:{}:5:1]",
        "    MOV32I R35, 0xdddddddd;[7:7:{}:5:1]",
        "    STS [R30], RZ;[7:7:{}:1:1]",
        "    STS [R30+0x400], RZ;[7:7:{}:1:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        *flood,
        f"    LDGSTS.E.{size * 8} [R30], desc[{{UR4,UR5}}][{{R20,R21}}];"
        "[7:2:{4}:1:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        overwrite,
        "    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    LDGDEPBAR;[0:7:{}:1:0]",
        "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    SHF.L.U32 R31, R4, 0x{shift:x}, RZ;[7:7:{{}}:5:1]",
        "    IADD3 R31, R31, 0x1000, RZ;[7:7:{}:5:1]",
        "    LDS R40, [R31];[1:7:{}:8:1]",
        "    LDS R41, [R31+0x400];[2:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R22,R23};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x8], {R24,R25};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x10], {R26,R27};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x18], {R40,R41};[7:7:{1,2}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def measure(prefix: int, operand: str, size: int,
            reps: int) -> tuple[float, float, int]:
    mod = CudaModule(assemble(source(prefix, operand, size), arch="sm120",
                              check_deps=True))
    out = mod.devmem_alloc(32 * 32)
    target = mod.devmem_alloc(reps * 0x1000)
    flood_mem = mod.devmem_alloc(max(0x1000, prefix * 0x1000 + 512))
    mod.devmem_set(target, 0x11223344, reps * 0x1000 // 4)
    waits, totals, bad = [], [], 0
    try:
        for rep in range(reps):
            mod.launch("readrelease", grid=(1,), block=(32,),
                       args=[out, target + rep * 0x1000, flood_mem],
                       shared_mem=0x2000)
            mod.synchronize()
            raw = mod.device_read(out, 32 * 32)
            for lane in range(32):
                t0, t1, t2, old, new = struct.unpack_from("<QQQII", raw, lane * 32)
                if lane == 0:
                    waits.append(t1 - t0)
                    totals.append(t2 - t0)
                bad += (old != 0x11223344 or new != 0)
    finally:
        mod.devmem_free(flood_mem)
        mod.devmem_free(target)
        mod.devmem_free(out)
    return statistics.median(waits), statistics.median(totals), bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefixes", default="0,1,2,3,4,6,8,12,16")
    ap.add_argument("--reps", type=int, default=21)
    ap.add_argument("--sizes", default="4,8,16")
    args = ap.parse_args()
    print("size operand prefix rd_release copy_complete bad_lanes")
    for size in (int(x) for x in args.sizes.split(",") if x):
        for operand in ("gaddr", "saddr"):
            for prefix in (int(x) for x in args.prefixes.split(",") if x):
                rd, done, bad = measure(prefix, operand, size, args.reps)
                print(f"{size:4d} {operand:5s} {prefix:6d} {rd:10.0f} "
                      f"{done:13.0f} {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
