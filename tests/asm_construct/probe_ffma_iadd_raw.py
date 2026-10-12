#!/usr/bin/env python3
"""B200 FFMA -> IADD arithmetic RAW boundary across FMA Lite and ALU Lite."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


FRESH = 0x3F800001  # integer +1 applied to the bits of FP32 1.0
POISON_PLUS_ONE = 0x40000001


def source(gap: int, yield_bit: int, copies: int) -> str:
    lines = [
        "#fn ffma_iadd(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        # 0.5 * 0.5 + 0.75 = 1.0; the result differs from every source.
        "    MOV32I R24, 0x3f000000;[7:7:{0}:8:1]",
        "    MOV32I R25, 0x3f000000;[7:7:{}:8:1]",
        "    MOV32I R26, 0x3f400000;[7:7:{}:8:1]",
        "    MOV32I R27, 0x00000001;[7:7:{}:8:1]",
    ]

    for i in range(copies):
        prod = 40 + 2 * i
        cons = prod + 1
        wait = "{0}" if i else "{}"
        lines += [
            f"    MOV32I R{prod}, 0x40000000;[7:7:{wait}:8:1]",
            f"    MOV32I R{cons}, 0xdeadbeef;[7:7:{{}}:8:1]",
            f"    FFMA R{prod}, R24, R25, R26;[7:7:{{}}:{gap}:{yield_bit}]",
            f"    IADD R{cons}, PT, R{prod}, R27;[7:7:{{}}:8:1]",
            "    NOP;[7:7:{}:8:1]",
            "    NOP;[7:7:{}:8:1]",
            f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{4*i:x}], "
            f"R{cons};[0:7:{{}}:1:0]",
        ]

    lines += ["    EXIT;[7:7:{0}:5:0]", "}"]
    return "\n".join(lines)


def run(gap: int, yield_bit: int, copies: int) -> tuple[int, ...]:
    reset_context()
    mod = CudaModule(assemble(source(gap, yield_bit, copies),
                              check_deps=False))
    out = mod.devmem_alloc(4 * copies)
    try:
        mod.device_write(out, bytes(4 * copies))
        mod.launch("ffma_iadd", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        return struct.unpack(f"<{copies}I", mod.device_read(out, 4 * copies))
    finally:
        mod.devmem_free(out)


def classify(values: tuple[int, ...]) -> str:
    return "".join("F" if x == FRESH else
                   "S" if x == POISON_PLUS_ONE else "?" for x in values)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", action="append", type=int)
    ap.add_argument("--yield-bit", action="append", type=int, choices=(0, 1))
    ap.add_argument("--copies", type=int, default=16)
    ap.add_argument("--reps", type=int, default=5)
    ns = ap.parse_args()
    if ns.copies < 1 or 40 + 2 * ns.copies > 80:
        ap.error("--copies must be in 1..20")

    print("gap y pattern(s)                         permanent")
    for yield_bit in ns.yield_bit or (0, 1):
        for gap in ns.gap or range(1, 9):
            samples = [run(gap, yield_bit, ns.copies)
                       for _ in range(ns.reps)]
            patterns = sorted({classify(x) for x in samples})
            raw = sorted({v for sample in samples for v in sample
                          if v not in (FRESH, POISON_PLUS_ONE)})
            ok = all(x == FRESH for sample in samples for x in sample)
            extra = "" if not raw else " raw=" + "/".join(
                f"{x:08x}" for x in raw)
            print(f"{gap:3d} {yield_bit:d} {'/'.join(patterns):32} "
                  f"{'YES' if ok else 'no ':9}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
