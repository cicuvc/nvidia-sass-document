#!/usr/bin/env python3
"""Test whether two aligned 64-bit UDP results can commit together."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


GAPS = tuple(range(15))
LAYOUTS = {"same_row": 18, "diff_row": 20}
ORDERS = ("ACBD", "BACD", "CABD", "DABC")


def source(phase: int) -> str:
    lines = [
        "#fn urfwb4(out<8>) {",
        "    #pragma MAXREG_COUNT(72)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    MOV32I R40, 0x40404040;[7:7:{}:5:1]",
        "    MOV32I R41, 0xa1a1a1a1;[7:7:{}:5:1]",
        "    MOV32I R42, 0xb2b2b2b2;[7:7:{}:5:1]",
        "    MOV32I R43, 0xc3c3c3c3;[7:7:{}:5:1]",
        "    MOV32I R44, 0xd4d4d4d4;[7:7:{}:5:1]",
        "    UMOV UR8, 0x1;[7:7:{}:5:1]",
        "    UMOV UR9, 0x1;[7:7:{}:5:1]",
        "    UMOV UR10, 0x28;[7:7:{}:5:1]",
        "    UMOV UR11, 0x2b;[7:7:{}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
    ]
    case = 0
    for _, bd in LAYOUTS.items():
        for order in ORDERS:
            selectors = {"A": 16, "C": 17, "B": bd, "D": bd + 1}
            for gap in GAPS:
                off = case * 16
                lines += [
                    "    UMOV.64 {UR16,UR17}, 0x0000002800000028;"
                    "[7:7:{}:1:0]",
                    f"    UMOV.64 {{UR{bd},UR{bd + 1}}}, "
                    "0x0000002800000028;[7:7:{}:1:0]",
                    "    NOP;[7:7:{}:8:1]",
                    "    UIMAD.WIDE {UR16,UR17}, UR8, UR9, {UR10,UR11};"
                    "[7:7:{}:1:0]",
                ]
                lines += ["    NOP;[7:7:{}:1:0]"] * phase
                lines.append(
                    f"    UMOV.64 {{UR{bd},UR{bd + 1}}}, "
                    "0x0000002c0000002a;[7:7:{}:1:0]")
                lines += ["    NOP;[7:7:{}:1:0]"] * gap
                for j, label in enumerate(order):
                    lines.append(
                        f"    MOV R{60 + j}, R[UR{selectors[label]}];"
                        f"[7:7:{{}}:{5 if j == 3 else 1}:{1 if j == 3 else 0}]")
                for j in range(4):
                    lines.append(
                        f"    STG.E.STRONG.GPU [{{R2,R3}}+0x{off + 4*j:x}], "
                        f"R{60 + j};[7:1:{'{1}' if j == 0 else '{}'}:8:0]")
                case += 1
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def name(v: int) -> str:
    return {0x40404040: "P", 0xA1A1A1A1: "A", 0xB2B2B2B2: "B",
            0xC3C3C3C3: "C", 0xD4D4D4D4: "D"}.get(v, "?")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", type=int, choices=range(9), default=5)
    ns = p.parse_args()
    mod = CudaModule(assemble(source(ns.phase), check_deps=False))
    ncases = len(LAYOUTS) * len(ORDERS) * len(GAPS)
    out = mod.devmem_alloc(ncases * 16)
    try:
        results = []
        for _ in range(5):
            mod.device_write(out, bytes(ncases * 16))
            mod.launch("urfwb4", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            results.append(struct.unpack(f"<{ncases * 4}I",
                                         mod.device_read(out, ncases * 16)))
    finally:
        mod.devmem_free(out)
    if any(x != results[0] for x in results[1:]):
        print("warning: nondeterministic repetitions")
    vals = results[-1]
    case = 0
    for layout in LAYOUTS:
        for order in ORDERS:
            states = []
            for _ in GAPS:
                got = vals[4 * case:4 * case + 4]
                states.append("".join(name(x) for x in got))
                case += 1
            print(f"phase={ns.phase} {layout:9s} order={order}  "
                  + " ".join(f"g{g}:{s}" for g, s in zip(GAPS, states)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
