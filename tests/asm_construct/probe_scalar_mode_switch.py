#!/usr/bin/env python3
"""Distinguish mixed scalar-pipe bandwidth from warp-switch/mode cost on SM120.

Warp 0 and warp 4 share a subcore.  Both execute all-predicated-off arithmetic
streams, removing RF reads and architectural execution.  Instructions use
yield=0 inside a quantum and yield=1 at its boundary, controlling how often
the scheduler can alternate the two encoded pipe families.
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
    "iadd3": "IADD3 R40, R24, R27, R28",
    "imad": "IMAD R40, R24, R27, R28",
    "ffma": "FFMA R40, R24, R27, R28",
    "fadd": "FADD R40, R24, R27",
    "hfma2": "HFMA2 R40, R24, R27, R28",
    "hadd2": "HADD2 R40, R24, R27",
}


def body(name: str, n: int, quantum: int) -> list[str]:
    inst = OPS[name]
    return [
        f"    @P6 {inst};[7:7:{{}}:1:{1 if (i + 1) % quantum == 0 else 0}]"
        for i in range(n)
    ]


def source(a: str, b: str, n: int, quantum: int, factor: int) -> str:
    return "\n".join([
        "#fn modeswitch(out<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR.U32 R5, R4, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        "    MOV32I R24, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40003c00;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f003c00;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *body(a, n, quantum),
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:5:1]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
        "    CS2R {R34,R35}, SR_CLOCKLO;[7:7:{}:5:0]",
        *body(b, n * factor, quantum),
        "    CS2R {R36,R37}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:5:1]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R34,R35};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R36,R37};[7:1:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def measure(a: str, b: str, n: int, quantum: int,
            factor: int, reps: int) -> tuple[float, float]:
    mod = CudaModule(assemble(source(a, b, n, quantum, factor),
                              arch="sm120", check_deps=True))
    out = mod.devmem_alloc(256 * 16)
    victims, contenders = [], []
    try:
        mod.launch("modeswitch", grid=(1,), block=(256,), args=[out])
        mod.synchronize()
        for _ in range(reps):
            mod.launch("modeswitch", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            c0, c1 = struct.unpack("<QQ", mod.device_read(out + 4 * 32 * 16, 16))
            victims.append((t1 - t0) / n)
            contenders.append((c1 - c0) / (n * factor))
    finally:
        mod.devmem_free(out)
    return min(victims), min(contenders)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", default="hfma2,ffma;ffma,hfma2;hfma2,hfma2;ffma,ffma")
    ap.add_argument("--quantums", default="1,2,4,8,16,32")
    ap.add_argument("--n", type=int, default=256)
    ap.add_argument("--factor", type=int, default=4)
    ap.add_argument("--reps", type=int, default=7)
    args = ap.parse_args()
    print("victim contender quantum victim_cpi contender_cpi")
    for pair in args.pairs.split(";"):
        a, b = pair.split(",", 1)
        for q in (int(x) for x in args.quantums.split(",") if x):
            va, vb = measure(a, b, args.n, q, args.factor, args.reps)
            print(f"{a:7s} {b:9s} {q:3d} {va:10.3f} {vb:13.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
