#!/usr/bin/env python3
"""Test whether B200 FP64 shares SHFL's saturated SM-wide MIO queue.

Warp 0 is timed.  Warps 1/2/3, on the other three subcores, run a long SHFL
stream whose aggregate arrival rate exceeds SHFL's measured SM-wide service
rate.  Active SHFL, predicated-off SHFL, and NOP backgrounds distinguish MIO
execution/admission pressure from fetch/front-end traffic.  A timed SHFL
victim is the positive control; DADD is the tested path.
"""

from __future__ import annotations

import argparse
import collections
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.arch import current  # noqa: E402


BACKGROUNDS = {
    "nop": "NOP",
    "off": "@P6 SHFL.BFLY PT, R40, R24, 0x1, 0x1f",
    "shfl": "SHFL.BFLY PT, R40, R24, 0x1, 0x1f",
    "dadd_off": "@P6 DADD {RZ,RZ}, {R24,R25}, {R26,R27}",
    "dadd": "DADD {RZ,RZ}, {R24,R25}, {R26,R27}",
}


def victim_ops(kind: str, count: int) -> list[str]:
    ops = []
    for i in range(count):
        if kind == "dadd":
            d = 40 + 2 * (i % 40)
            inst = (f"DADD {{R{d},R{d + 1}}}, "
                    "{R24,R25}, {R26,R27}")
        elif kind == "shfl":
            d = 40 + (i % 80)
            inst = f"SHFL.BFLY PT, R{d}, R24, 0x1, 0x1f"
        elif kind == "nop":
            inst = "NOP"
        else:
            raise ValueError(kind)
        ops.append(f"    {inst};[7:7:{{}}:1:1]")
    return ops


def source(victim: str, background: str, delay: int,
           victim_count: int, background_count: int) -> str:
    bg = BACKGROUNDS[background]
    lines = [
        "#fn fp64shfl(out<8>) {",
        "    #pragma MAXREG_COUNT(128)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    MOV32I R24, 0;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3ff00000;[7:7:{}:5:1]",
        "    MOV32I R26, 0;[7:7:{}:5:1]",
        "    MOV32I R27, 0x3ff00000;[7:7:{}:5:1]",
        "    ISETP.F P6, RZ, RZ;[7:7:{}:13:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        "    BRA #label(background);[7:7:{}:5:1]",
        "#def_label(victim)",
    ]
    lines += ["    NOP;[7:7:{}:8:1]" for _ in range(delay)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    lines += victim_ops(victim, victim_count)
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:0:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(background)",
    ]
    for i in range(background_count):
        # Rotate destinations without changing the instruction family.  The
        # background has enough registers to avoid a WAW within its backlog.
        d = 40 + (i % 80)
        inst = bg.replace("R40", f"R{d}")
        lines.append(f"    {inst};[7:7:{{}}:1:1]")
    lines += [
        "#def_label(done)",
        "    EXIT;[7:7:{0}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--victims", default="nop,shfl,dadd")
    p.add_argument("--backgrounds", default="nop,off,shfl")
    p.add_argument("--delays", default="0,2,4,8")
    p.add_argument("--victim-count", type=int, default=64)
    p.add_argument("--background-count", type=int, default=256)
    p.add_argument("--reps", type=int, default=21)
    ns = p.parse_args()
    victims = [x for x in ns.victims.split(",") if x]
    backgrounds = [x for x in ns.backgrounds.split(",") if x]
    delays = [int(x) for x in ns.delays.split(",") if x]
    if (any(x not in {"nop", "shfl", "dadd"} for x in victims)
            or any(x not in BACKGROUNDS for x in backgrounds)
            or min(delays, default=-1) < 0 or ns.victim_count <= 0
            or ns.background_count <= 0 or ns.reps <= 0):
        p.error("invalid mode, count, delay, or repetitions")

    print(f"FP64 versus saturated SHFL queue ({current().name})")
    print(f"victim_count={ns.victim_count} background_count={ns.background_count}")
    for victim in victims:
        for delay in delays:
            fields = []
            for background in backgrounds:
                cubin = assemble(source(
                    victim, background, delay,
                    ns.victim_count, ns.background_count), check_deps=True)
                mod = CudaModule(cubin)
                out = mod.devmem_alloc(16)
                values = []
                try:
                    for rep in range(ns.reps + 1):
                        mod.launch("fp64shfl", grid=(1,), block=(128,),
                                   args=[out])
                        mod.synchronize()
                        if rep:
                            t0, t1 = struct.unpack(
                                "<QQ", mod.device_read(out, 16))
                            values.append((t1 - t0) & ((1 << 64) - 1))
                finally:
                    mod.devmem_free(out)
                hist = dict(sorted(collections.Counter(values).items()))
                fields.append(
                    f"{background}:med={statistics.median(values):g} {hist}")
            print(f"{victim:4s} delay={delay:2d}  " + "  ".join(fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
