#!/usr/bin/env python3
"""Measure sm_120 ALU-Lite result visibility, not table-only latency.

Fixed-latency instructions are not protected by an automatic RAW interlock.
Each instance therefore settles a poison value, issues one producer, and lets
a consumer observe the destination after a controlled issue gap.  A stale /
fresh boundary is the hardware-visible producer->consumer latency.

The probe intentionally tests both fine (stall-1 NOPs) and coarse (few NOPs
carrying large stalls) gaps.  Predicate paths can have alignment-dependent
forwarding windows, so a single filler shape is not a safe simulator rule.
"""

from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402
from archutil import adapt_source  # noqa: E402


POISON = 0x40000000                 # 2.0f
FRESH = 0x3F800000                  # 1.0f
STALE_MARK = 0x5AA50000
FRESH_MARK = 0x5AA50001
GAPS = list(range(1, 17)) + [20, 24, 30]


@dataclass(frozen=True)
class GprProducer:
    setup: tuple[str, ...]
    inst: str


GPR_PRODUCERS = {
    "FMNMX": GprProducer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x40000000"),
        "FMNMX R40, R24, R27, PT"),
    "FSEL": GprProducer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x40000000"),
        "FSEL R40, R24, R27, PT"),
    "FSET": GprProducer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x40000000"),
        "FSET.BF.LT.AND R40, R24, R27, PT"),
    "IADD": GprProducer(
        ("MOV32I R24, 0x3f7fffff", "MOV32I R27, 0x1"),
        "IADD R40, PT, R24, R27"),
    "IADD32I": GprProducer(
        ("MOV32I R24, 0x3f7fffff",),
        "IADD32I R40, PT, R24, 0x1"),
    "IMNMX": GprProducer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x40000000"),
        "IMNMX.U32 R40, R24, R27, PT"),
    "MOV": GprProducer(
        ("MOV32I R24, 0x3f800000",),
        "MOV R40, R24"),
    "SEL": GprProducer(
        ("MOV32I R24, 0x3f800000", "MOV32I R27, 0x40000000"),
        "SEL R40, R24, R27, PT"),
}


GPR_CONSUMERS = {
    # Preserve the bits on all paths.  FADD is safe because both possible
    # values are normal FP32 numbers.
    "alulite": "MOV R50, R40",
    "aluheavy": "IADD3 R50, R40, RZ, RZ",
    "fmalite": "FADD R50, R40, RZ",
    "fp16": "HADD2 R50, R40, RZ",
}


PRED_PRODUCERS = {
    "FSETP": GprProducer(
        ("MOV32I R24, 0x1", "MOV32I R27, 0x2"),
        "FSETP.LT.AND P0, P1, R24, R27, PT"),
    "ISETP": GprProducer(
        ("MOV32I R24, 0x1", "MOV32I R27, 0x2"),
        "ISETP.LT.AND P0, PT, R24, R27, PT"),
    "IADD.PU": GprProducer(
        ("MOV32I R24, 0xffffffff", "MOV32I R27, 0x1"),
        "IADD R40, P0, R24, R27"),
    "IADD32I.PU": GprProducer(
        ("MOV32I R24, 0xffffffff",),
        "IADD32I R40, P0, R24, 0x1"),
}


def filler(gap: int, coarse: bool) -> list[str]:
    """Producer has stall=1; add gap-1 cycles before the consumer."""
    rem = gap - 1
    out = []
    while rem:
        n = min(15, rem) if coarse else 1
        out.append(f"    NOP;[7:7:{{}}:{n}:1]")
        rem -= n
    return out


def prologue(name: str) -> list[str]:
    return [
        f"#fn {name}(out<8>) {{",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[2:7:{}:1:0]",
        "    MOV32I R10, 0;[7:7:{1,2}:8:1]",
    ]


def gpr_source(prod_name: str, consumer: str, coarse: bool) -> str:
    prod = GPR_PRODUCERS[prod_name]
    lines = prologue("lat")
    for i, gap in enumerate(GAPS):
        for inst in prod.setup:
            lines.append(f"    {inst};[7:7:{{}}:8:1]")
        lines += [
            f"    MOV32I R40, 0x{POISON:08x};[7:7:{{}}:15:1]",
            "    NOP;[7:7:{}:15:1]",
            f"    {prod.inst};[7:7:{{}}:1:1]",
        ]
        lines += filler(gap, coarse)
        lines += [
            f"    {GPR_CONSUMERS[consumer]};[3:7:{{}}:8:1]",
            "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R51;[0:7:{{}}:1:0]",
        ]
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def pred_source(prod_name: str, consumer: str, coarse: bool) -> str:
    prod = PRED_PRODUCERS[prod_name]
    lines = prologue("plat")
    for i, gap in enumerate(GAPS):
        # P0 poison=false, then settle well beyond the predicate latency.
        lines += [
            "    MOV32I R30, 0x1;[7:7:{}:8:1]",
            "    MOV32I R32, 0x2;[7:7:{}:8:1]",
        ]
        for inst in prod.setup:
            lines.append(f"    {inst};[7:7:{{}}:8:1]")
        lines += [
            f"    MOV32I R50, 0x{STALE_MARK:08x};[7:7:{{}}:8:1]",
            "    ISETP.F P0, RZ, RZ;[7:7:{}:15:1]",
            "    NOP;[7:7:{}:15:1]",
            f"    {prod.inst};[7:7:{{}}:1:1]",
        ]
        lines += filler(gap, coarse)
        off = 4 * i
        if consumer == "selector":
            # P0=true selects R30 on the tested encoding; false selects R32.
            lines += [
                "    SEL R50, R30, R32, P0;[3:7:{}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
                f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R51;[0:7:{{}}:1:0]",
            ]
        elif consumer == "guard":
            lines += [
                f"    @P0 MOV32I R50, 0x{FRESH_MARK:08x};[3:7:{{}}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
                f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R51;[0:7:{{}}:1:0]",
            ]
        elif consumer == "branch":
            true_label, done_label = f"true{i}", f"done{i}"
            lines += [
                f"    @P0 BRA #label({true_label});[7:7:{{}}:5:1]",
                f"    MOV32I R50, 0x{STALE_MARK:08x};[7:7:{{}}:5:1]",
                f"    BRA #label({done_label});[7:7:{{}}:5:1]",
                f"    #def_label({true_label})",
                f"    MOV32I R50, 0x{FRESH_MARK:08x};[7:7:{{}}:5:1]",
                f"    #def_label({done_label})",
                f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R50;[0:7:{{}}:1:0]",
            ]
        elif consumer == "p2r":
            lines += [
                "    P2R R50, PR, RZ, 0x1;[3:7:{}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
                f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R51;[0:7:{{}}:1:0]",
            ]
        else:
            raise ValueError(consumer)
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def run_source(source: str, fn: str, reps: int) -> list[tuple[int, ...]]:
    reset_context()
    mod = CudaModule(assemble(adapt_source(source), check_deps=False))
    out = mod.devmem_alloc(4096)
    values = []
    try:
        # First launch after a fresh context occasionally carries a distinct
        # clock/dispatch warm-up phase.  It must not enter latency classes.
        for rep in range(reps + 1):
            mod.device_write(out, bytes(4096))
            mod.launch(fn, grid=(1,), block=(1,), args=[out])
            mod.synchronize()
            got = struct.unpack(
                f"<{len(GAPS)}I", mod.device_read(out, 4 * len(GAPS)))
            if rep:
                values.append(got)
    finally:
        mod.devmem_free(out)
    return values


def states(reps: list[tuple[int, ...]], fresh: int, stale: int) -> str:
    out = []
    for i in range(len(GAPS)):
        vals = [r[i] for r in reps]
        if all(v == fresh for v in vals):
            out.append("F")
        elif all(v == stale for v in vals):
            out.append("S")
        else:
            out.append("?")
    return "".join(out)


def permanent_boundary(pattern: str) -> int | None:
    return next((GAPS[i] for i in range(len(GAPS))
                 if all(x == "F" for x in pattern[i:])), None)


def measure_pattern(builder, fn: str, reps: int, fresh: int, stale: int,
                    isolated: bool) -> str:
    """Optionally put every gap in its own module to remove PC-layout phase."""
    global GAPS
    if not isolated:
        return states(run_source(builder(), fn, reps), fresh, stale)
    saved = list(GAPS)
    out = []
    try:
        for gap in saved:
            GAPS = [gap]
            got = states(run_source(builder(), fn, reps), fresh, stale)
            out.append(got[0])
    finally:
        GAPS = saved
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--kind", choices=("all", "gpr", "pred"), default="all")
    ap.add_argument("--producer", action="append",
                    help="limit to producer mnemonic (repeatable)")
    ap.add_argument("--isolated", action="store_true",
                    help="compile one module per gap (slower; removes PC-layout phase)")
    ns = ap.parse_args()
    selected = {x.upper() for x in ns.producer} if ns.producer else None

    print("gaps: " + " ".join(f"{x:2}" for x in GAPS))
    ok = True
    if ns.kind in ("all", "gpr"):
        print("\nGPR result: S=poison(2.0f), F=fresh(1.0f)")
        for prod in GPR_PRODUCERS:
            if selected and prod not in selected:
                continue
            for cons in GPR_CONSUMERS:
                for coarse in (False, True):
                    pat = measure_pattern(
                        lambda: gpr_source(prod, cons, coarse), "lat", ns.reps,
                        FRESH, POISON, ns.isolated)
                    boundary = permanent_boundary(pat)
                    print(f"{prod:8} -> {cons:8} {'coarse' if coarse else 'fine':6} "
                          f"{pat} permanent={boundary}")
                    ok &= boundary is not None and pat[-1] == "F"

    if ns.kind in ("all", "pred"):
        print("\nPRED result: S=false, F=true")
        for prod in PRED_PRODUCERS:
            if selected and prod not in selected:
                continue
            for cons in ("selector", "p2r", "guard", "branch"):
                for coarse in (False, True):
                    if cons == "selector":
                        fresh, stale = 1, 2
                    elif cons == "p2r":
                        fresh, stale = 1, 0
                    else:
                        fresh, stale = FRESH_MARK, STALE_MARK
                    pat = measure_pattern(
                        lambda: pred_source(prod, cons, coarse), "plat", ns.reps,
                        fresh, stale, ns.isolated)
                    boundary = permanent_boundary(pat)
                    print(f"{prod:8} -> {cons:8} {'coarse' if coarse else 'fine':6} "
                          f"{pat} permanent={boundary}")
                    ok &= boundary is not None and pat[-1] == "F"
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
