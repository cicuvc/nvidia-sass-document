#!/usr/bin/env python3
"""Consumer-specific RAW visibility for the sm_120 ALU-Heavy leaf."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_alulite_latency as base  # noqa: E402


FRESH = base.FRESH
POISON = base.POISON


@dataclass(frozen=True)
class Producer:
    setup: tuple[str, ...]
    inst: str
    fresh: int = FRESH
    poison: int = POISON


P = Producer


GPR_PRODUCERS = {
    "IADD3": P(("MOV32I R24, 0x3f800000", "MOV32I R27, 0", "MOV32I R28, 0"),
               "IADD3 R40, R24, R27, R28"),
    "ISCADD": P(("MOV32I R24, 0", "MOV32I R27, 0x3f800000"),
                "ISCADD R40, PT, R24, R27, 0x2"),
    "ISCADD32I": P(("MOV32I R24, 0x0fe00000",),
                   "ISCADD32I R40, PT, R24, 0x1, 0x2", 0x3F800001),
    "LEA": P(("MOV32I R24, 0", "MOV32I R27, 0x3f800000"),
             "LEA R40, R24, R27, 0x4"),
    "LOP": P(("MOV32I R24, 0x3f800000", "MOV32I R27, 0"),
             "LOP.XOR PT, R40, R24, R27"),
    "LOP32I": P(("MOV32I R24, 0x2db45678",),
                "LOP32I.XOR PT, R40, R24, 0x12345678"),
    "LOP3": P(("MOV32I R24, 0x3f800000", "MOV32I R27, 0", "MOV32I R28, 0"),
              "LOP3.LUT R40, R24, R27, R28, 0x96"),
    "PRMT": P(("MOV32I R24, 0x3f800000", "MOV32I R27, 0",
               "MOV32I R28, 0x3210"),
              "PRMT R40, R24, R28, R27"),
    "SHF": P(("MOV32I R24, 0", "MOV32I R27, 0",
              "MOV32I R28, 0x3f800000"),
             "SHF.R.U32.HI R40, R24, R27, R28"),
    "SHL": P(("MOV32I R24, 0x3f800000", "MOV32I R27, 0"),
             "SHL R40, R24, R27"),
    "SHR": P(("MOV32I R24, 0x3f800000", "MOV32I R27, 0"),
             "SHR.U32 R40, R24, R27"),
    "SGXT": P(("MOV32I R24, 0x3f800000",),
              "SGXT R40, R24, 0x1f"),
    "IABS": P(("MOV32I R24, 0x3f800000",), "IABS R40, R24"),
    "BMSK": P(("MOV32I R24, 0x17", "MOV32I R27, 0x7"),
              "BMSK R40, R24, R27"),
    "F2FP": P(("MOV32I R24, 0x3f800000", "MOV32I R27, 0x3f800000"),
              "F2FP.F16.F32.PACK_AB R40, R24, R27", 0x3C003C00),
    "F2IP": P(("MOV32I R24, 0x3f800000",),
              "F2IP.U8.F32 R40, RZ, R24, RZ", 0x1),
    "I2FP": P(("MOV32I R24, 0x1",),
              "I2FP.F32.S32 R40, R24"),
    "I2I": P(("MOV32I R24, 0xff",),
             "I2I.SAT.U8 R40, R24", 0xFF),
    "I2IP": P(("MOV32I R24, 0x1",),
              "I2IP.U8.S32 R40, RZ, R24, RZ", 0x1),
    "P2R": P(("PSETP.AND P0, PT, PT",),
             "P2R R40, PR, RZ, 0x1", 0x1),
    "HMNMX2": P(("MOV32I R24, 0x3c003c00", "MOV32I R27, 0x40004000"),
                "HMNMX2 R40, R24, R27, PT", 0x3C003C00),
    "HSET2": P(("MOV32I R24, 0x3c003c00", "MOV32I R27, 0x40004000"),
               "HSET2.LT.AND.BF R40, R24, R27, PT", 0x3C003C00),
}


PRED_PRODUCERS = {
    "IADD3.PU": P(("MOV32I R24, 0xffffffff", "MOV32I R27, 0x1",
                    "MOV32I R28, 0"),
                   "IADD3 R40, P0, PT, R24, R27, R28"),
    "PSETP": P((), "PSETP.AND P0, PT, PT"),
    "PLOP3": P((), "PLOP3.LUT P0, PT, PT, PT, PT, 0xff"),
    "R2P": P(("MOV32I R24, 0x1",), "R2P PR, R24, 0x1"),
    "HSETP2": P(("MOV32I R24, 0x3c003c00", "MOV32I R27, 0x40004000"),
                "HSETP2.LT.AND P0, P1, R24, R27, PT"),
}


def gpr_source(prod_name: str, consumer: str, coarse: bool) -> str:
    prod = GPR_PRODUCERS[prod_name]
    lines = base.prologue("hlat")
    for i, gap in enumerate(base.GAPS):
        for inst in prod.setup:
            lines.append(f"    {inst};[7:7:{{}}:8:1]")
        lines += [
            f"    MOV32I R40, 0x{prod.poison:08x};[7:7:{{}}:15:1]",
            "    NOP;[7:7:{}:15:1]",
            f"    {prod.inst};[7:7:{{}}:1:1]",
        ]
        lines += base.filler(gap, coarse)
        lines += [
            f"    {base.GPR_CONSUMERS[consumer]};[3:7:{{}}:8:1]",
            "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], R51;[0:7:{{}}:1:0]",
        ]
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def pred_source(prod_name: str, consumer: str, coarse: bool) -> str:
    prod = PRED_PRODUCERS[prod_name]
    lines = base.prologue("hplat")
    for i, gap in enumerate(base.GAPS):
        lines += [
            "    MOV32I R30, 0x1;[7:7:{}:8:1]",
            "    MOV32I R32, 0x2;[7:7:{}:8:1]",
        ]
        for inst in prod.setup:
            lines.append(f"    {inst};[7:7:{{}}:8:1]")
        lines += [
            f"    MOV32I R50, 0x{base.STALE_MARK:08x};[7:7:{{}}:8:1]",
            "    ISETP.F P0, RZ, RZ;[7:7:{}:15:1]",
            "    NOP;[7:7:{}:15:1]",
            f"    {prod.inst};[7:7:{{}}:1:1]",
        ]
        lines += base.filler(gap, coarse)
        off = 4 * i
        if consumer == "selector":
            lines += [
                "    SEL R50, R30, R32, P0;[3:7:{}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            ]
        elif consumer == "p2r":
            lines += [
                "    P2R R50, PR, RZ, 0x1;[3:7:{}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            ]
        elif consumer == "guard":
            lines += [
                f"    @P0 MOV32I R50, 0x{base.FRESH_MARK:08x};[3:7:{{}}:8:1]",
                "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:8:1]",
            ]
        elif consumer == "branch":
            t, d = f"true{i}", f"done{i}"
            lines += [
                f"    @P0 BRA #label({t});[7:7:{{}}:5:1]",
                f"    MOV32I R51, 0x{base.STALE_MARK:08x};[7:7:{{}}:5:1]",
                f"    BRA #label({d});[7:7:{{}}:5:1]",
                f"    #def_label({t})",
                f"    MOV32I R51, 0x{base.FRESH_MARK:08x};[7:7:{{}}:5:1]",
                f"    #def_label({d})",
            ]
        else:
            raise ValueError(consumer)
        lines.append(
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{off:x}], R51;[0:7:{{}}:1:0]")
    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def measure(builder, fn: str, reps: int, fresh: int, stale: int,
            isolated: bool) -> str:
    if not isolated:
        return base.states(base.run_source(builder(), fn, reps), fresh, stale)
    saved = list(base.GAPS)
    out = []
    try:
        for gap in saved:
            base.GAPS = [gap]
            out.append(base.states(base.run_source(builder(), fn, reps),
                                   fresh, stale)[0])
    finally:
        base.GAPS = saved
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=("all", "gpr", "pred"), default="all")
    ap.add_argument("--producer", action="append")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--isolated", action="store_true")
    ap.add_argument("--gaps", default=None,
                    help="comma-separated issue gaps (default: shared full sweep)")
    ns = ap.parse_args()
    if ns.gaps:
        base.GAPS = [int(x) for x in ns.gaps.split(",")]
    selected = {x.upper() for x in ns.producer} if ns.producer else None
    gaps = list(base.GAPS)
    print("gaps: " + " ".join(f"{x:2}" for x in gaps))
    ok = True
    if ns.kind in ("all", "gpr"):
        print("\nALU-Heavy GPR result")
        for prod in GPR_PRODUCERS:
            if selected and prod not in selected:
                continue
            producer = GPR_PRODUCERS[prod]
            for cons in base.GPR_CONSUMERS:
                for coarse in (False, True):
                    pat = measure(lambda: gpr_source(prod, cons, coarse),
                                  "hlat", ns.reps,
                                  producer.fresh, producer.poison,
                                  ns.isolated)
                    boundary = next((gaps[i] for i in range(len(gaps))
                                     if all(x == "F" for x in pat[i:])), None)
                    print(f"{prod:10} -> {cons:8} "
                          f"{'coarse' if coarse else 'fine':6} {pat} permanent={boundary}")
                    ok &= boundary is not None
    if ns.kind in ("all", "pred"):
        print("\nALU-Heavy PRED result")
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
                        fresh, stale = base.FRESH_MARK, base.STALE_MARK
                    pat = measure(lambda: pred_source(prod, cons, coarse),
                                  "hplat", ns.reps, fresh, stale, ns.isolated)
                    boundary = next((gaps[i] for i in range(len(gaps))
                                     if all(x == "F" for x in pat[i:])), None)
                    print(f"{prod:10} -> {cons:8} "
                          f"{'coarse' if coarse else 'fine':6} {pat} permanent={boundary}")
                    ok &= boundary is not None
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
