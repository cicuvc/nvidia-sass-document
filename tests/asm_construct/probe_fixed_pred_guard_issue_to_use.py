#!/usr/bin/env python3
"""Phase-safe fixed-predicate producer -> effective instruction guard sweep."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


CONSUMERS = {
    "mov32i": ("MOV32I R27, 0x1", "MOV32I R51, 0x1"),
    "alulite": ("MOV32I R27, 0x1", "IADD R50, PT, R50, R27"),
    "aluheavy": ("MOV32I R27, 0x1", "IADD3 R50, R50, R27, RZ"),
    "fmalite": ("MOV32I R27, 0x3f800000", "FADD R50, R50, R27"),
    "fmaheavy": ("MOV32I R27, 0x1\n    MOV32I R28, 0x1",
                 "IMAD R50, R50, R27, R28"),
    "packed": ("MOV32I R27, 0x3c003c00", "HADD2 R50, R50, R27"),
}


def source(consumer: str, gap: int, count: int, loops: int) -> str:
    setup, guarded = CONSUMERS[consumer]
    lines = [
        "#fn pguard(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        f"    MOV32I R80, 0x{loops:x};[7:7:{{0}}:8:1]",
        *[f"    {x};[7:7:{{}}:8:1]" for x in setup.split("\n    ")],
        "    MOV32I R50, 0x0;[7:7:{}:8:1]",
        "    ISETP.F P0, RZ, RZ;[7:7:{}:15:1]",
        "    NOP;[7:7:{}:15:1]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    #def_label(guard_loop)",
    ]
    for _ in range(count):
        if consumer == "mov32i":
            lines += [
                "    MOV32I R51, 0x0;[7:7:{}:4:1]",
                f"    PLOP3.LUT P0, PT, P0, PT, !PT, 0x96;[7:7:{{}}:{gap}:1]",
                f"    @P0 {guarded};[7:7:{{}}:12:1]",
                "    IADD3 R50, R50, R51, RZ;[7:7:{}:4:1]",
            ]
        else:
            lines += [
                f"    PLOP3.LUT P0, PT, P0, PT, !PT, 0x96;[7:7:{{}}:{gap}:1]",
                f"    @P0 {guarded};[7:7:{{}}:4:1]",
            ]
    lines += [
        "    IADD32I R80, PT, R80, -0x1;[7:7:{}:4:1]",
        "    ISETP.NE.AND P2, PT, R80, RZ, PT;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    @P2 BRA #label(guard_loop);[7:7:{}:5:1]",
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R30,R31};[0:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R26,R27};[1:7:{}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R50;[2:7:{}:1:0]",
        "    EXIT;[7:7:{0,1,2}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(consumer: str, gap: int, count: int, loops: int) -> tuple[float, int]:
    reset_context()
    mod = CudaModule(assemble(source(consumer, gap, count, loops),
                              check_deps=False))
    out = mod.devmem_alloc(64)
    try:
        mod.device_write(out, bytes(64))
        mod.launch("pguard", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        a, b, value = struct.unpack("<QQI", mod.device_read(out, 20))
        return (((b - a) & ((1 << 64) - 1)) / (count * loops), value)
    finally:
        mod.devmem_free(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", action="append", type=int)
    ap.add_argument("--consumer", action="append", choices=tuple(CONSUMERS))
    ap.add_argument("--count", type=int, default=32)
    ap.add_argument("--loops", type=int, default=32)
    ap.add_argument("--reps", type=int, default=3)
    ns = ap.parse_args()
    total = ns.count * ns.loops
    increments = (total + 1) // 2
    for consumer in ns.consumer or list(CONSUMERS):
        if consumer == "fmalite":
            expected = struct.unpack("<I", struct.pack("<f", float(increments)))[0]
        elif consumer == "packed":
            h = struct.unpack("<H", struct.pack("<e", float(increments)))[0]
            expected = h | (h << 16)
        else:
            expected = increments
        print(f"\n{consumer}: expected 0x{expected:08x}")
        print("gap    clocks/pair    values       verdict")
        for gap in ns.gap or range(1, 15):
            samples = [run(consumer, gap, ns.count, ns.loops)
                       for _ in range(ns.reps)]
            clocks = sum(x[0] for x in samples) / len(samples)
            values = sorted({x[1] for x in samples})
            verdict = "OK" if values == [expected] else "BAD"
            print(f"{gap:3d}    {clocks:8.3f}    "
                  f"{[f'0x{x:08x}' for x in values]!s:14} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
