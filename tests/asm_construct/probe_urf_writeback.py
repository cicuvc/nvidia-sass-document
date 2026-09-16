#!/usr/bin/env python3
"""Probe uniform-RF completion arbitration with LDCU versus UDP writes.

Warp 0 issues a scoreboarded LDCU into UR16 and times its first req-waiting
consumer.  A second warp emits a yield=0 UMOV-immediate write storm either on
the same subcore (warp 4) or another subcore (warp 1).  Storm destinations
separate same-row/different-word from different-row/same-low-two-bits cases.
This distinguishes a row-wide URF write service from independent word banks,
subject to any buffering in front of architectural commit.
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
    "same_row_b1": 17,       # target UR16: same 128-bit row, other word
    "same_row_b2": 18,
    "same_row_b3": 19,
    "diff_row_b0": 40,       # same low two index bits, different row
    "diff_row_b1": 41,
}


def source(placement: str, storm_kind: str, n: int, width: int,
           victim_delay: int) -> str:
    contender = 4 if placement == "same" else 1
    block = (contender + 1) * 32
    if width == 32:
        suffix, dst = "", "UR16"
    elif width == 64:
        suffix, dst = ".64", "{UR16,UR17}"
    elif width == 128:
        suffix, dst = ".128", "{UR16,UR17,UR18,UR19}"
    else:
        raise ValueError(width)
    storm_dst = STORM_DEST[storm_kind]
    storm = [f"    UMOV UR{storm_dst}, 0x{0x12340000 + i:x};"
             "[7:7:{}:1:1]" for i in range(n)]
    lines = [
        "#fn urfwb(value<16>, out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        f"    ISETP.EQ.AND P0, PT, R5, 0x{contender:x}, PT;"
        "[7:7:{}:13:1]",
        "    @P0 BRA #label(storm);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(victim_delay)],
        f"    LDCU{suffix} {dst}, #param(value);[0:7:{{}}:1:0]",
        "    UMOV UR30, UR16;[7:7:{0}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(storm)",
        "    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{}:5:0]",
        *storm,
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x10], {R24,R25};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x18], {R26,R27};[7:1:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    # Keep the computed launch width visible in source generation assertions.
    assert block in (64, 160)
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--placement", choices=("same", "diff"), default="same")
    p.add_argument("--storm", choices=STORM_DEST, default="same_row_b1")
    p.add_argument("--count", type=int, default=128)
    p.add_argument("--width", type=int, choices=(32, 64, 128), default=32)
    p.add_argument("--victim-delay", type=int, default=24)
    p.add_argument("--reps", type=int, default=15)
    ns = p.parse_args()
    if (ns.count < 0 or ns.count > 512 or ns.victim_delay < 0
            or ns.victim_delay > 128 or ns.reps <= 0):
        p.error("count must be 0..512, victim-delay 0..128, reps positive")
    if ns.width >= 64 and ns.storm.startswith("same_row"):
        # A same-row scalar storm would overwrite part of the LDCU result.
        # The result is dead, but excluding this case avoids a WAW dependency
        # from obscuring pure physical-port arbitration.
        p.error("use a different-row storm for 64/128-bit LDCU")

    text = source(ns.placement, ns.storm, ns.count, ns.width,
                  ns.victim_delay)
    mod = CudaModule(assemble(text, check_deps=True))
    out = mod.devmem_alloc(32)
    contender = 4 if ns.placement == "same" else 1
    vals = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("urfwb", grid=(1,), block=((contender + 1) * 32,),
                       args=[bytes(range(16)), out])
            mod.synchronize()
            if rep:
                t0, t1, s0, s1 = struct.unpack("<QQQQ",
                                                mod.device_read(out, 32))
                vals.append(((t1 - t0) & ((1 << 64) - 1),
                             (s0 - t0) & ((1 << 64) - 1),
                             (s1 - t0) & ((1 << 64) - 1)))
    finally:
        mod.devmem_free(out)
    victim = [x[0] for x in vals]
    storm_start = [x[1] for x in vals]
    storm_end = [x[2] for x in vals]
    print(f"placement={ns.placement} storm={ns.storm} count={ns.count} "
          f"width={ns.width} victim={victim} "
          f"median={statistics.median(victim):g} "
          f"storm_rel=[{statistics.median(storm_start):g},"
          f"{statistics.median(storm_end):g}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
