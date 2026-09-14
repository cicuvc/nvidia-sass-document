#!/usr/bin/env python3
"""Distinguish one full-warp RF read from two mask-aware half-warp slices.

Warp 0 and warp 4 share a GB202 subcore; warp 1 is the placement control.
Each active instruction is ``FADD RZ, R24, R26`` (two even-bank sources, no
architectural write).  The two streams use either equal or complementary
half-warp predicates.

If two independently addressed 64-byte RF read slices are selected/gated by
the execution mask, low16 and high16 streams can collect concurrently.  A
single full-width address service, ganged slices, or post-read predication
gives no complementary-mask advantage.
"""

from __future__ import annotations

import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.arch import current  # noqa: E402


LENGTHS = (128, 256, 512, 1024)
REPS = 7
GUARD = {
    "full": "", "low": "@P1", "high": "@!P1",
    "even": "@P2", "odd": "@!P2", "off": "@P6",
}


def stream(mask: str, n: int) -> list[str]:
    prefix = f"{GUARD[mask]} " if GUARD[mask] else ""
    return [f"    {prefix}FADD RZ, R24, R26;[7:7:{{}}:1:1]"
            for _ in range(n)]


def source(vmask: str, cmask: str, n: int, contender_warp: int) -> str:
    return "\n".join([
        "#fn rfslice(out<8>) {",
        "    #pragma MAXREG_COUNT(40)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    S2R R8, SR_LANEID;[3:7:{}:5:1]",
        "    SHR.U32 R5, R4, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        "    ISETP.LT.U32.AND P1, PT, R8, 0x10, PT;[7:7:{3}:13:1]",
        "    LOP3.LUT R9, R8, 0x1, RZ, 0xc0;[7:7:{3}:5:1]",
        "    ISETP.EQ.U32.AND P2, PT, R9, RZ, PT;[7:7:{}:13:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R26, 0x40000000;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.U32.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        f"    ISETP.EQ.U32.AND P0, PT, R5, 0x{contender_warp:x}, PT;[7:7:{{}}:13:1]",
        "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *stream(vmask, n),
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        *stream(cmask, n * 4),
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R30,R31};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R32,R33};[7:1:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def slope(points: list[tuple[int, float]]) -> float:
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    return sum((x-xm)*(y-ym) for x, y in points) / sum(
        (x-xm)**2 for x, _ in points)


def measure(vmask: str, cmask: str, warp: int) -> float:
    points = []
    for n in LENGTHS:
        mod = CudaModule(assemble(source(vmask, cmask, n, warp),
                                  check_deps=True))
        out = mod.devmem_alloc(256 * 16)
        try:
            mod.launch("rfslice", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            vals = []
            for _ in range(REPS):
                mod.launch("rfslice", grid=(1,), block=(256,), args=[out])
                mod.synchronize()
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1-t0) & ((1 << 64)-1))
            points.append((n, float(min(vals))))
        finally:
            mod.devmem_free(out)
    return slope(points)


def main() -> int:
    cases = [
        ("same full/full", "full", "full", 4),
        ("same low/low", "low", "low", 4),
        ("same low/high", "low", "high", 4),
        ("same high/low", "high", "low", 4),
        ("same even/even", "even", "even", 4),
        ("same even/odd", "even", "odd", 4),
        ("same low/off", "low", "off", 4),
        ("diff low/low", "low", "low", 1),
        ("diff low/high", "low", "high", 1),
    ]
    print(f"RF lane-slice overlap probe ({current().name})")
    for label, vm, cm, warp in cases:
        print(f"{label:18s} {measure(vm, cm, warp):.4f} victim clocks/inst",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
