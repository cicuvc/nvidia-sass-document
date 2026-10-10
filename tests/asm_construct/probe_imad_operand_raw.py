#!/usr/bin/env python3
"""B200 ordinary 32-bit IMAD RAW recurrence for Ra/Rb/Rc operand slots."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


def imad(operand: str, dst: int, src: int) -> str:
    if operand == "ra":
        return f"IMAD R{dst}, R{src}, R27, R28"
    if operand == "rb":
        return f"IMAD R{dst}, R27, R{src}, R28"
    return f"IMAD R{dst}, R27, R28, R{src}"


def source(operand: str, gap: int, yield_bit: int,
           count: int, loops: int) -> str:
    lines = [
        "#fn imad_raw(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        "    MOV32I R27, 0x1;[7:7:{0}:8:1]",
        "    MOV32I R28, 0x1;[7:7:{}:8:1]",
        "    MOV32I R40, 0x0;[7:7:{}:8:1]",
        "    MOV32I R41, 0x40000000;[7:7:{}:8:1]",
        f"    MOV32I R80, 0x{loops:x};[7:7:{{}}:8:1]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    #def_label(chain_loop)",
    ]
    for i in range(count):
        src, dst = ((40, 41) if i % 2 == 0 else (41, 40))
        lines.append(f"    {imad(operand, dst, src)};"
                     f"[7:7:{{}}:{gap}:{yield_bit}]")
    lines += [
        "    IADD32I R80, PT, R80, -0x1;[7:7:{}:4:1]",
        "    ISETP.NE.AND P0, PT, R80, RZ, PT;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    @P0 BRA #label(chain_loop);[7:7:{}:5:1]",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R30,R31};[0:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R32,R33};[1:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x10], {R40,R41};[2:7:{}:1:0]",
        "    EXIT;[7:7:{0,1,2}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(operand: str, gap: int, yield_bit: int,
        count: int, loops: int) -> tuple[float, tuple[int, int]]:
    reset_context()
    mod = CudaModule(assemble(source(operand, gap, yield_bit, count, loops),
                              check_deps=False))
    out = mod.devmem_alloc(32)
    try:
        mod.device_write(out, bytes(32))
        mod.launch("imad_raw", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        begin, end, r40, r41 = struct.unpack("<QQII", mod.device_read(out, 24))
        clocks = ((end - begin) & ((1 << 64) - 1)) / (count * loops)
        return clocks, (r40, r41)
    finally:
        mod.devmem_free(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--operand", action="append", choices=("ra", "rb", "rc"))
    ap.add_argument("--gap", action="append", type=int)
    ap.add_argument("--yield-bit", action="append", type=int, choices=(0, 1))
    ap.add_argument("--count", type=int, default=128)
    ap.add_argument("--loops", type=int, default=32)
    ap.add_argument("--reps", type=int, default=3)
    ns = ap.parse_args()
    steps = ns.count * ns.loops
    expected = (steps, steps - 1)
    print("operand gap y clocks/op       value verdict")
    for operand in ns.operand or ("ra", "rb", "rc"):
        for yield_bit in ns.yield_bit or (0, 1):
            for gap in ns.gap or range(1, 6):
                samples = [run(operand, gap, yield_bit, ns.count, ns.loops)
                           for _ in range(ns.reps)]
                clocks = [x[0] for x in samples]
                values = {x[1] for x in samples}
                value_text = "/".join(f"{a:08x}:{b:08x}"
                                      for a, b in sorted(values))
                print(f"{operand:7} {gap:3d} {yield_bit:d} "
                      f"{statistics.mean(clocks):8.3f}±"
                      f"{statistics.pstdev(clocks):.3f}  {value_text} "
                      f"{'OK' if values == {expected} else 'BAD'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
