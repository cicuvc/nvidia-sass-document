#!/usr/bin/env python3
"""Estimate GB202 fixed-math admission credits from short bursts.

All target instructions are guarded by architecturally-false P6 and write RZ,
so the curve measures predicate-insensitive family admission rather than RF
collection or architectural writeback.  The ending CS2R does not explicitly
wait for target results.  A fast initial segment followed by the target-pipe
drain slope exposes effective queued/executing credits, not necessarily a
literal FIFO entry count.
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
    "nop": "NOP",
    "aluheavy": "@P6 IADD3 RZ, R24, R27, R28",
    "lop3": "@P6 LOP3.LUT RZ, R24, R27, R28, 0x96",
    "shf": "@P6 SHF.R.U32.HI RZ, R24, R27, R28",
    "alulite": "@P6 IADD RZ, PT, R24, R27",
    "mov": "@P6 MOV RZ, R24",
    "isetp": "@P6 ISETP.NE.AND P1, PT, R24, R27, PT",
    "alulite64": "@P6 MOV64IUR {RZ,RZ}, 0x12345678",
    "fmaheavy": "@P6 IMAD RZ, R24, R27, R28",
    "imul": "@P6 IMUL.U32 RZ, R24, R27",
    "fswzadd": "@P6 FSWZADD.NDV RZ, R24, R27, PPPPPPPP",
    "fmaheavy_hi": "@P6 IMAD.HI RZ, PT, R24, R27, {R28,R29}",
    "fmalite": "@P6 FFMA RZ, R24, R27, R28",
    "fadd": "@P6 FADD RZ, R24, R27",
    "fmul": "@P6 FMUL RZ, R24, R27",
    "packed": "@P6 HFMA2 RZ, R24, R27, R28",
    "hadd2": "@P6 HADD2 RZ, R24, R27",
    "hmul2": "@P6 HMUL2 RZ, R24, R27",
    "fp64": "@P6 DADD {RZ,RZ}, {R24,R25}, {R26,R27}",
}

ACTORS = {
    "one": (0,),
    "same2": (0, 4),
    "same4": (0, 4, 8, 12),
    "same8": (0, 4, 8, 12, 16, 20, 24, 28),
    "diff2": (0, 1),
    "diff4": (0, 1, 2, 3),
}

BARRIER_OPS = {
    "aluheavy": "@P6 IADD3 RZ, RZ, RZ, RZ",
    "lop3": "@P6 LOP3.LUT RZ, RZ, RZ, RZ, 0x96",
    "shf": "@P6 SHF.R.U32.HI RZ, RZ, RZ, RZ",
    "alulite": "@P6 IADD RZ, PT, RZ, RZ",
    "mov": "@P6 MOV RZ, RZ",
    "isetp": "@P6 ISETP.NE.AND P1, PT, RZ, RZ, PT",
    "fmaheavy": "@P6 IMAD RZ, RZ, RZ, RZ",
    "imul": "@P6 IMUL.U32 RZ, RZ, RZ",
    "fswzadd": "@P6 FSWZADD.NDV RZ, RZ, RZ, PPPPPPPP",
    "fmalite": "@P6 FFMA RZ, RZ, RZ, RZ",
    "fadd": "@P6 FADD RZ, RZ, RZ",
    "fmul": "@P6 FMUL RZ, RZ, RZ",
    "packed": "@P6 HFMA2 RZ, RZ, RZ, RZ",
    "hadd2": "@P6 HADD2 RZ, RZ, RZ",
    "hmul2": "@P6 HMUL2 RZ, RZ, RZ",
}

BARRIER_PLACEMENTS = {
    "one": ((0,), 1),
    "same2": ((0, 4), 1),
    "diff2": ((0, 1), 2),
}


def barrier_source(n: int, mode: str, placement: str, active: bool,
                   producer_delay: int = 0) -> tuple[str, int]:
    """Time producer progress using a clean-subcore barrier observer."""
    producers, observer = BARRIER_PLACEMENTS[placement]
    op = BARRIER_OPS[mode]
    if active:
        op = op.removeprefix("@P6 ")
    lines = [
        "#fn fixedbarrier(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    ISETP.F P6, RZ, RZ;[7:7:{}:13:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for warp in producers:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
            "[7:7:{}:13:1]",
            "    @P0 BRA #label(producer);[7:7:{}:5:1]",
        ]
    lines += [
        f"    ISETP.EQ.AND P0, PT, R5, 0x{observer:x}, PT;"
        "[7:7:{}:13:1]",
        "    @P0 BRA #label(observer);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(producer)",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(producer_delay)]
    lines += [f"    {op};[7:7:{{}}:1:0:7]" for _ in range(n)]
    lines += [
        "    BRA #label(join);[7:7:{}:5:1]",
        "#def_label(observer)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "#def_label(join)",
        f"    BAR.SYNC 1, 0x{(len(producers) + 1) * 32:x};"
        "[7:7:{}:5:1]",
        f"    ISETP.EQ.AND P0, PT, R5, 0x{observer:x}, PT;"
        "[7:7:{}:13:1]",
        "    @!P0 BRA #label(done);[7:7:{}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines), (max(*producers, observer) + 1) * 32


def source(n: int, mode: str, actors: tuple[int, ...], active: bool,
           fast: bool, prefix_hi: int, prefix_packed: int,
           prefix_active: bool, blocker_hi: int) -> str:
    op = OPS[mode]
    if active:
        op = op.removeprefix("@P6 ")
    sched = "[7:7:{}:1:0:7]" if fast else "[7:7:{}:1:1]"
    if fast and mode == "alulite64":
        sched = "[7:7:{}:1:0]"
    elif fast and mode == "fp64":
        sched = "[7:7:{}:1:0:3]"
    prefix_op = OPS["fmaheavy_hi"]
    if active or prefix_active:
        prefix_op = prefix_op.removeprefix("@P6 ")
    lines = [
        "#fn scalarburst(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R5, 0x10, {R2,R3};[7:7:{0,1}:5:1]",
        "    MOV32I R24, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3ff00000;[7:7:{}:5:1]",
        "    MOV32I R26, 0;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40003c00;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f003c00;[7:7:{}:5:1]",
        "    MOV32I R29, 0x3f003c00;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if blocker_hi:
        if actors != (0, 4):
            raise ValueError("--blocker-hi requires --actors same2")
        lines += [
            "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
            "    @P0 BRA #label(blocker);[7:7:{}:5:1]",
            "    ISETP.EQ.AND P0, PT, R5, 0x4, PT;[7:7:{}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:5:1]",
            "    BRA #label(done);[7:7:{}:5:1]",
            "#def_label(blocker)",
            "    NOP;[7:7:{}:8:1]",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        ]
        lines += [
            "    IMAD.HI RZ, PT, R24, R27, {R28,R29};" + sched
            for _ in range(blocker_hi)
        ]
        lines += [
            "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    BRA #label(store);[7:7:{}:5:1]",
        ]

    if actors == tuple(range(max(actors) + 1)):
        lines += ["    BRA #label(work);[7:7:{}:5:1]"]
    elif all(w % 4 == 0 for w in actors):
        lines += [
            "    LOP3.LUT R8, R5, 0x3, RZ, 0xc0;[7:7:{}:5:1]",
            "    ISETP.EQ.AND P0, PT, R8, RZ, PT;[7:7:{}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:5:1]",
            "    BRA #label(done);[7:7:{}:5:1]",
        ]
    else:
        for w in actors:
            lines += [
                f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;"
                "[7:7:{}:13:1]",
                "    @P0 BRA #label(work);[7:7:{}:5:1]",
            ]
        lines += ["    BRA #label(done);[7:7:{}:5:1]"]
    lines += [
        "#def_label(work)",
        "    NOP;[7:7:{}:8:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += [f"    {prefix_op};{sched}" for _ in range(prefix_hi)]
    packed_op = OPS["packed"]
    if active or prefix_active:
        packed_op = packed_op.removeprefix("@P6 ")
    lines += [f"    {packed_op};{sched}" for _ in range(prefix_packed)]
    lines += [f"    {op};{sched}" for _ in range(n)]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "#def_label(store)",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:0:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def parse_counts(text: str) -> list[int]:
    if "-" in text:
        lo, hi = (int(x) for x in text.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(x) for x in text.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=OPS, default="aluheavy")
    ap.add_argument("--actors", choices=ACTORS, default="one")
    ap.add_argument("--counts", default="0-32")
    ap.add_argument("--reps", type=int, default=11)
    ap.add_argument("--active", action="store_true",
                    help="execute targets instead of using all-off P6")
    ap.add_argument("--fast", action="store_true",
                    help="use yield=0 and reuse all three operands")
    ap.add_argument("--prefix-hi", type=int, default=0,
                    help="prepend this many IMAD.HI operations")
    ap.add_argument("--prefix-packed", type=int, default=0,
                    help="prepend this many HFMA2 operations")
    ap.add_argument("--prefix-active", action="store_true",
                    help="execute prefixes even when burst targets are @P6")
    ap.add_argument("--blocker-hi", type=int, default=0,
                    help="on warp 0, execute IMAD.HI while warp 4 runs burst")
    ap.add_argument("--barrier-method", action="store_true",
                    help="time producer progress from a clean-subcore observer")
    ap.add_argument("--producer-delay", type=int, default=0,
                    help="stall-8 NOPs before a barrier-method producer burst")
    ns = ap.parse_args()
    counts = parse_counts(ns.counts)
    if (not counts or min(counts) < 0 or max(counts) > 100 or
            ns.reps <= 0 or not 0 <= ns.prefix_hi <= 32 or
            not 0 <= ns.prefix_packed <= 32 or
            not 0 <= ns.blocker_hi <= 100 or
            not 0 <= ns.producer_delay <= 32):
        ap.error("counts must be in 0..100, prefix in 0..32, blocker in "
                 "0..100, producer-delay in 0..32, reps positive")
    if ns.barrier_method:
        if ns.mode not in BARRIER_OPS or ns.actors not in BARRIER_PLACEMENTS:
            ap.error("barrier method supports fixed scalar modes and "
                     "one/same2/diff2 placements")
        if ns.prefix_hi or ns.prefix_packed or ns.blocker_hi:
            ap.error("barrier method does not support prefix/blocker options")
    actors = ACTORS[ns.actors]
    report_actors = (0,) if ns.barrier_method else actors

    print(f"mode={ns.mode} actors={ns.actors} active={ns.active} "
          f"fast={ns.fast} prefix_hi={ns.prefix_hi} "
          f"prefix_packed={ns.prefix_packed} "
          f"prefix_active={ns.prefix_active} "
          f"blocker_hi={ns.blocker_hi} "
          f"barrier_method={ns.barrier_method} "
          f"producer_delay={ns.producer_delay}")
    actor_cols = "" if len(report_actors) == 1 else " " + " ".join(
        f"w{w}_median" for w in report_actors)
    print("N span_median min max delta" + actor_cols)
    previous = None
    for n in counts:
        if ns.barrier_method:
            src, block_size = barrier_source(
                n, ns.mode, ns.actors, ns.active, ns.producer_delay)
            function_name = "fixedbarrier"
            out_size = 16
            result_actors = (0,)
        else:
            src = source(n, ns.mode, actors, ns.active, ns.fast,
                         ns.prefix_hi, ns.prefix_packed, ns.prefix_active,
                         ns.blocker_hi)
            block_size = (max(actors) + 1) * 32
            function_name = "scalarburst"
            out_size = (max(actors) + 1) * 16
            result_actors = actors
        mod = CudaModule(assemble(src, check_deps=True))
        out = mod.devmem_alloc(out_size)
        vals = []
        actor_vals = [[] for _ in report_actors]
        try:
            for _ in range(ns.reps + 1):
                mod.launch(function_name, grid=(1,), block=(block_size,),
                           args=[out])
                mod.synchronize()
                raw = mod.device_read(out, out_size)
                times = [struct.unpack_from("<QQ", raw, w * 16)
                         for w in result_actors]
                vals.append(max(t1 for _, t1 in times) -
                            min(t0 for t0, _ in times))
                for dst, (t0, t1) in zip(actor_vals, times):
                    dst.append(t1 - t0)
        finally:
            mod.devmem_free(out)
        kept = vals[1:]
        med = statistics.median(kept)
        delta = "-" if previous is None else f"{med - previous:g}"
        actor_text = "" if len(report_actors) == 1 else " " + " ".join(
            f"{statistics.median(v[1:]):9g}" for v in actor_vals)
        print(f"{n:2d} {med:6g} {min(kept):3d} {max(kept):3d} {delta}" +
              actor_text)
        previous = med
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
