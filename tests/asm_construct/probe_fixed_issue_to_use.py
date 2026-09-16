#!/usr/bin/env python3
"""Calibrate real GPU clocks for fixed-pipe dependent issue/use chains.

The stale/fresh probes report a nominal SASS issue gap.  This probe measures
the actual SR_CLOCKLO distance of long chains at that known-correct forwarding
gap and compares it with an independent chain carrying identical scheduling
brackets.  It intentionally does not claim that issue-to-issue alone locates
the consumer's internal operand-use stage; the pairwise forwarding equations
are applied by the analysis note.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


@dataclass(frozen=True)
class Op:
    pipe: str
    setup: tuple[str, ...]
    dep: str
    independent: str
    safe_gap: int


OPS = {
    "MOV": Op("alu-lite", (), "MOV R{d}, R{s}", "MOV R{d}, R24", 2),
    "IADD": Op("alu-lite", ("MOV32I R27, 0x1",),
                "IADD R{d}, PT, R{s}, R27",
                "IADD R{d}, PT, R24, R27", 2),
    "IADD3": Op("alu-heavy", ("MOV32I R27, 0x1",),
                 "IADD3 R{d}, R{s}, R27, RZ",
                 "IADD3 R{d}, R24, R27, RZ", 2),
    "LOP3": Op("alu-heavy", (), "LOP3.LUT R{d}, R{s}, RZ, RZ, 0xcc, PT",
                "LOP3.LUT R{d}, R24, RZ, RZ, 0xcc, PT", 2),
    "FADD": Op("fma-lite", ("MOV32I R27, 0x3f800000",),
                "FADD R{d}, R{s}, R27",
                "FADD R{d}, R24, R27", 2),
    "FFMA": Op("fma-lite", ("MOV32I R27, 0x3f800000",
                              "MOV32I R28, 0x3f800000"),
                "FFMA R{d}, R{s}, R27, R28",
                "FFMA R{d}, R24, R27, R28", 2),
    "IMAD": Op("fma-heavy", ("MOV32I R27, 0x1", "MOV32I R28, 0x1"),
                "IMAD R{d}, R{s}, R27, R28",
                "IMAD R{d}, R24, R27, R28", 2),
    "IMAD.WIDE": Op(
        "fma-heavy-wide",
        ("MOV32I R27, 0x1", "MOV32I R28, 0x1", "MOV32I R29, 0x0"),
        "IMAD.WIDE.U32 {{R{d},R{d1}}}, PT, R{s}, R27, {{R28,R29}}",
        "IMAD.WIDE.U32 {{R{d},R{d1}}}, PT, R24, R27, {{R28,R29}}", 1),
    "IMAD.HI": Op(
        "fma-heavy-hi",
        ("MOV32I R24, 0x1", "MOV32I R27, 0x1",
         "MOV32I R28, 0xffffffff", "MOV32I R29, 0x0"),
        "IMAD.HI R{d}, PT, R24, R27, {{R{c0},R{c1}}}",
        "IMAD.HI R{d}, PT, R24, R27, {{R28,R29}}", 2),
    "HADD2": Op("packed-fp", ("MOV32I R27, 0x3c003c00",),
                 "HADD2 R{d}, R{s}, R27",
                 "HADD2 R{d}, R24, R27", 2),
}


def source(name: str, mode: str, gap: int, count: int, loops: int) -> str:
    op = OPS[name]
    lines = [
        "#fn i2u(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        "    MOV32I R24, 0x3f800000;[7:7:{0}:8:1]",
        "    MOV32I R40, 0x00000000;[7:7:{}:8:1]",
        "    MOV32I R41, 0x40000000;[7:7:{}:8:1]",
        "    MOV32I R42, 0x40000000;[7:7:{}:8:1]",
        "    MOV32I R43, 0x40000000;[7:7:{}:8:1]",
        f"    MOV32I R80, 0x{loops:x};[7:7:{{}}:8:1]",
    ]
    lines += [f"    {x};[7:7:{{}}:8:1]" for x in op.setup]
    if name == "IMAD.HI":
        lines += [
            "    MOV32I R40, 0xffffffff;[7:7:{}:8:1]",
            "    MOV32I R41, 0x00000000;[7:7:{}:8:1]",
            "    MOV32I R42, 0xffffffff;[7:7:{}:8:1]",
            "    MOV32I R43, 0x40000000;[7:7:{}:8:1]",
        ]
    lines += [
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    #def_label(chain_loop)",
    ]
    dsts = list(range(40, 80))
    for i in range(count):
        if mode == "dep":
            if name == "IMAD.WIDE":
                s, d = ((40, 42) if i % 2 == 0 else (42, 40))
                c0 = c1 = 0
            elif name == "IMAD.HI":
                if i % 2 == 0:
                    s, d, c0, c1 = 0, 43, 40, 41
                else:
                    s, d, c0, c1 = 0, 41, 42, 43
            else:
                s, d = ((40, 41) if i % 2 == 0 else (41, 40))
                c0 = c1 = 0
            inst = op.dep.format(s=s, d=d, d1=d + 1, c0=c0, c1=c1)
        elif mode == "ind":
            if name == "IMAD.WIDE":
                d = 40 + 2 * (i % 20)
            else:
                d = dsts[i % len(dsts)]
            inst = op.independent.format(d=d, d1=d + 1, c0=28, c1=29)
        elif mode == "nop":
            inst = "NOP"
        else:
            raise ValueError(mode)
        lines.append(f"    {inst};[7:7:{{}}:{gap}:1]")
    lines += [
        # Sustained phase-safe ALU-Lite -> ALU-Lite distance.  The isolated
        # pair is fresh at nominal gap 2, but this periodic back-edge can
        # otherwise let ISETP observe the pre-decrement value once per loop.
        "    IADD32I R80, PT, R80, -0x1;[7:7:{}:4:1]",
        # Keep the loop-control predicate far outside its phase-sensitive
        # guard/CBU forwarding window.  A lone nominal stall-13 producer can
        # execute one extra iteration at this back-edge PC phase.
        "    ISETP.NE.AND P0, PT, R80, RZ, PT;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    @P0 BRA #label(chain_loop);[7:7:{}:5:1]",
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R30,R31};[0:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R26,R27};[1:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x10], {R40,R41};[2:7:{}:1:0]",
        "    EXIT;[7:7:{0,1,2}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(name: str, mode: str, gap: int, count: int,
        loops: int) -> tuple[float, tuple[int, int]]:
    reset_context()
    mod = CudaModule(assemble(source(name, mode, gap, count, loops),
                              check_deps=False))
    out = mod.devmem_alloc(64)
    try:
        mod.device_write(out, bytes(64))
        mod.launch("i2u", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        a, b, r40, r41 = struct.unpack("<QQII", mod.device_read(out, 24))
        return (((b - a) & ((1 << 64) - 1)) / (count * loops),
                (r40, r41))
    finally:
        mod.devmem_free(out)


def expected_dep(name: str, steps: int) -> tuple[int, int] | None:
    """Bit-exact recurrence used by the dependent chain."""
    if name == "MOV":
        return (0, 0)
    if name in ("IADD", "IADD3", "IMAD"):
        return (steps & 0xFFFFFFFF, (steps - 1) & 0xFFFFFFFF)
    if name == "IMAD.WIDE":
        return (steps & 0xFFFFFFFF, 0)
    if name == "IMAD.HI":
        return (0xFFFFFFFF, steps & 0xFFFFFFFF)
    if name in ("FADD", "FFMA"):
        def f32_bits(x: float) -> int:
            return struct.unpack("<I", struct.pack("<f", x))[0]
        return (f32_bits(float(steps)), f32_bits(float(steps - 1)))
    if name == "HADD2":
        def hbits(x: float) -> int:
            return struct.unpack("<H", struct.pack("<e", x))[0]
        a, b = hbits(float(steps)), hbits(float(steps - 1))
        return (a | (a << 16), b | (b << 16))
    # The current LOP3 LUT control is timing-only, not a strong recurrence.
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--op", action="append", choices=tuple(OPS))
    ap.add_argument("--gap", action="append", type=int,
                    help="override; may be repeated (default: safe_gap and neighbors)")
    ap.add_argument("--count", type=int, default=64,
                    help="unrolled operations per loop iteration (even)")
    ap.add_argument("--loops", type=int, default=64)
    ap.add_argument("--reps", type=int, default=5)
    ns = ap.parse_args()
    print("op       pipe        gap    dependent      independent     nop")
    for name in ns.op or list(OPS):
        op = OPS[name]
        gaps = ns.gap or sorted({max(1, op.safe_gap - 1), op.safe_gap,
                                 op.safe_gap + 1, op.safe_gap + 2})
        for gap in gaps:
            vals = {}
            for mode in ("dep", "ind", "nop"):
                samples = [run(name, mode, gap, ns.count, ns.loops)
                           for _ in range(ns.reps)]
                clocks = [x[0] for x in samples]
                vals[mode] = (statistics.mean(clocks),
                              statistics.pstdev(clocks),
                              {x[1] for x in samples})
            dep_values = "/".join(
                f"{a:08x}:{b:08x}" for a, b in sorted(vals["dep"][2]))
            expected = expected_dep(name, ns.count * ns.loops)
            if expected is None:
                verdict = "unchecked"
            else:
                verdict = "OK" if vals["dep"][2] == {expected} else "BAD"
            print(f"{name:8} {op.pipe:11} {gap:3d}  "
                  f"{vals['dep'][0]:8.3f}±{vals['dep'][1]:.3f}  "
                  f"{vals['ind'][0]:8.3f}±{vals['ind'][1]:.3f}  "
                  f"{vals['nop'][0]:8.3f}±{vals['nop'][1]:.3f}  "
                  f"dep={dep_values} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
