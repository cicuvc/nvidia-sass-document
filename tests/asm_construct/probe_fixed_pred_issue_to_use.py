#!/usr/bin/env python3
"""Steady issue/use calibration for the local fixed-predicate path."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


def source(mode: str, gap: int, count: int, loops: int) -> str:
    if mode == "dep":
        # LUT 0x96 is xor3: P0 xor PT xor !PT = !P0.
        body = "PLOP3.LUT P0, PT, P0, PT, !PT, 0x96"
    elif mode == "ind":
        body = "PLOP3.LUT P0, PT, PT, PT, PT, 0xff"
    elif mode == "nop":
        body = "NOP"
    else:
        raise ValueError(mode)
    lines = [
        "#fn pi2u(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        f"    MOV32I R80, 0x{loops:x};[7:7:{{0}}:8:1]",
        "    ISETP.F P0, RZ, RZ;[7:7:{}:15:1]",
        "    NOP;[7:7:{}:15:1]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    #def_label(pred_loop)",
    ]
    lines += [f"    {body};[7:7:{{}}:{gap}:1]" for _ in range(count)]
    lines += [
        "    IADD32I R80, PT, R80, -0x1;[7:7:{}:4:1]",
        "    ISETP.NE.AND P2, PT, R80, RZ, PT;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    @P2 BRA #label(pred_loop);[7:7:{}:5:1]",
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    P2R R40, PR, RZ, 0x1;[7:7:{}:8:1]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R30,R31};[0:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R26,R27};[1:7:{}:1:0]",
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R40;[2:7:{}:1:0]",
        "    EXIT;[7:7:{0,1,2}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(mode: str, gap: int, count: int, loops: int) -> tuple[float, int]:
    reset_context()
    mod = CudaModule(assemble(source(mode, gap, count, loops),
                              check_deps=False))
    out = mod.devmem_alloc(64)
    try:
        mod.device_write(out, bytes(64))
        mod.launch("pi2u", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        a, b, pred = struct.unpack("<QQI", mod.device_read(out, 20))
        return (((b - a) & ((1 << 64) - 1)) / (count * loops), pred & 1)
    finally:
        mod.devmem_free(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", action="append", type=int)
    ap.add_argument("--count", type=int, default=63)
    ap.add_argument("--loops", type=int, default=65)
    ap.add_argument("--reps", type=int, default=3)
    ns = ap.parse_args()
    expected = (ns.count * ns.loops) & 1
    print("gap    dependent      independent     nop       P0")
    for gap in ns.gap or range(1, 14):
        vals = {}
        for mode in ("dep", "ind", "nop"):
            samples = [run(mode, gap, ns.count, ns.loops)
                       for _ in range(ns.reps)]
            clocks = [x[0] for x in samples]
            vals[mode] = (statistics.mean(clocks), statistics.pstdev(clocks),
                          {x[1] for x in samples})
        verdict = "OK" if vals["dep"][2] == {expected} else "BAD"
        print(f"{gap:3d}  {vals['dep'][0]:8.3f}±{vals['dep'][1]:.3f}  "
              f"{vals['ind'][0]:8.3f}±{vals['ind'][1]:.3f}  "
              f"{vals['nop'][0]:8.3f}±{vals['nop'][1]:.3f}  "
              f"{sorted(vals['dep'][2])} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
