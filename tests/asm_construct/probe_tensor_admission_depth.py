#!/usr/bin/env python3
"""Measure effective GB202 tensor admission credits with short MMA bursts.

The final CS2R has no dependency on the MMA destinations.  If tensor ops can
enter a decoded-op FIFO faster than the tensor backend drains them, T(N) has
an initial one-cycle slope followed by the 16/32-cycle backend slope.  P6 is
architecturally false, but prior NCU probes show that tensor reservation and
subpipe occupancy survive all-off predication.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def mma(op: str, index: int, active: bool) -> str:
    if op == "hmma_imma":
        op = "hmma" if index % 2 == 0 else "imma"
    elif op == "imma_hmma":
        op = "imma" if index % 2 == 0 else "hmma"
    rd = 32 + 4 * (index % 47)
    dst = f"{{R{rd},R{rd+1},R{rd+2},R{rd+3}}}"
    guard = "" if active else "@P6 "
    if op == "hmma":
        body = (f"HMMA.16816.F32.BF16 {dst}, {{R16,R17,R18,R19}}, "
                "{R20,R21}, {R24,R25,R26,R27}")
    elif op == "qmma":
        body = (f"QMMA.16832.F32.E4M3.E4M3 {dst}, "
                "{R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27}")
    elif op == "imma":
        body = (f"IMMA.16816.U8.U8 {dst}, {{R16,R17}}.ROW, R20.COL, "
                "{R24,R25,R26,R27}, !UPT")
    else:
        raise ValueError(op)
    return f"    {guard}{body};[7:7:{{}}:1:0]"


def source(op: str, n: int, active: bool) -> str:
    lines = [
        "#fn tensorburst(out<8>) {",
        "    #pragma MAXREG_COUNT(224)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    MOV32I R16, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R17, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R18, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R19, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R20, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R21, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R24, 0;[7:7:{}:5:1]",
        "    MOV32I R25, 0;[7:7:{}:5:1]",
        "    MOV32I R26, 0;[7:7:{}:5:1]",
        "    MOV32I R27, 0;[7:7:{}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    CS2R {R8,R9}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += [mma(op, i, active) for i in range(n)]
    lines += [
        "    CS2R {R10,R11}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R8,R9};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R10,R11};[7:0:{}:8:0]",
    ]
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(64)]
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def parse_counts(text: str) -> list[int]:
    if "-" in text:
        lo, hi = (int(x) for x in text.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(x) for x in text.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--op", choices=("hmma", "qmma", "imma",
                                     "hmma_imma", "imma_hmma"),
                    default="hmma")
    ap.add_argument("--counts", default="0-24")
    ap.add_argument("--reps", type=int, default=11)
    ap.add_argument("--active", action="store_true")
    ns = ap.parse_args()
    counts = parse_counts(ns.counts)
    if not counts or min(counts) < 0 or max(counts) > 47 or ns.reps <= 0:
        ap.error("counts must be in 0..47 and reps positive")

    print(f"op={ns.op} active={ns.active}")
    print("N span_median min max delta")
    previous = None
    for n in counts:
        mod = CudaModule(assemble(source(ns.op, n, ns.active),
                                  check_deps=True))
        out = mod.devmem_alloc(16)
        vals = []
        try:
            for _ in range(ns.reps + 1):
                mod.launch("tensorburst", grid=(1,), block=(32,), args=[out])
                mod.synchronize()
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append(t1 - t0)
        finally:
            mod.devmem_free(out)
        kept = vals[1:]
        med = statistics.median(kept)
        delta = "-" if previous is None else f"{med - previous:g}"
        print(f"{n:2d} {med:6g} {min(kept):3d} {max(kept):3d} {delta}")
        previous = med
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
