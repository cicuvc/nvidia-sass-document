#!/usr/bin/env python3
"""H100 ALU vs FMA-Heavy isolation: two warps, one subcore, pure streams.

Warps 0 and 4 (same subcore) run independent pure streams of N ops with
yield=0 brackets after a BAR.SYNC; each warp records its own CS2R span.
If ALU and FMA Heavy are separate 0.5/cyc services, an IADD3 x IMAD pair
sustains 0.5 + 0.5 = 1.0/cyc combined (exactly the scheduler issue
ceiling) with no interference, while same-family pairs halve to 0.25
each.  IADD3 x FFMA probes the issue-ceiling case (0.5 + 1.0 service
demand exceeds 1.0/cyc).
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402

OPS = {
    "iadd3": "IADD3 RZ, R24, R25, RZ",
    "imad": "IMAD RZ, R24, R25, RZ",
    "hfma2": "HFMA2 RZ, R24, R25, 0f3f803f80",
    "ffma": "FFMA RZ, R24, R25, 0f3f800000",
    "dadd": "DADD {RZ,RZ}, {RZ,RZ}, {RZ,RZ}",
    "nop": "NOP",
}


def source(op_a: str, op_b: str, n: int, warps: tuple[int, int]) -> str:
    lines = [
        "#fn iso(out<8>) {",
        "    #pragma MAXREG_COUNT(40)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:2:0]",
        "    S2R R0, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R0, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R2,R3}, R0, 0x10, {R2,R3};[7:7:{0,2}:5:1]",
        "    MOV R24, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV R25, 0x40003c00;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for i, w in enumerate(warps):
        op = OPS[(op_a, op_b)[i]]
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;[7:7:{{}}:13:1]",
            f"    @!P0 BRA #label(skip{w});[7:7:{{}}:5:1]",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        ]
        lines += [f"    {op};[7:7:{{}}:1:0]" for _ in range(n)]
        lines += [
            "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[0:1:{}:8:0]",
            "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[0:1:{}:8:0]",
            f"#def_label(skip{w})",
        ]
    lines += [
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(op_a: str, op_b: str, n: int, warps: tuple[int, int],
            reps: int) -> tuple[float, float]:
    mod = CudaModule(assemble(source(op_a, op_b, n, warps), arch="sm90",
                              check_deps=False))
    nthreads = (max(warps) + 1) * 32
    out = mod.devmem_alloc(nthreads * 16)
    spans: list[tuple[int, int]] = []
    try:
        for rep in range(reps + 1):
            mod.launch("iso", grid=(1,), block=(nthreads,), args=[out])
            mod.synchronize()
            if rep:
                raw = mod.device_read(out, nthreads * 16)
                pair = []
                for w in warps:
                    t0, t1 = struct.unpack_from("<QQ", raw, w * 32 * 16)
                    pair.append((t1 - t0) & ((1 << 64) - 1))
                spans.append(tuple(pair))
    finally:
        mod.devmem_free(out)
    return (statistics.median(s[0] for s in spans),
            statistics.median(s[1] for s in spans))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pairs", default="iadd3:imad")
    p.add_argument("--n", type=int, default=512)
    p.add_argument("--reps", type=int, default=9)
    p.add_argument("--diff", action="store_true",
                   help="place warps on different subcores (0,1)")
    ns = p.parse_args()
    warps = (0, 1) if ns.diff else (0, 4)
    for pair in ns.pairs.split(","):
        a, b = pair.split(":")
        sa, sb = measure(a, b, ns.n, warps, ns.reps)
        print(f"{a:6s} x {b:6s} {'diff' if ns.diff else 'same'}: "
              f"A={sa / ns.n:6.3f} cyc/op  B={sb / ns.n:6.3f} cyc/op  "
              f"agg={ns.n / sa + ns.n / sb:5.3f}/cyc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
