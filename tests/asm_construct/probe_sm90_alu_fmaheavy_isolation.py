#!/usr/bin/env python3
"""H100 two-warp pure-stream timing and overlap sanity check.

Warps 0 and 4 run yield=0 streams at different PCs.  Report both per-warp
CS2R spans and the enclosing wall span.  The per-warp windows can be largely
sequential, so their reciprocal-rate sum is diagnostic only and MUST NOT be
interpreted as aggregate SMSP throughput without checking ``wall``.
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
    "hfma2_mma": "HFMA2.MMA RZ, R24, R25, 0f3f803f80",
    "ffma": "FFMA RZ, R24, R25, 0f3f800000",
    "ffma_z": "FFMA RZ, RZ, RZ, RZ",
    "imad_z": "IMAD RZ, RZ, RZ, RZ",
    "hfma2_z": "HFMA2 RZ, RZ, RZ, RZ",
    "iadd3_z": "IADD3 RZ, RZ, RZ, RZ",
    "dadd": "DADD {RZ,RZ}, {RZ,RZ}, {RZ,RZ}",
    "nop": "NOP",
}


def real_dest(op: str, i: int) -> str:
    if op.startswith("DADD"):
        d = 28 + 2 * (i % 4)
        return f"DADD {{R{d},R{d + 1}}}, {{RZ,RZ}}, {{RZ,RZ}}"
    d = 28 + (i % 9)
    head, rest = op.split(" ", 1)
    return f"{head} R{d}, " + rest.split(", ", 1)[1]


def source(op_a: str, op_b: str, n: int, warps: tuple[int, ...],
           reuse: bool = False, realdest: bool = False) -> str:
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
        op = OPS[(op_a, op_b)[i % 2]]
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;[7:7:{{}}:13:1]",
            f"    @!P0 BRA #label(skip{w});[7:7:{{}}:5:1]",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        ]
        # fe_pipe does not accept the operand-reuse batch_t field.
        sched = ("[7:7:{}:1:0:7]" if reuse and op != "NOP"
                 else "[7:7:{}:1:0]")
        for i in range(n):
            inst = real_dest(op, i) if realdest and op != "NOP" else op
            lines.append(f"    {inst};{sched}")
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


def measure(op_a: str, op_b: str, n: int, warps: tuple[int, ...],
            reps: int, reuse: bool = False,
            realdest: bool = False) -> tuple[tuple[float, ...], float]:
    mod = CudaModule(assemble(source(op_a, op_b, n, warps, reuse,
                                             realdest),
                              arch="sm90", check_deps=False))
    nthreads = (max(warps) + 1) * 32
    out = mod.devmem_alloc(nthreads * 16)
    spans: list[tuple[int, ...]] = []
    walls: list[int] = []
    try:
        for rep in range(reps + 1):
            mod.launch("iso", grid=(1,), block=(nthreads,), args=[out])
            mod.synchronize()
            if rep:
                raw = mod.device_read(out, nthreads * 16)
                times = [struct.unpack_from("<QQ", raw, w * 32 * 16)
                         for w in warps]
                spans.append(tuple((t1 - t0) & ((1 << 64) - 1)
                                   for t0, t1 in times))
                walls.append(max(t1 for _, t1 in times) -
                             min(t0 for t0, _ in times))
    finally:
        mod.devmem_free(out)
    return (tuple(statistics.median(s[i] for s in spans)
                  for i in range(len(warps))),
            statistics.median(walls))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pairs", default="iadd3:imad")
    p.add_argument("--n", type=int, default=512)
    p.add_argument("--reps", type=int, default=9)
    p.add_argument("--realdest", action="store_true",
                   help="rotating real destinations instead of RZ")
    p.add_argument("--reuse", action="store_true",
                   help="reuse-mask 7 on all stream ops (zero RF demand)")
    p.add_argument("--warps", default="0,4")
    p.add_argument("--diff", action="store_true",
                   help="place warps on different subcores (0,1)")
    ns = p.parse_args()
    warps = ((0, 1) if ns.diff else
             tuple(int(x) for x in ns.warps.split(",")))
    for pair in ns.pairs.split(","):
        a, b = pair.split(":")
        spans, wall = measure(a, b, ns.n, warps, ns.reps, ns.reuse,
                              ns.realdest)
        rates = [ns.n / x for x in spans]
        print(f"{a:6s} x {b:6s} warps={warps}: "
              + " ".join(f"{x / ns.n:6.3f}" for x in spans)
              + f"  sum_recip={sum(rates):5.3f}/cyc"
              + f" wall={wall / ns.n:6.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
