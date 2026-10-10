#!/usr/bin/env python3
"""B200 IMAD.WIDE service/RAW timing under logical-lane masks."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


MASKS = {
    "all": (None, 0),
    "lo16": ("ISETP.LT.U32.AND P1, PT, R0, 0x10, PT", 0),
    "hi16": ("ISETP.GE.U32.AND P1, PT, R0, 0x10, PT", 16),
    "lane0": ("ISETP.EQ.U32.AND P1, PT, R0, RZ, PT", 0),
    "lane16": ("ISETP.EQ.U32.AND P1, PT, R0, 0x10, PT", 16),
}


def source(mask: str, dependent: bool, gap: int,
           count: int, loops: int, layout: str = "alternating") -> str:
    pred_setup, _ = MASKS[mask]
    guard = "" if pred_setup is None else "@P1 "
    lines = [
        "#fn wide_mask(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
        "    S2R R0, SR_TID.X;[2:7:{}:1:0]",
        "    IMAD.WIDE.U32 {R8,R9}, PT, R0, 0x20, {R6,R7};"
        "[7:7:{1,2}:8:1]",
    ]
    if pred_setup is not None:
        lines.append(f"    {pred_setup};[7:7:{{}}:13:1]")
    # Keep predicate production far outside the effective-guard window.
    lines += [
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    MOV32I R24, 0x1;[7:7:{0,1}:8:1]",
        "    MOV32I R27, 0x1;[7:7:{}:8:1]",
        "    MOV32I R28, 0x1;[7:7:{}:8:1]",
        "    MOV32I R29, 0x0;[7:7:{}:8:1]",
        "    MOV32I R40, 0x0;[7:7:{}:8:1]",
        "    MOV32I R41, 0x0;[7:7:{}:8:1]",
        "    MOV32I R42, 0x0;[7:7:{}:8:1]",
        "    MOV32I R43, 0x0;[7:7:{}:8:1]",
        f"    MOV32I R80, 0x{loops:x};[7:7:{{}}:8:1]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    #def_label(chain_loop)",
    ]

    for i in range(count):
        if dependent:
            if layout == "linear":
                s = None if i == 0 else 40 + 2 * (i - 1)
                d = 40 + 2 * i
            else:
                s, d = ((40, 42) if i % 2 == 0 else (42, 40))
        else:
            s, d = 24, 40 + 2 * (i % 20)
        src = "RZ" if s is None else f"R{s}"
        lines.append(
            f"    {guard}IMAD.WIDE.U32 {{R{d},R{d+1}}}, PT, {src}, R27, "
            f"{{R28,R29}};[7:7:{{}}:{gap}:0]"
        )

    result = 40 + 2 * (count - 1) if dependent and layout == "linear" else 40

    lines += [
        "    IADD32I R80, PT, R80, -0x1;[7:7:{}:4:1]",
        "    ISETP.NE.AND P0, PT, R80, RZ, PT;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    @P0 BRA #label(chain_loop);[7:7:{}:5:1]",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64 desc[{UR4,UR5}][{R8,R9}], {R30,R31};[0:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R8,R9}+0x8], {R32,R33};[1:7:{}:1:0]",
        f"    STG.E.64 desc[{{UR4,UR5}}][{{R8,R9}}+0x10], "
        f"{{R{result},R{result+1}}};[2:7:{{}}:1:0]",
        "    EXIT;[7:7:{0,1,2}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(mask: str, dependent: bool, gap: int,
        count: int, loops: int,
        layout: str = "alternating") -> tuple[float, tuple[int, int]]:
    reset_context()
    mod = CudaModule(assemble(source(mask, dependent, gap, count, loops, layout),
                              check_deps=False))
    out = mod.devmem_alloc(32 * 32)
    try:
        mod.device_write(out, bytes(32 * 32))
        mod.launch("wide_mask", grid=(1,), block=(32,), args=[out])
        mod.synchronize()
        store_lane = MASKS[mask][1]
        lane_data = mod.device_read(out, 32 * 32)[32 * store_lane:]
        begin, end, lo, hi = struct.unpack("<QQII", lane_data[:24])
        clocks = ((end - begin) & ((1 << 64) - 1)) / (count * loops)
        return clocks, (lo, hi)
    finally:
        mod.devmem_free(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask", action="append", choices=tuple(MASKS))
    ap.add_argument("--gap", type=int, default=1)
    ap.add_argument("--count", type=int, default=128)
    ap.add_argument("--loops", type=int, default=32)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--layout", choices=("alternating", "linear"),
                    default="alternating")
    ns = ap.parse_args()
    if ns.layout == "linear" and (ns.loops != 1 or ns.count > 20):
        ap.error("linear layout requires --loops 1 and --count <= 20")
    expected = (ns.count * ns.loops, 0)
    print("mask    dependent       independent     value verdict")
    for mask in ns.mask or MASKS:
        dep = [run(mask, True, ns.gap, ns.count, ns.loops, ns.layout)
               for _ in range(ns.reps)]
        ind = [run(mask, False, ns.gap, ns.count, ns.loops, ns.layout)
               for _ in range(ns.reps)]
        dep_t = [x[0] for x in dep]
        ind_t = [x[0] for x in ind]
        values = {x[1] for x in dep}
        value_text = "/".join(f"{lo:08x}:{hi:08x}"
                              for lo, hi in sorted(values))
        print(f"{mask:7} {statistics.mean(dep_t):8.3f}±"
              f"{statistics.pstdev(dep_t):.3f}  "
              f"{statistics.mean(ind_t):8.3f}±"
              f"{statistics.pstdev(ind_t):.3f}  {value_text} "
              f"{'OK' if values == {expected} else 'BAD'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
