#!/usr/bin/env python3
"""Amplify possible LDCU/UDP uniform-RF writeback collisions in one warp.

Each round issues one scoreboarded LDCU to UR16, K active or predicated-off
UMOV-immediate writes, then req-waits the load.  Repetition amplifies a
single-cycle completion collision.  Storm targets distinguish another word
of UR16's row from the same word-bank position in a different row.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


STORM_DEST = {
    "same_row_b1": 17,
    "same_row_b2": 18,
    "same_row_b3": 19,
    "diff_row_b0": 40,
    "diff_row_b1": 41,
}


def source(storm_kind: str, gap: int, rounds: int, pred: bool) -> str:
    sd = STORM_DEST[storm_kind]
    guard = "@!UPT " if pred else ""
    lines = [
        "#fn urfwbserial(value<4>, out<8>) {",
        "    #pragma MAXREG_COUNT(32)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{1}:5:0]",
    ]
    for r in range(rounds):
        sb = r % 6
        lines.append(
            f"    LDCU UR16, #param(value);[{sb}:7:{{}}:1:0]")
        for i in range(gap):
            lines.append(
                f"    {guard}UMOV UR{sd}, 0x{0x12340000 + i:x};"
                "[7:7:{}:1:0]")
        lines.append(f"    UMOV UR30, UR16;[7:7:{{{sb}}}:1:0]")
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--storm", choices=STORM_DEST, default="same_row_b1")
    p.add_argument("--gap", type=int, default=8)
    p.add_argument("--rounds", type=int, default=32)
    p.add_argument("--pred", action="store_true")
    p.add_argument("--reps", type=int, default=15)
    ns = p.parse_args()
    if ns.gap < 0 or ns.gap > 32 or ns.rounds <= 0 or ns.rounds > 64:
        p.error("gap must be 0..32 and rounds 1..64")

    mod = CudaModule(assemble(source(ns.storm, ns.gap, ns.rounds, ns.pred),
                                    check_deps=True))
    out = mod.devmem_alloc(16)
    vals = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("urfwbserial", grid=(1,), block=(32,),
                       args=[0x12345678, out])
            mod.synchronize()
            if rep:
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    med = statistics.median(vals)
    print(f"storm={ns.storm} gap={ns.gap} rounds={ns.rounds} pred={ns.pred} "
          f"cycles={vals} median={med:g} cycles/round={med/ns.rounds:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
