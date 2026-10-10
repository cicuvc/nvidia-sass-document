#!/usr/bin/env python3
"""Measure how many early dependent FMA-Lite requests B200 can absorb.

Each case starts with a fully ready accumulator, emits a finite burst of N
Rd==Ra operations at the requested control-code gap, then uses the long loop
tail to drain the pipe.  Repeating the finite burst makes a one-off holding
slot visible without allowing backlog to grow across loop iterations.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


OPS = {
    "FADD": (
        ("MOV32I R90, 0x3f800000",),
        "MOV32I R40, 0x00000000",
        "FADD R{d}, R{s}, R90",
    ),
    "FFMA": (
        ("MOV32I R90, 0x3f800000", "MOV32I R91, 0x3f800000"),
        "MOV32I R40, 0x00000000",
        "FFMA R{d}, R{s}, R90, R91",
    ),
    "FMUL": (
        ("MOV32I R90, 0x3f802000",),
        "MOV32I R40, 0x3f800000",
        "FMUL R{d}, R{s}, R90",
    ),
}


def source(op_name: str, gap: int, yield_bit: int,
           max_burst: int, loops: int, layout: str) -> str:
    setup, init, inst_template = OPS[op_name]
    lines = [
        "#fn early_burst(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
    ]
    lines += [f"    {x};[7:7:{{0}}:8:1]" for x in setup]

    bursts = list(range(2, max_burst + 1, 2))
    for case, burst in enumerate(bursts):
        wait = "{0}" if case else "{}"
        lines += [
            f"    {init};[7:7:{wait}:8:1]",
            "    MOV32I R41, 0x40000000;[7:7:{}:8:1]",
            f"    MOV32I R80, 0x{loops:x};[7:7:{{}}:8:1]",
            f"    #def_label(loop_{burst})",
        ]
        if layout == "linear":
            lines += [f"    MOV32I R{reg}, 0x40000000;[7:7:{{}}:8:1]"
                      for reg in range(42, 41 + burst)]
        for i in range(burst):
            if layout == "self":
                d = s = 40
            elif layout == "linear":
                s, d = 40 + i, 41 + i
            else:
                s, d = ((40, 41) if i % 2 == 0 else (41, 40))
            inst = inst_template.format(d=d, s=s)
            # The final operation is followed by a deliberate drain rather
            # than another early request.  Even alternating bursts naturally
            # leave the live accumulator in R40 without an extra ALU copy.
            inst_gap = 4 if i == burst - 1 else gap
            lines.append(f"    {inst};[7:7:{{}}:{inst_gap}:{yield_bit}]")
        lines += [
            "    IADD32I R80, PT, R80, -0x1;[7:7:{}:4:1]",
            "    ISETP.NE.AND P0, PT, R80, RZ, PT;[7:7:{}:8:1]",
            "    NOP;[7:7:{}:8:1]",
            "    NOP;[7:7:{}:8:1]",
            f"    @P0 BRA #label(loop_{burst});[7:7:{{}}:5:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*case:x}], "
            f"R{40 + burst if layout == 'linear' else 40};[0:7:{{}}:1:0]",
        ]

    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def expected(op_name: str, steps: int) -> int:
    if op_name in ("FADD", "FFMA"):
        return bits(float(steps))
    value = f32(1.0)
    factor = struct.unpack("<f", struct.pack("<I", 0x3F802000))[0]
    for _ in range(steps):
        value = f32(value * factor)
    return bits(value)


def run(op_name: str, gap: int, yield_bit: int,
        max_burst: int, loops: int, layout: str) -> tuple[int, ...]:
    reset_context()
    cubin = assemble(source(op_name, gap, yield_bit, max_burst, loops, layout),
                     check_deps=False)
    mod = CudaModule(cubin)
    ncases = max_burst // 2
    out = mod.devmem_alloc(4 * ncases)
    try:
        mod.device_write(out, bytes(4 * ncases))
        mod.launch("early_burst", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        return struct.unpack(f"<{ncases}I", mod.device_read(out, 4 * ncases))
    finally:
        mod.devmem_free(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--op", action="append", choices=tuple(OPS))
    ap.add_argument("--gap", action="append", type=int, default=None)
    ap.add_argument("--yield-bit", action="append", type=int, choices=(0, 1))
    ap.add_argument("--max-burst", type=int, default=16)
    ap.add_argument("--loops", type=int, default=128)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--layout", choices=("linear", "alternate", "self"),
                    default="alternate")
    ns = ap.parse_args()
    if ns.layout == "linear" and ns.loops != 1:
        ap.error("--layout linear requires --loops 1")

    for op_name in ns.op or OPS:
        for yield_bit in ns.yield_bit or (0, 1):
            for gap in ns.gap or (2, 3, 4):
                samples = [run(op_name, gap, yield_bit, ns.max_burst,
                               ns.loops, ns.layout) for _ in range(ns.reps)]
                print(f"\n{op_name} gap={gap} yield={yield_bit} "
                      f"layout={ns.layout} loops={ns.loops}")
                first_bad = None
                for case, burst in enumerate(range(2, ns.max_burst + 1, 2)):
                    want = expected(op_name, burst * ns.loops)
                    got = tuple(x[case] for x in samples)
                    ok = all(x == want for x in got)
                    if not ok and first_bad is None:
                        first_bad = burst
                    observed = "/".join(f"{x:08x}" for x in sorted(set(got)))
                    print(f"  N={burst:2d} early={burst-1:2d} "
                          f"got={observed} want={want:08x} "
                          f"{'OK' if ok else 'BAD'}")
                print("  first_bad=" + (str(first_bad) if first_bad else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
