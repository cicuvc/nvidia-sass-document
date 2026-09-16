#!/usr/bin/env python3
"""Separate fixed-pipe -> R2UR input forwarding from R2UR output latency.

Each instance first settles a poison value in R2, optionally overwrites R2
with an INT/FMA/FP16 producer, and issues R2UR after a swept issue gap.  Eight
independent UDP reads then settle R2UR's relatively slow UR result before it
is copied to memory.  Thus stale/fresh classifies only R2UR's GPR input read.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


PRODUCERS = {
    "int": ("IADD3 R2, PT, PT, RZ, R3, RZ", 0x22222222, 0x11111111),
    "fma": ("FADD R2, R3, RZ", 0x3F800000, 0x40000000),
    # Packed (1.0,0.0) and (2.0,0.0); HADD2 with RZ is an exact pass-through.
    "fp16": ("HADD2 R2, R3, RZ", 0x3C00, 0x4000),
}


def settle_ur(off: int) -> list[str]:
    lines = ["    UMOV UR9, UR16;[7:7:{}:5:1]" for _ in range(8)]
    lines += [
        "    IADD3 R20, PT, PT, RZ, UR16, RZ;[7:7:{}:8:1]",
        f"    STG.E.STRONG.GPU [{{R6,R7}}+0x{off:x}], R20;"
        "[7:1:{0,1}:8:0]",
    ]
    return lines


def source(family: str, gaps: list[int]) -> str:
    producer, true, poison = PRODUCERS[family]
    lines = [
        "#fn r2urfwd(out<8>) {",
        "    #pragma MAXREG_COUNT(32)",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        f"    MOV32I R3, 0x{true:x};[7:7:{{}}:5:1]",
    ]
    # gap=-1 is the poison-only detector control.
    for i, gap in enumerate([-1] + gaps):
        lines += [
            f"    MOV32I R2, 0x{poison:x};[7:7:{{}}:8:1]",
            "    NOP;[7:7:{}:8:1]",
        ]
        if gap >= 0:
            lines.append(f"    {producer};[7:7:{{}}:1:1]")
            lines += ["    NOP;[7:7:{}:1:1]"] * max(0, gap - 1)
        lines.append("    R2UR UR16, R2;[2:7:{}:5:1]")
        lines += settle_ur(i * 4)
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run(family: str, gaps: list[int]) -> tuple[int, ...]:
    reset_context()
    mod = CudaModule(assemble(source(family, gaps), check_deps=False))
    out = mod.devmem_alloc(4 * (len(gaps) + 1))
    mod.device_write(out, bytes(4 * (len(gaps) + 1)))
    try:
        mod.launch("r2urfwd", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        return struct.unpack(f"<{len(gaps) + 1}I",
                             mod.device_read(out, 4 * (len(gaps) + 1)))
    finally:
        mod.devmem_free(out)


def run_latch(family: str) -> int:
    """Overwrite R2 immediately after R2UR to locate its GPR source sample."""
    _, true, poison = PRODUCERS[family]
    lines = [
        "#fn r2urlatch(out<8>) {",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        f"    MOV32I R2, 0x{poison:x};[7:7:{{}}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    R2UR UR16, R2;[2:7:{}:1:1]",
        f"    MOV32I R2, 0x{true:x};[7:7:{{}}:1:1]",
        *settle_ur(0),
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    reset_context()
    mod = CudaModule(assemble("\n".join(lines), check_deps=False))
    out = mod.devmem_alloc(4)
    try:
        mod.launch("r2urlatch", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        return struct.unpack("<I", mod.device_read(out, 4))[0]
    finally:
        mod.devmem_free(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", choices=PRODUCERS, default="int")
    p.add_argument("--reps", type=int, default=5)
    ns = p.parse_args()
    gaps = list(range(1, 17)) + [30]
    _, true, poison = PRODUCERS[ns.family]
    reps = [run(ns.family, gaps) for _ in range(ns.reps)]

    def cls(v: int) -> str:
        return "F" if v == true else ("S" if v == poison else "?")

    print(f"family={ns.family} true=0x{true:08x} poison=0x{poison:08x}")
    print("gap    : " + " ".join(f"{x:2}" for x in gaps))
    for i, vals in enumerate(reps):
        print(f"run {i}: poison={cls(vals[0])} " +
              " ".join(f" {cls(x)}" for x in vals[1:]))
    latch = [run_latch(ns.family) for _ in range(ns.reps)]
    print("post-R2UR overwrite: " + " ".join(cls(x) for x in latch) +
          " (S means R2UR sampled before the younger write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
