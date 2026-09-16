#!/usr/bin/env python3
"""Phase-safe IMAD.HI result -> next IMAD.HI Ra dependency probe.

IMAD.HI is signed-only, so a simple monotonic +1 recurrence is unavailable.
Each loop resets a short, non-converged nonlinear chain and checks its final
value.  Repeating that block exposes changing issue phases without allowing
the recurrence to settle at a fixed point and hide stale reads.
"""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


B = 0x9ABCDEF0
RC = 0x1234567890ABCDEF
INITIAL = 1


def step(x: int) -> int:
    product = ctypes.c_int32(x).value * ctypes.c_int32(B).value
    return (((product + RC) & ((1 << 64) - 1)) >> 32) & 0xFFFFFFFF


def expected(count: int) -> int:
    x = INITIAL
    for _ in range(count):
        x = step(x)
    return x


def source(gap: int, count: int, loops: int) -> str:
    final = 40 if count % 2 == 0 else 41
    want = expected(count)
    lines = [
        "#fn hi_ra(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]",
        f"    MOV32I R26, 0x{B:x};[7:7:{{0}}:8:1]",
        f"    MOV32I R28, 0x{RC & 0xffffffff:x};[7:7:{{}}:8:1]",
        f"    MOV32I R29, 0x{RC >> 32:x};[7:7:{{}}:8:1]",
        f"    MOV32I R52, 0x{want:x};[7:7:{{}}:8:1]",
        "    MOV32I R50, 0x0;[7:7:{}:8:1]",
        f"    MOV32I R80, 0x{loops:x};[7:7:{{}}:8:1]",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    #def_label(chain_loop)",
        "    MOV32I R40, 0x1;[7:7:{}:8:1]",
        "    MOV32I R41, 0xdeadbeef;[7:7:{}:8:1]",
    ]
    for i in range(count):
        s, d = ((40, 41) if i % 2 == 0 else (41, 40))
        lines.append(
            f"    IMAD.HI R{d}, PT, R{s}, R26, {{R28,R29}};"
            f"[7:7:{{}}:{gap}:1]"
        )
    lines += [
        # Separate result readiness from the validation path.
        "    NOP;[7:7:{}:8:1]",
        f"    ISETP.EQ.AND P1, PT, R{final}, R52, PT;[7:7:{{}}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    @!P1 IADD32I R50, PT, R50, 0x1;[7:7:{}:4:1]",
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
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x10], R50;[2:7:{}:1:0]",
        "    EXIT;[7:7:{0,1,2}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(gap: int, count: int, loops: int) -> tuple[float, int]:
    reset_context()
    mod = CudaModule(assemble(source(gap, count, loops), check_deps=False))
    out = mod.devmem_alloc(32)
    try:
        mod.device_write(out, bytes(32))
        mod.launch("hi_ra", grid=(1,), block=(1,), args=[out])
        mod.synchronize()
        begin, end, errors = struct.unpack("<QQI", mod.device_read(out, 20))
        clocks = ((end - begin) & ((1 << 64) - 1)) / (count * loops)
        return clocks, errors
    finally:
        mod.devmem_free(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", action="append", type=int)
    ap.add_argument("--count", type=int, default=16)
    ap.add_argument("--loops", type=int, default=64)
    ap.add_argument("--reps", type=int, default=3)
    ns = ap.parse_args()
    print(f"chain expected=0x{expected(ns.count):08x}")
    for gap in ns.gap or range(1, 13):
        samples = [run(gap, ns.count, ns.loops) for _ in range(ns.reps)]
        clocks = sum(x[0] for x in samples) / len(samples)
        errors = sorted({x[1] for x in samples})
        verdict = "OK" if errors == [0] else "BAD"
        print(f"gap={gap:2d} clocks/op={clocks:8.3f} errors={errors} {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
