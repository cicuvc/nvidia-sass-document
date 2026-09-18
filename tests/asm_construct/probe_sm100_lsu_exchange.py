#!/usr/bin/env python3
"""Build a hand-scheduled B200 LDS/SHFL SM-wide throughput probe.

The output is 16 u64 values: start/end clocks for warps 0..7.  Inactive warp
records remain 0xdeadbeef.  Use tools/modal_tcgen05_alloc.py to launch the
resulting cubin on B200.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble


ACTORS = {
    "one": (0,),
    "same2": (0, 4),
    "diff2": (0, 1),
    "diff4": (0, 1, 2, 3),
    "all8": tuple(range(8)),
}


def inst(op: str, i: int, warp: int) -> str:
    if op == "mixed":
        op = "lds" if warp % 2 == 0 else "shfl"
    if op == "lds":
        return f"LDS R{40 + i % 40}, [R26]"
    if op == "lds_z":
        return f"LDS R{40 + i % 40}, [RZ]"
    if op == "lds128":
        r = 40 + 4 * (i % 10)
        return f"LDS.128 {{R{r},R{r+1},R{r+2},R{r+3}}}, [R26]"
    if op == "shfl":
        return f"SHFL.BFLY PT, R{40 + i % 40}, R24, 0x1, 0x1f"
    if op == "shfl_z":
        return f"SHFL.BFLY PT, R{40 + i % 40}, RZ, 0x1, 0x1f"
    raise ValueError(op)


def source(op: str, actors: tuple[int, ...], count: int) -> str:
    addr_shift = 4 if op == "lds128" else 2
    lines = [
        "#fn lsu_exchange(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(4096)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{2}:5:1]",
        f"    SHL R26, R6, 0x{addr_shift:x};[7:7:{{}}:5:1]",
        "    IMAD.WIDE.U32 {R8,R9}, R5, 0x10, {R2,R3};"
        "[7:7:{1}:5:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for w in actors:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{w:x}, PT;[7:7:{{}}:13:1]",
            f"    @P0 BRA #label(work_{w});[7:7:{{}}:5:1]",
        ]
    lines += ["    BRA #label(done);[7:7:{}:5:1]"]
    for w in actors:
        lines += [
            f"    #def_label(work_{w})",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        ]
        lines += [f"    {inst(op, i, w)};[7:7:{{}}:1:1]"
                  for i in range(count)]
        lines += [
            "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P1 STG.E.64.STRONG.GPU [{R8,R9}], {R20,R21};"
            "[7:3:{1}:8:0]",
            "    @P1 STG.E.64.STRONG.GPU [{R8,R9}+8], {R22,R23};"
            "[7:3:{3}:8:0]",
            "    BRA #label(done);[7:7:{}:5:1]",
        ]
    lines += ["    #def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--op", choices=("lds", "lds_z", "lds128", "shfl",
                                      "shfl_z", "mixed"), required=True)
    ap.add_argument("--actors", choices=ACTORS, required=True)
    ap.add_argument("--count", type=int, default=512)
    ap.add_argument("--output", type=Path, required=True)
    ns = ap.parse_args()
    src = source(ns.op, ACTORS[ns.actors], ns.count)
    # Branches are mutually exclusive per warp; the dependency checker cannot
    # prove that and otherwise reports false cross-branch SB3 reuse hazards.
    ns.output.write_bytes(assemble(src, arch="sm100", check_deps=False))
    print(f"wrote {ns.output}: op={ns.op} actors={ns.actors} "
          f"count={ns.count}")


if __name__ == "__main__":
    main()
