#!/usr/bin/env python3
"""Matched-control throughput for INT<->FMA cross-pipe forwarding."""

from __future__ import annotations

import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(direction: str, mode: str, layout: str, lookup: bool,
           n: int = 128) -> str:
    offsets = {"EEE": (0, 2, 4), "EOE": (0, 3, 4),
               "EOO": (0, 3, 5)}[layout]
    lines = [
        "#fn crossbw(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    MOV R4, R2;[7:7:{1}:5:1]",
        "    MOV32I R11, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R13, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R15, 0x40800000;[7:7:{}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    for i in range(n):
        base = 40 + 12 * (i % 4)
        a, b, c = (base + x for x in offsets)
        d, e = base + 8, base + 10
        prev = 40 + 12 * ((i - 1) % 4)
        pa, pb, pc = (prev + x for x in offsets)
        dests = {"one": (d, e, a), "two": (d, b, a),
                 "three": (c, b, a), "repeat": (d, e, a)}[mode]
        srcs = ((15, 13, 11) if mode != "repeat" else (15, 13, 13))
        if direction == "int-fma":
            for dst, src in zip(dests, srcs):
                lines.append(
                    f"    IADD3 R{dst}, R{src}, RZ, RZ;[7:7:{{}}:1:1]")
            lines += ["    NOP;[7:7:{}:1:1]", "    NOP;[7:7:{}:1:1]"]
            if not lookup and mode == "one":
                ops = f"R{pa}, R13, R15"
            elif not lookup and mode == "two":
                ops = f"R{pa}, R{pb}, R15"
            elif not lookup and mode == "three":
                ops = f"R{pa}, R{pb}, R{pc}"
            elif not lookup:
                ops = f"R{pa}, R{pa}, R{pa}"
            elif mode == "one":
                ops = f"R{a}, R13, R15"
            elif mode == "two":
                ops = f"R{a}, R{b}, R15"
            elif mode == "three":
                ops = f"R{a}, R{b}, R{c}"
            else:
                ops = f"R{a}, R{a}, R{a}"
            lines.append(f"    FFMA RZ, {ops};[7:7:{{}}:1:1]")
        else:
            for dst, src in zip(dests, srcs):
                lines.append(f"    FADD R{dst}, R{src}, RZ;[7:7:{{}}:1:1]")
            lines += ["    NOP;[7:7:{}:1:1]", "    NOP;[7:7:{}:1:1]"]
            if not lookup and mode == "one":
                ops = f"R{pa}, R13, R15"
            elif not lookup and mode == "two":
                ops = f"R{pa}, R{pb}, R15"
            elif not lookup and mode == "three":
                ops = f"R{pa}, R{pb}, R{pc}"
            elif not lookup:
                ops = f"R{pa}, R{pa}, R{pa}"
            elif mode == "one":
                ops = f"R{a}, R13, R15"
            elif mode == "two":
                ops = f"R{a}, R{b}, R15"
            elif mode == "three":
                ops = f"R{a}, R{b}, R{c}"
            else:
                ops = f"R{a}, R{a}, R{a}"
            lines.append(f"    IADD3 RZ, {ops};[7:7:{{}}:1:1]")
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:7:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(direction: str, mode: str, layout: str, lookup: bool,
        reps: int = 10, n: int = 128) -> list[float]:
    mod = CudaModule(assemble(
        source(direction, mode, layout, lookup, n), check_deps=False))
    out = mod.devmem_alloc(64)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("crossbw", grid=(1,), block=(1,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            if rep:
                vals.append(((t1 - t0) & ((1 << 64) - 1)) / n)
    finally:
        mod.devmem_free(out)
    return vals


def main() -> int:
    print("direction mode layout active control delta (cycles/iteration)")
    for direction in ("int-fma", "fma-int"):
        for mode in ("one", "two", "three", "repeat"):
            for layout in ("EEE", "EOE", "EOO"):
                active = statistics.median(run(direction, mode, layout, True))
                control = statistics.median(run(direction, mode, layout, False))
                print(f"{direction:7} {mode:6} {layout} {active:7.3f} "
                      f"{control:7.3f} {active-control:+7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
