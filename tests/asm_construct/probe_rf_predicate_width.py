#!/usr/bin/env python3
"""Test whether partial-lane predicates reduce sm_120 RF collection cost.

The probe times yield-zero, single-warp streams whose source registers are
either all in the even bank or split across the even and odd banks.  The same
stream is run unpredicated, on the low/high half warp, with alternating low
and high half-warp predicates, and fully predicated off.

If a nominal per-bank ``2R`` is two independently useful 64-byte transfers,
an all-even two-source FADD may fall from two clocks to one when only 16 lanes
are active.  If the ports are ganged behind one register-row selection (or
predicate gating occurs after collection), partial predicates will not alter
the source-bank slope.
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
REPS = 5
SCHED = "[7:7:{}:1:0]"

OPS = {
    "fadd_ee": "FADD R{d}, R24, R26",
    "fadd_eo": "FADD R{d}, R24, R27",
    "ffma_eee": "FFMA R{d}, R24, R26, R28",
    "ffma_eeo": "FFMA R{d}, R24, R26, R27",
    "shfl_ee": "SHFL.IDX PT, R{d}, R24, R26, 0x1f",
    "shfl_eo": "SHFL.IDX PT, R{d}, R24, R27, 0x1f",
    "shfl_eee": "SHFL.IDX PT, R{d}, R24, R26, R28",
}

MODES = {
    "full": ("",),
    "lane0": ("@P1",),
    "low16": ("@P0",),
    "high16": ("@!P0",),
    "evenlanes": ("@P2",),
    "alternate16": ("@P0", "@!P0"),
    "off": ("@P6",),
}


def fit_slope(points: list[tuple[int, float]]) -> float:
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    return sum((x - xm) * (y - ym) for x, y in points) / sum(
        (x - xm) ** 2 for x, _ in points)


def source(op: str, mode: str, n: int) -> str:
    guards = MODES[mode]
    body = []
    for i in range(n):
        # Balance destination banks and avoid short WAW distances.
        d = 40 + i % 40
        guard = guards[i % len(guards)]
        prefix = f"{guard} " if guard else ""
        body.append(f"    {prefix}{OPS[op].format(d=d)};{SCHED}")
    return "\n".join([
        "#fn rfpred(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_LANEID;[2:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        "    ISETP.LT.U32.AND P0, PT, R4, 0x10, PT;[7:7:{2}:13:1]",
        "    ISETP.EQ.U32.AND P1, PT, R4, RZ, PT;[7:7:{2}:13:1]",
        "    LOP3.LUT R5, R4, 0x1, RZ, 0xc0;[7:7:{2}:5:1]",
        "    ISETP.EQ.U32.AND P2, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R26, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40400000;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f000000;[7:7:{}:5:1]",
        *[f"    MOV R{d}, RZ;[7:7:{{}}:5:1]" for d in range(40, 80)],
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *body,
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def main() -> int:
    print(f"RF partial-predicate width probe ({current().name})")
    print("single warp, stall=1/yield=0; values are fitted clocks/instruction")
    print(f"{'op':<11} " + " ".join(f"{m:>12}" for m in MODES))
    for op in OPS:
        slopes = {}
        for mode in MODES:
            points = []
            for n in LENGTHS:
                mod = CudaModule(assemble(source(op, mode, n), check_deps=True))
                out = mod.devmem_alloc(32 * 16)
                try:
                    mod.launch("rfpred", grid=(1,), block=(32,), args=[out])
                    mod.synchronize()
                    samples = []
                    for _ in range(REPS):
                        mod.launch("rfpred", grid=(1,), block=(32,), args=[out])
                        mod.synchronize()
                        t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                        samples.append((t1 - t0) & ((1 << 64) - 1))
                    points.append((n, float(min(samples))))
                finally:
                    mod.devmem_free(out)
            slopes[mode] = fit_slope(points)
        print(f"{op:<11} " + " ".join(f"{slopes[m]:12.4f}" for m in MODES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
