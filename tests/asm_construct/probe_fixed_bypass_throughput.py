#!/usr/bin/env python3
"""Sustained effective operand-forwarding bandwidth for fixed pipelines."""

from __future__ import annotations

import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


MODES = ("none", "one", "two", "ac", "bc", "three", "repeat")


def source(family: str, mode: str, n: int, layout: str = "EEE",
           lookup: bool = True) -> str:
    lines = [
        "#fn bwt(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R5, SR_TID.X;[2:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R5, 0x10, {R2,R3};[7:7:{1,2}:5:1]",
        "    MOV32I R10, 0;[7:7:{}:5:1]",
        "    MOV32I R11, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R12, 2;[7:7:{}:5:1]",
        "    MOV32I R13, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R14, 4;[7:7:{}:5:1]",
        "    MOV32I R15, 0x40800000;[7:7:{}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    offsets = {"EEE": (0, 2, 4), "EOE": (0, 3, 4),
               "EOO": (0, 3, 5)}[layout]
    for i in range(n):
        base = 40 + 12 * (i % 4)
        a, b, c = (base + x for x in offsets)
        d, e = base + 8, base + 10
        prev = 40 + 12 * ((i - 1) % 4)
        pa, pb, pc = (prev + x for x in offsets)
        if family == "int":
            producers = {
                "none": ((d, 8), (e, 16), (c, 32)),
                "one": ((d, 8), (e, 16), (a, 1)),
                "two": ((d, 8), (b, 2), (a, 1)),
                "ac": ((d, 8), (c, 4), (a, 1)),
                "bc": ((d, 8), (c, 4), (b, 2)),
                "three": ((c, 4), (b, 2), (a, 1)),
                "repeat": ((d, 8), (e, 16), (a, 1)),
            }[mode]
            for dst, val in producers:
                lines.append(
                    f"    IADD3 R{dst}, R10, {val}, RZ;[7:7:{{}}:1:1]")
            lines.append("    NOP;[7:7:{}:1:1]")
            if mode == "none":
                ops = "R10, R12, R14"
            elif not lookup and mode == "one":
                ops = f"R{pa}, R12, R14"
            elif not lookup and mode == "two":
                ops = f"R{pa}, R{pb}, R14"
            elif not lookup and mode == "ac":
                ops = f"R{pa}, R12, R{pc}"
            elif not lookup and mode == "bc":
                ops = f"R10, R{pb}, R{pc}"
            elif not lookup and mode == "three":
                ops = f"R{pa}, R{pb}, R{pc}"
            elif not lookup and mode == "repeat":
                ops = f"R{pa}, R{pa}, R{pa}"
            elif mode == "one":
                ops = f"R{a}, R12, R14"
            elif mode == "two":
                ops = f"R{a}, R{b}, R14"
            elif mode == "ac":
                ops = f"R{a}, R12, R{c}"
            elif mode == "bc":
                ops = f"R10, R{b}, R{c}"
            elif mode == "three":
                ops = f"R{a}, R{b}, R{c}"
            else:
                ops = f"R{a}, R{a}, R{a}"
            lines.append(f"    IADD3 RZ, {ops};[7:7:{{}}:1:1]")
        else:
            producers = {
                "none": ((d, 15), (e, 13), (c, 11)),
                "one": ((d, 15), (e, 13), (a, 11)),
                "two": ((d, 15), (b, 13), (a, 11)),
                "ac": ((d, 15), (c, 15), (a, 11)),
                "bc": ((d, 15), (c, 15), (b, 13)),
                "three": ((c, 15), (b, 13), (a, 11)),
                "repeat": ((d, 15), (e, 13), (a, 13)),
            }[mode]
            for dst, src in producers:
                lines.append(f"    FADD R{dst}, R{src}, RZ;[7:7:{{}}:1:1]")
            lines.append("    NOP;[7:7:{}:1:1]")
            if mode == "none":
                ops = "R11, R13, R15"
            elif not lookup and mode == "one":
                ops = f"R{pa}, R13, R15"
            elif not lookup and mode == "two":
                ops = f"R{pa}, R{pb}, R15"
            elif not lookup and mode == "ac":
                ops = f"R{pa}, R13, R{pc}"
            elif not lookup and mode == "bc":
                ops = f"R11, R{pb}, R{pc}"
            elif not lookup and mode == "three":
                ops = f"R{pa}, R{pb}, R{pc}"
            elif not lookup and mode == "repeat":
                ops = f"R{pa}, R{pa}, R{pa}"
            elif mode == "one":
                ops = f"R{a}, R13, R15"
            elif mode == "two":
                ops = f"R{a}, R{b}, R15"
            elif mode == "ac":
                ops = f"R{a}, R13, R{c}"
            elif mode == "bc":
                ops = f"R11, R{b}, R{c}"
            elif mode == "three":
                ops = f"R{a}, R{b}, R{c}"
            else:
                ops = f"R{a}, R{a}, R{a}"
            lines.append(f"    FFMA RZ, {ops};[7:7:{{}}:1:1]")
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R22,R23};[7:7:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(family: str, mode: str, n: int = 128, reps: int = 20,
        layout: str = "EEE", lookup: bool = True,
        block: int = 1) -> list[float]:
    mod = CudaModule(assemble(
        source(family, mode, n, layout, lookup), check_deps=False))
    out = mod.devmem_alloc(max(1024, block * 16))
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("bwt", grid=(1,), block=(block,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            if rep:
                vals.append(((t1 - t0) & ((1 << 64) - 1)) / n)
    finally:
        mod.devmem_free(out)
    return vals


def main() -> int:
    print("five instructions/iteration: 3 producers + gap-2 NOP + 1 consumer")
    print("family mode    median cyc/iter   range")
    for family in ("int", "fma"):
        for mode in MODES:
            vals = run(family, mode)
            print(f"{family:5} {mode:6} {statistics.median(vals):10.3f} "
                  f"{min(vals):.3f}..{max(vals):.3f}")
    print("\nparity layouts (A/B/C parity):")
    for family in ("int", "fma"):
        for mode in ("two", "three"):
            for layout in ("EEE", "EOE", "EOO"):
                vals = run(family, mode, layout=layout)
                print(f"{family:5} {mode:5} {layout}: "
                      f"{statistics.median(vals):.3f} cyc/iter")
    print("\nmatched producer controls (active - stable-RF consumer):")
    for family in ("int", "fma"):
        for mode in ("one", "two", "ac", "bc", "three", "repeat"):
            for layout in ("EEE", "EOE", "EOO"):
                active = statistics.median(
                    run(family, mode, layout=layout, lookup=True))
                control = statistics.median(
                    run(family, mode, layout=layout, lookup=False))
                print(f"{family:5} {mode:6} {layout}: active={active:.3f} "
                      f"control={control:.3f} delta={active-control:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
