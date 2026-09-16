#!/usr/bin/env python3
"""Stale/fresh boundary for potentially coincident UDP result writes.

UIADD3 writes selector A=41 and the following UMOV writes selector B=42.
Indexed-RF MOV consumers deliberately sample committed URF state rather than
the ordinary UDP-result forwarding path.  Destination layouts and consumer
orders distinguish row-wide write arbitration from per-word-bank ports.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


GAPS = tuple(range(0, 15))
SCALAR_LAYOUTS = {"same_row": 17, "diff_row_same_word": 20,
                  "diff_row_other_word": 21}


def config(wide_b: bool):
    if wide_b:
        return ({"same_row": 18, "diff_row": 20}, ("ABC", "BAC", "CAB"), 3)
    return (SCALAR_LAYOUTS, ("AB", "BA"), 2)


def source(phase: int, wide_b: bool) -> str:
    layouts, orders, nvalues = config(wide_b)
    lines = [
        "#fn urfwbbound(out<8>) {",
        "    #pragma MAXREG_COUNT(72)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    MOV32I R40, 0x40404040;[7:7:{}:5:1]",
        "    MOV32I R41, 0xa1a1a1a1;[7:7:{}:5:1]",
        "    MOV32I R42, 0xb2b2b2b2;[7:7:{}:5:1]",
        "    MOV32I R43, 0xc3c3c3c3;[7:7:{}:5:1]",
        "    UMOV UR8, 0x14;[7:7:{}:5:1]",
        "    UMOV UR9, 0x15;[7:7:{}:5:1]",
        "    UMOV UR10, 0x0;[7:7:{}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
    ]
    case = 0
    for layout, bd in layouts.items():
        for order in orders:
            for gap in GAPS:
                off = case * nvalues * 4
                reset_b = (f"UMOV.64 {{UR{bd},UR{bd + 1}}}, "
                           "0x0000002800000028" if wide_b
                           else f"UMOV UR{bd}, 0x28")
                write_b = (f"UMOV.64 {{UR{bd},UR{bd + 1}}}, "
                           "0x0000002b0000002a" if wide_b
                           else f"UMOV UR{bd}, 0x2a")
                lines += [
                    "    UMOV UR16, 0x28;[7:7:{}:1:0]",
                    f"    {reset_b};[7:7:{{}}:1:0]",
                    "    NOP;[7:7:{}:8:1]",
                    "    UIADD3 UR16, UPT, UPT, UR8, UR9, UR10;"
                    "[7:7:{}:1:0]",
                ]
                lines += ["    NOP;[7:7:{}:1:0]"] * phase
                lines.append(f"    {write_b};[7:7:{{}}:1:0]")
                lines += ["    NOP;[7:7:{}:1:0]"] * gap
                selectors = {"A": 16, "B": bd, "C": bd + 1}
                for j, label in enumerate(order):
                    stall = 5 if j == nvalues - 1 else 1
                    lines.append(
                        f"    MOV R{60 + j}, R[UR{selectors[label]}];"
                        f"[7:7:{{}}:{stall}:{1 if stall == 5 else 0}]")
                for j in range(nvalues):
                    req = "{1}" if j == 0 else "{}"
                    lines.append(
                        f"    STG.E.STRONG.GPU [{{R2,R3}}+0x{off + 4*j:x}], "
                        f"R{60 + j};[7:1:{req}:8:0]")
                case += 1
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def name(v: int) -> str:
    return {0x40404040: "P", 0xA1A1A1A1: "A",
            0xB2B2B2B2: "B", 0xC3C3C3C3: "C"}.get(v, f"?{v:08x}")


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", type=int, choices=range(0, 9), default=0)
    p.add_argument("--wide-b", action="store_true")
    ns = p.parse_args()
    layouts, orders, nvalues = config(ns.wide_b)
    # Early selector reads are intentional and lie inside conservative table
    # hazards, hence dependency checking is disabled for this boundary probe.
    mod = CudaModule(assemble(source(ns.phase, ns.wide_b), check_deps=False))
    ncases = len(layouts) * len(orders) * len(GAPS)
    out = mod.devmem_alloc(ncases * nvalues * 4)
    try:
        results = []
        for _ in range(5):
            mod.device_write(out, bytes(ncases * nvalues * 4))
            mod.launch("urfwbbound", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            results.append(struct.unpack(f"<{ncases * nvalues}I",
                                         mod.device_read(
                                             out, ncases * nvalues * 4)))
    finally:
        mod.devmem_free(out)
    if any(x != results[0] for x in results[1:]):
        print("warning: nondeterministic repetitions")
    vals = results[-1]
    case = 0
    for layout in layouts:
        for order in orders:
            states = []
            for _ in GAPS:
                got = vals[nvalues * case:nvalues * case + nvalues]
                states.append("".join(name(x) for x in got))
                case += 1
            print(f"phase={ns.phase} {layout:20s} order={order}  "
                  + " ".join(f"g{g}:{s}" for g, s in zip(GAPS, states)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
