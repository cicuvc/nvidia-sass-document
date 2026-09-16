#!/usr/bin/env python3
"""Measure effective fixed-pipe bypass operand width on sm_120."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


GAPS = list(range(1, 10)) + [12, 16]
MODES = ("one", "two", "three", "repeat")


def int_source(mode: str, gap: int) -> tuple[str, int]:
    pending = {"one": (40,), "two": (40, 42), "three": (40, 42, 44),
               "repeat": (40,)}[mode]
    # Always issue exactly three producers.  Dummies come first so the last
    # real producer has identical age in one/two/repeat where possible.
    prod = []
    if mode == "one" or mode == "repeat":
        prod = [(60, 8), (62, 16), (40, 1 if mode == "one" else 2)]
    elif mode == "two":
        prod = [(60, 8), (42, 2), (40, 1)]
    else:
        prod = [(44, 4), (42, 2), (40, 1)]
    if mode == "repeat":
        consumer, expected = "IADD3 R50, R40, R40, R40", 6
    else:
        consumer, expected = "IADD3 R50, R40, R42, R44", 7
    init = {40: 0 if 40 in pending else 1,
            42: 0 if 42 in pending else 2,
            44: 0 if 44 in pending else 4}
    lines = [
        "#fn width(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[2:7:{}:1:0]",
        "    MOV32I R10, 0;[7:7:{1,2}:5:1]",
    ]
    for reg in (40, 42, 44):
        lines.append(f"    MOV32I R{reg}, {init[reg]};[7:7:{{}}:5:1]")
    lines += ["    NOP;[7:7:{}:8:1]", "    NOP;[7:7:{}:8:1]"]
    for reg, value in prod:
        lines.append(f"    IADD3 R{reg}, R10, {value}, RZ;[7:7:{{}}:1:1]")
    lines += ["    NOP;[7:7:{}:1:1]"] * (gap - 1)
    lines += [
        f"    {consumer};[3:7:{{}}:5:1]",
        "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:5:1]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}], R51;[0:7:{}:1:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines), expected


def fma_source(mode: str, gap: int) -> tuple[str, int]:
    # Exact FP32 values: distinct consumer = 1*2+4 = 6; repeated = 2*2+2 = 6.
    bits = {1: 0x3F800000, 2: 0x40000000, 4: 0x40800000}
    pending = {"one": (40,), "two": (40, 42), "three": (40, 42, 44),
               "repeat": (40,)}[mode]
    if mode == "one":
        prod = [(60, 4), (62, 4), (40, 1)]
    elif mode == "repeat":
        prod = [(60, 4), (62, 4), (40, 2)]
    elif mode == "two":
        prod = [(60, 4), (42, 2), (40, 1)]
    else:
        prod = [(44, 4), (42, 2), (40, 1)]
    init_values = {40: 0 if 40 in pending else bits[1],
                   42: 0 if 42 in pending else bits[2],
                   44: 0 if 44 in pending else bits[4]}
    consumer = ("FFMA R50, R40, R40, R40" if mode == "repeat" else
                "FFMA R50, R40, R42, R44")
    lines = [
        "#fn width(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[2:7:{}:1:0]",
        "    MOV32I R11, 0x3f800000;[7:7:{1,2}:5:1]",
        "    MOV32I R12, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R14, 0x40800000;[7:7:{}:5:1]",
    ]
    for reg in (40, 42, 44):
        lines.append(f"    MOV32I R{reg}, 0x{init_values[reg]:08x};[7:7:{{}}:5:1]")
    lines += ["    NOP;[7:7:{}:8:1]", "    NOP;[7:7:{}:8:1]"]
    src_for = {1: 11, 2: 12, 4: 14}
    for reg, value in prod:
        lines.append(f"    FADD R{reg}, R{src_for[value]}, RZ;[7:7:{{}}:1:1]")
    lines += ["    NOP;[7:7:{}:1:1]"] * (gap - 1)
    lines += [
        f"    {consumer};[3:7:{{}}:5:1]",
        "    IADD3 R51, R50, RZ, RZ;[7:7:{3}:5:1]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}], R51;[0:7:{}:1:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines), 0x40C00000


def run(family: str, mode: str, gap: int, reps: int = 3) -> tuple[list[int], int]:
    reset_context()
    src, expected = (int_source(mode, gap) if family == "int"
                     else fma_source(mode, gap))
    mod = CudaModule(assemble(src, check_deps=False))
    out = mod.devmem_alloc(4096)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.device_write(out, bytes(4096))
            mod.launch("width", grid=(1,), block=(1,), args=[out])
            mod.synchronize()
            value, = struct.unpack("<I", mod.device_read(out, 4))
            if rep:
                vals.append(value)
    finally:
        mod.devmem_free(out)
    return vals, expected


def main() -> int:
    print("fixed-pipe bypass width; F=fresh exact result")
    print("gap : " + " ".join(f"{x:2d}" for x in GAPS))
    ok = True
    for family in ("int", "fma"):
        for mode in MODES:
            states = []
            for gap in GAPS:
                vals, expected = run(family, mode, gap)
                states.append("F" if all(v == expected for v in vals) else "S")
            permanent = next((GAPS[i] for i in range(len(GAPS))
                              if all(x == "F" for x in states[i:])), None)
            print(f"{family:3} {mode:6}: " + "  ".join(states)
                  + f"  permanent={permanent}")
            ok &= permanent is not None
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
