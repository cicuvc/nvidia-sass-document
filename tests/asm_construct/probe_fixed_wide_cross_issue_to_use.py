#!/usr/bin/env python3
"""Measure IMAD.WIDE low/high result use by ordinary fixed-pipe leaves.

The WIDE -> consumer edge uses the requested scheduling gap.  The reverse
consumer -> WIDE edge is deliberately padded, so correctness locates the
forward edge rather than the full recurrence round trip.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


CONSUMERS = {
    "IADD": "IADD R{dst}, PT, R{src}, R26",
    "IADD3": "IADD3 R{dst}, R{src}, R26, RZ",
    "LEA": "LEA R{dst}, R{src}, R26, 0x0",
    "IMAD": "IMAD R{dst}, R{src}, R27, R26",
    "FADD": "FADD R{dst}, R{src}, R26",
    "HADD2": "HADD2 R{dst}, R{src}, R26",
}


def source(half: str, consumer: str, gap: int, count: int,
           loops: int, independent: bool) -> str:
    # Integer low: WIDE(x * 1 + 7) low=x+7; consumer adds 1.  The non-zero
    # Rc is essential: ALU Heavy can otherwise mistake the early Ra payload
    # for the architecturally identical final low result.
    # High: WIDE(0 + {0,x}) high=x.  Feeding x through Rc.high keeps both
    # integer and FP32 consumers on an exact +1 recurrence.
    is_fp32 = consumer == "FADD"
    is_fp16 = consumer == "HADD2"
    is_integer = not (is_fp32 or is_fp16)
    init = 0x3C003C00 if is_fp16 else (0x3F800000 if is_fp32 else 1)
    mul = 1 if half == "low" else 0
    add = init
    src = 40 if half == "low" else 41
    state = 31 if half == "high" else 42
    consume_src = 44 if independent else src
    inst = CONSUMERS[consumer].format(src=consume_src, dst=state)
    wide_ra = "RZ" if half == "high" else f"R{state}"
    low_bias = 7 if is_integer else (0x00010001 if is_fp16 else 1)

    lines = [
        "#fn wide_cross(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        f"    MOV32I R44, 0x{init:x};"
        "[7:7:{0}:8:1]",
        f"    MOV32I R26, 0x{add:x};[7:7:{{}}:8:1]",
        "    MOV32I R27, 0x1;[7:7:{}:8:1]",
        f"    MOV32I R28, 0x{mul:x};[7:7:{{}}:8:1]",
        f"    MOV32I R30, 0x{low_bias if half == 'low' else 0:x};"
        "[7:7:{}:8:1]",
        "    MOV32I R31, 0x0;[7:7:{}:8:1]",
        f"    MOV32I R{state}, 0x{init:x};"
        "[7:7:{}:8:1]",
        f"    MOV32I R80, 0x{loops:x};[7:7:{{}}:8:1]",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    #def_label(chain_loop)",
    ]
    for _ in range(count):
        lines += [
            # The next consumer is the edge under test.
            f"    IMAD.WIDE.U32 {{R40,R41}}, PT, {wide_ra}, R28, "
            f"{{R30,R31}};[7:7:{{}}:{gap}:1]",
            # Eight nominal cycles make the reverse edge unambiguously safe.
            f"    {inst};[7:7:{{}}:8:1]",
        ]
    lines += [
        "    IADD32I R80, PT, R80, -0x1;[7:7:{}:4:1]",
        "    ISETP.NE.AND P0, PT, R80, RZ, PT;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    @P0 BRA #label(chain_loop);[7:7:{}:5:1]",
        "    CS2R {R34,R35}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R32,R33};[0:7:{}:1:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R34,R35};[1:7:{}:1:0]",
        f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x10], R{state};"
        "[2:7:{}:1:0]",
        "    EXIT;[7:7:{0,1,2}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(half: str, consumer: str, gap: int, count: int,
        loops: int, independent: bool) -> tuple[float, int]:
    reset_context()
    cubin = assemble(source(half, consumer, gap, count, loops, independent),
                     check_deps=False)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(32)
    try:
        mod.device_write(out, bytes(32))
        mod.launch("wide_cross", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        begin, end, value = struct.unpack("<QQI", mod.device_read(out, 20))
        clocks = ((end - begin) & ((1 << 64) - 1)) / (count * loops)
        return clocks, value
    finally:
        mod.devmem_free(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", action="append", choices=("low", "high"))
    ap.add_argument("--consumer", action="append", choices=tuple(CONSUMERS))
    ap.add_argument("--gap", action="append", type=int)
    ap.add_argument("--count", type=int, default=32)
    ap.add_argument("--loops", type=int, default=32)
    ap.add_argument("--reps", type=int, default=3)
    ns = ap.parse_args()
    total = ns.count * ns.loops
    print("half consumer gap dependent       independent     value verdict")
    for half in ns.half or ("low", "high"):
        for consumer in ns.consumer or tuple(CONSUMERS):
            for gap in ns.gap or range(1, 9):
                samples = [run(half, consumer, gap, ns.count, ns.loops, False)
                           for _ in range(ns.reps)]
                controls = [run(half, consumer, gap, ns.count, ns.loops, True)
                            for _ in range(ns.reps)]
                dep_t = [x[0] for x in samples]
                ind_t = [x[0] for x in controls]
                values = {x[1] for x in samples}
                if consumer == "FADD":
                    expected = 0x3F800000
                    for _ in range(total):
                        if half == "low":
                            expected = (expected + 1) & 0xFFFFFFFF
                        x = struct.unpack("<f", struct.pack("<I", expected))[0]
                        expected = struct.unpack("<I", struct.pack("<f", x + 1.0))[0]
                elif consumer == "HADD2":
                    expected = 0x3C003C00
                    for _ in range(total):
                        if half == "low":
                            expected = (expected + 0x00010001) & 0xFFFFFFFF
                        lo = struct.unpack("<e", struct.pack("<H", expected & 0xFFFF))[0]
                        hi = struct.unpack("<e", struct.pack("<H", expected >> 16))[0]
                        lob = struct.unpack("<H", struct.pack("<e", lo + 1.0))[0]
                        hib = struct.unpack("<H", struct.pack("<e", hi + 1.0))[0]
                        expected = lob | (hib << 16)
                else:
                    expected = 1 + total * (8 if half == "low" else 1)
                verdict = "OK" if values == {expected} else "BAD"
                value_text = "/".join(f"{x:08x}" for x in sorted(values))
                print(f"{half:4} {consumer:8} {gap:3d} "
                      f"{statistics.mean(dep_t):8.3f}±{statistics.pstdev(dep_t):.3f} "
                      f"{statistics.mean(ind_t):8.3f}±{statistics.pstdev(ind_t):.3f} "
                      f"{value_text} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
