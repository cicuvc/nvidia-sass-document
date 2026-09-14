#!/usr/bin/env python3
"""Scale one MIO-class stream across same/different GB202 subcores.

Actor sets use the established ``warp_id % 4`` subcore mapping.  Besides the
balanced one/same2/diff2/diff4/all8 sets, skewed and two-subcore sets expose
whether arbitration is per warp or per subcore queue.  Per-warp clock
intervals expose fairness; the aggregate rate uses the common-SM interval
from the earliest actor start to the latest actor end.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


ACTORS = {
    "one": (0,),
    "same2": (0, 4),
    "diff2": (0, 1),
    "diff4": (0, 1, 2, 3),
    "skew5": (0, 1, 2, 3, 4),
    "skew6": (0, 1, 2, 3, 4, 5),
    "pair01x2": (0, 4, 1, 5),
    "pair02x2": (0, 4, 2, 6),
    "pair03x2": (0, 4, 3, 7),
    "all8": tuple(range(8)),
}
OPS = ("nop", "iadd3", "bmov", "nanosleep", "mufu", "shfl", "lds")


def instruction(op: str, i: int) -> str:
    rd = 40 + i % 40
    if op == "nop":
        return "NOP"
    if op == "iadd3":
        return f"IADD3 R{rd}, R24, RZ, RZ"
    if op == "nanosleep":
        return "NANOSLEEP 0x0"
    if op == "bmov":
        return f"BMOV.32 R{rd}, MACTIVE"
    if op == "mufu":
        return f"MUFU.RCP R{rd}, R24"
    if op == "shfl":
        return f"SHFL.BFLY PT, R{rd}, R24, 0x1, 0x1f"
    if op == "lds":
        return f"LDS R{rd}, [RZ]"
    raise ValueError(op)


def source(op: str, actors: tuple[int, ...], n: int, pred_off: bool) -> str:
    lines = [
        "#fn mioscale(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(1024)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for w in actors:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;[7:7:{{}}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:5:1]",
        ]
    lines += ["    BRA #label(done);[7:7:{}:5:1]", "#def_label(work)",
              "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]"]
    guard = "@P6 " if pred_off else ""
    lines += [f"    {guard}{instruction(op, i)};[7:7:{{}}:1:1]"
              for i in range(n)]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R22,R23};[7:1:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--op", choices=OPS, default="shfl")
    p.add_argument("--actors", choices=ACTORS, default="diff4")
    p.add_argument("--count", type=int, default=512)
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--pred-off", action="store_true")
    ns = p.parse_args()
    if min(ns.count, ns.reps) <= 0:
        p.error("count and reps must be positive")
    actors = ACTORS[ns.actors]
    mod = CudaModule(assemble(source(ns.op, actors, ns.count, ns.pred_off),
                              check_deps=True))
    out = mod.devmem_alloc(256 * 16)
    samples = {w: [] for w in actors}
    spans = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("mioscale", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            if rep:
                raw = mod.device_read(out, 256 * 16)
                starts = []
                ends = []
                for w in actors:
                    t0, t1 = struct.unpack_from("<QQ", raw, w * 32 * 16)
                    samples[w].append((t1 - t0) & ((1 << 64) - 1))
                    starts.append(t0)
                    ends.append(t1)
                spans.append(max(ends) - min(starts))
    finally:
        mod.devmem_free(out)
    med = {w: statistics.median(v) / ns.count for w, v in samples.items()}
    aggregate = len(actors) * ns.count / statistics.median(spans)
    print(f"{ns.op} actors={ns.actors} pred_off={ns.pred_off}: "
          f"cycles/op={med} span_inst/cycle={aggregate:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
