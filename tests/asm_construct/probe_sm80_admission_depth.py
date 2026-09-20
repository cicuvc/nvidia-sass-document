#!/usr/bin/env python3
"""Estimate GA100 fixed-math admission credits from short bursts.

sm_80 port of probe_scalar_admission_depth.py (GB202).  All target
instructions are guarded by architecturally-false P6 and write RZ, so the
curve measures predicate-insensitive family admission rather than RF
collection or architectural writeback.  The ending CS2R does not explicitly
wait for target results.  A fast initial segment followed by the target-pipe
drain slope exposes effective queued/executing credits, not necessarily a
literal FIFO entry count.

Uses the sm70/sm80 direct-parameter address skeleton (kernel params at
c[0x0][0x160]) rather than the scoreboard-sensitive sm90/sm120 harness.
"""

from __future__ import annotations

import argparse
import os
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402

# Raw const-bank param address per arch: sm70/75/80/89 are dword-indexed
# (0x160 dwords = 0x580 bytes), sm90+ are byte-indexed (param base 0x210).
ARCH = os.environ.get("PROBE_ARCH") or os.environ.get("ASSEMBLER_ARCH", "sm80")
DIALECT_PARAM = ARCH.startswith("sm9") or ARCH.startswith("sm1")


OPS = {
    "nop": "NOP",
    "aluheavy": "@P6 IADD3 RZ, R24, R27, R28",
    "alulite": "@P6 IADD RZ, PT, R24, R27",
    "fmaheavy": "@P6 IMAD RZ, R24, R27, R28",
    "fmaheavy_hi": "@P6 IMAD.HI RZ, PT, R24, R27, {R28,R29}",
    "fmalite": "@P6 FFMA RZ, R24, R27, R28",
    "packed": "@P6 HFMA2 RZ, R24, R27, R28",
    "packed_mma": "@P6 HFMA2.MMA RZ, R24, R27, R28",
    "fp64": "@P6 DADD {RZ,RZ}, {R24,R25}, {R26,R27}",
    # MIO-side families (sm90 dialects; harmless on sm80 too).
    "lsu": "@P6 STS [RZ], R24",
    "xu": "@P6 MUFU.RCP R30, R24",
    "shfl": "@P6 SHFL.BFLY PT, RZ, RZ, 0x1, 0x1f",
    # CBU forms need per-instance labels; emitted specially below.
    "cbu_bra": "",
    "cbu_bssy": "",
    # Interleaved pairs for queue-sharing discrimination (emitted below).
    "mix_int_packed": "",
    "mix_int_fp64": "",
    "mix_packed_fp64": "",
    "mix_mma_packed": "",
    "mix_mma_fp64": "",
}

MIX = {
    "mix_int_packed": ("aluheavy", "packed"),
    "mix_int_fp64": ("aluheavy", "fp64"),
    "mix_packed_fp64": ("packed", "fp64"),
    "mix_mma_packed": ("packed_mma", "packed"),
    "mix_mma_fp64": ("packed_mma", "fp64"),
}

ACTORS = {
    "one": (0,),
    "same2": (0, 4),
    "same4": (0, 4, 8, 12),
    "same8": (0, 4, 8, 12, 16, 20, 24, 28),
    "diff2": (0, 1),
    "diff4": (0, 1, 2, 3),
}


def source(n: int, mode: str, actors: tuple[int, ...], active: bool,
           fast: bool, prefix_hi: int, prefix_packed: int,
           prefix_active: bool, blocker_hi: int,
           blocker_op: str = "hi") -> str:
    op = OPS[mode]
    if active:
        op = op.removeprefix("@P6 ")
    sched = "[7:7:{}:1:0:7]" if fast else "[7:7:{}:1:1]"
    if mode == "nop":
        sched = "[7:7:{}:1:0]" if fast else "[7:7:{}:1:1]"
    elif fast and mode == "fp64":
        sched = "[7:7:{}:1:0:3]"
    prefix_op = OPS["fmaheavy_hi"]
    if active or prefix_active:
        prefix_op = prefix_op.removeprefix("@P6 ")
    lines = [
        "#fn sm80_burst(out<8>) {",
        "    #pragma MAXREG_COUNT(40)",
        "    S2R R0, SR_TID.X;[7:7:{}:6:0]",
        # SR_TID.X needs more than one instruction gap on GA100 before its
        # value is readable (a consumer at stall 6 reads stale zero).  Use
        # the probe-verified tid-based address first, derive the warp id
        # only after enough padding.
        "    MOV R6, 0x10;[7:7:{}:6:0]",
            # sm90: inline c[] IMAD.WIDE addend is unverified; use the
        # dialect LDC path (param base handled by the assembler).  The LDC
        # needs stall>=2 for its SB claim to be visible (archutil rule).
        ("    LDC.64 {R2,R3}, #param(out);[1:7:{}:2:0]" if DIALECT_PARAM else
         "    NOP;[7:7:{}:6:0]"),
        ("    IMAD.WIDE.U32 {R2,R3}, R0, R6, {R2,R3};[7:7:{1,4}:6:0]" if DIALECT_PARAM else
         "    IMAD.WIDE.U32 {R2,R3}, R0, R6, c[0x0][0x160];[7:7:{}:6:0]"),
        "    NOP;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:6:0]",
        "    SHR R5, R0, 0x5;[7:7:{}:6:0]",
        "    MOV R24, 0x3f803c00;[7:7:{}:6:0]",
        "    MOV R25, 0x3ff00000;[7:7:{}:6:0]",
        "    MOV R26, RZ;[7:7:{}:6:0]",
        "    MOV R27, 0x40003c00;[7:7:{}:6:0]",
        "    MOV R28, 0x3f003c00;[7:7:{}:6:0]",
        "    MOV R29, 0x3f003c00;[7:7:{}:6:0]",
        # R24 != 0, so P6 is architecturally false for the whole kernel.
        "    ISETP.EQ.AND P6, PT, R24, RZ, PT;[7:7:{}:13:1]",
        # All warps arrive before the timed region; non-actors then exit.
        "    BAR.SYNC 0;[7:7:{}:6:0]",
    ]
    if blocker_hi:
        if actors != (0, 4):
            raise ValueError("--blocker-hi requires --actors same2")
        lines += [
            "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
            "    @P0 BRA #label(blocker);[7:7:{}:6:0]",
            "    ISETP.EQ.AND P0, PT, R5, 0x4, PT;[7:7:{}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:6:0]",
            "    BRA #label(done);[7:7:{}:6:0]",
            "#def_label(blocker)",
            "    NOP;[7:7:{}:8:1]",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:6:0]",
        ]
        bop = {"hi": "IMAD.HI RZ, PT, R24, R27, {R28,R29}",
               "wide": "IMAD.WIDE.U32 {R28,R29}, R24, R27, RZ",
               "alu": "IADD3 RZ, R24, R27, R28",
               "mufu": "MUFU.RCP R30, R24",
               "nop": "NOP"}[blocker_op]
        lines += [f"    {bop};{sched}" for _ in range(blocker_hi)]
        lines += [
            "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:6:0]",
            "    BRA #label(store);[7:7:{}:6:0]",
        ]

    for w in actors:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;"
            "[7:7:{}:13:1]",
            "    @P0 BRA #label(work);[7:7:{}:6:0]",
        ]
    lines += ["    BRA #label(done);[7:7:{}:6:0]"]
    lines += [
        "#def_label(work)",
        "    NOP;[7:7:{}:8:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:6:0]",
    ]
    lines += [f"    {prefix_op};{sched}" for _ in range(prefix_hi)]
    packed_op = OPS["packed"]
    if active or prefix_active:
        packed_op = packed_op.removeprefix("@P6 ")
    lines += [f"    {packed_op};{sched}" for _ in range(prefix_packed)]
    if mode == "cbu_bra":
        for i in range(n):
            lines.append(f"    @P6 BRA #label(cbb{i});{sched}")
            lines.append(f"#def_label(cbb{i})")
    elif mode == "cbu_bssy":
        for i in range(n):
            lines.append(f"    @P6 BSSY B0, #label(cbs{i});{sched}")
            lines.append(f"    @P6 BSYNC B0;{sched}")
            lines.append(f"#def_label(cbs{i})")
    elif mode in MIX:
        a, b = (OPS[k] for k in MIX[mode])
        if active:
            a, b = a.removeprefix("@P6 "), b.removeprefix("@P6 ")
        for i in range(n):
            lines.append(f"    {a if i % 2 == 0 else b};{sched}")
    else:
        lines += [f"    {op};{sched}" for _ in range(n)]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:6:0]",
        "#def_label(store)",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[0:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[0:1:{}:8:0]",
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
    ap.add_argument("--blocker-op", choices=("hi", "wide", "alu", "mufu",
                                             "nop"), default="hi")
    ap.add_argument("--blocker-hi", type=int, default=0,
                    help="on warp 0, execute IMAD.HI while warp 4 runs burst")
    ns = ap.parse_args()
    counts = parse_counts(ns.counts)
    if (not counts or min(counts) < 0 or max(counts) > 100 or
            ns.reps <= 0 or not 0 <= ns.prefix_hi <= 32 or
            not 0 <= ns.prefix_packed <= 32 or
            not 0 <= ns.blocker_hi <= 100):
        ap.error("counts must be in 0..100, prefix in 0..32, blocker in "
                 "0..100, reps positive")
    actors = ACTORS[ns.actors]

    print(f"mode={ns.mode} actors={ns.actors} active={ns.active} "
          f"fast={ns.fast} prefix_hi={ns.prefix_hi} "
          f"prefix_packed={ns.prefix_packed} "
          f"prefix_active={ns.prefix_active} "
          f"blocker_hi={ns.blocker_hi}")
    actor_cols = "" if len(actors) == 1 else " " + " ".join(
        f"w{w}_median" for w in actors)
    print("N span_median min max delta" + actor_cols)
    previous = None
    for n in counts:
        mod = CudaModule(assemble(
            source(n, ns.mode, actors, ns.active, ns.fast, ns.prefix_hi,
                   ns.prefix_packed, ns.prefix_active, ns.blocker_hi, ns.blocker_op),
            arch=ARCH, check_deps=False))
        nthreads = (max(actors) + 1) * 32
        out_size = nthreads * 16
        out = mod.devmem_alloc(out_size)
        vals = []
        actor_vals = [[] for _ in actors]
        try:
            for _ in range(ns.reps + 1):
                mod.launch("sm80_burst", grid=(1,),
                           block=(nthreads,), args=[out])
                mod.synchronize()
                raw = mod.device_read(out, out_size)
                # lane 0's slot of each actor warp (tid = warp * 32)
                times = [struct.unpack_from("<QQ", raw, w * 32 * 16)
                         for w in actors]
                vals.append(max(t1 for _, t1 in times) -
                            min(t0 for t0, _ in times))
                for dst, (t0, t1) in zip(actor_vals, times):
                    dst.append(t1 - t0)
        finally:
            mod.devmem_free(out)
        kept = vals[1:]
        med = statistics.median(kept)
        delta = "-" if previous is None else f"{med - previous:g}"
        actor_text = "" if len(actors) == 1 else " " + " ".join(
            f"{statistics.median(v[1:]):9g}" for v in actor_vals)
        print(f"{n:2d} {med:6g} {min(kept):3d} {max(kept):3d} {delta}" +
              actor_text, flush=True)
        previous = med
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
