#!/usr/bin/env python3
"""Sweep a scalar marker write through an HGMMA accumulator RMW window.

This is deliberately an async-proxy data race.  Each warp initializes an
n64 F32 accumulator to 1.0, issues one accumulating HGMMA/QGMMA whose dot
product is 16.0/32.0, waits a swept number of instruction slots, and writes
2.0 to one accumulator word without a DEPBAR.  For HGMMA the eventual value
distinguishes (QGMMA has the analogous 34.0/33.0/2.0 values):

  18.0 = marker committed before the HGMMA old-value read
  17.0 = marker committed after the read but before the HGMMA write
   2.0 = marker committed after the HGMMA write

A stable 17.0 interval bracketed by 18.0 and 2.0 would expose the internal
read-to-write aperture.  Undefined ordering makes negative results weaker
than positive ones; this is a microarchitectural probe, not valid CUDA usage.
"""

from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


BASE = 0x3F800000
MARKER = 0x40000000


def expected(mma: str) -> tuple[int, int, int]:
    # Dot products of 16 BF16 ones or 32 E4M3 ones.
    return ((0x41800000, 0x41880000, 0x41900000) if mma == "hgmma" else
            (0x42000000, 0x42040000, 0x42080000))


def source(target: str, pair: int, delay: int, hstall: int, dstall: int,
           mma: str, qfmt: str,
           marker: bool = True) -> str:
    treg = 24 + 2 * pair + (target == "O")
    acc = "{" + ",".join(f"R{r}" for r in range(24, 56)) + "}"
    data_byte = 0x38 if qfmt == "E4M3" else 0x3C
    data_word = (0x3F803F80 if mma == "hgmma" else
                 data_byte * 0x01010101)
    opcode = ("HGMMA.64x64x16.F32.BF16" if mma == "hgmma" else
              f"QGMMA.64x64x32.F32.{qfmt}.{qfmt}")
    lines = [
        "#fn hgrmwwin(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(16384)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x4, {R2,R3};[7:7:{0,1}:5:1]",
        "    SHF.L.U32 R12, R4, 0x4, RZ;[7:7:{1}:5:1]",
        f"    MOV32I R8, 0x{data_word:08x};[7:7:{{}}:5:1]",
        f"    MOV32I R9, 0x{data_word:08x};[7:7:{{}}:5:1]",
        f"    MOV32I R10, 0x{data_word:08x};[7:7:{{}}:5:1]",
        f"    MOV32I R11, 0x{data_word:08x};[7:7:{{}}:5:1]",
        "    STS.128 [R12], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x1000], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x2000], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x3000], {R8,R9,R10,R11};[7:7:{}:5:1]",
    ]
    lines += [f"    MOV32I R{r}, 0x{BASE:08x};[7:7:{{}}:5:1]"
              for r in range(24, 56)]
    lines += [
        "    UMOV UR4, 0x400040;[7:7:{}:5:1]",
        "    UMOV UR5, 0x0;[7:7:{}:5:1]",
        "    UMOV UR6, 0x4000c0;[7:7:{}:5:1]",
        "    UMOV UR7, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # All 256 threads populate shared memory, then only warpgroup 0 probes.
        # This avoids superposing the two warpgroup scheduling phases.
        "    SHR R13, R4, 0x5;[7:7:{1}:5:1]",
        "    ISETP.LT.U32.AND P0, PT, R13, 0x4, PT;[7:7:{}:13:1]",
        "    @!P0 BRA #label(exit);[7:7:{}:5:1]",
        "    WARPGROUP.ARRIVE;[7:7:{}:5:1]",
        f"    {opcode} {acc}, gdesc[UR4], {acc}, "
        f"UPT, gsb0;[7:7:{{}}:{hstall}:0]",
    ]
    lines += [f"    NOP;[7:7:{{}}:{dstall}:1]" for _ in range(delay)]
    if marker:
        lines += [f"    MOV32I R{treg}, 0x{MARKER:08x};[7:7:{{}}:1:0]"]
    lines += [
        "    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]",
        f"    STG.E.STRONG.GPU [{{R6,R7}}], R{treg};[7:2:{{}}:8:0]",
        "#def_label(exit)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_case(target: str, pair: int, delay: int, hstall: int, dstall: int,
             mma: str, qfmt: str,
             reps: int, marker: bool = True) -> collections.Counter[int]:
    cubin = assemble(source(target, pair, delay, hstall, dstall, mma, qfmt,
                            marker), arch="sm90",
                     check_deps=True)
    mod = CudaModule(cubin)
    # 256 threads are required to populate the complete descriptor-covered
    # shared-memory tiles (in particular B at 0xc00); only the first
    # warpgroup writes results.
    out = mod.devmem_alloc(256 * 4)
    counts: collections.Counter[int] = collections.Counter()
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0xAAAAAAAA, 256)
            mod.launch("hgrmwwin", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            if rep:
                values = struct.unpack("<256I", mod.device_read(out, 256 * 4))
                counts.update(values[:128])
    finally:
        mod.devmem_free(out)
    return counts


def label(counts: collections.Counter[int], mma: str) -> str:
    delta, rmw_base, rmw_marker = expected(mma)
    names = {
        BASE: "B", delta: "D", rmw_base: "base+d",
        MARKER: "M", rmw_marker: "marker+d", 0xAAAAAAAA: "X",
    }
    return "/".join(
        f"{names.get(v, f'?{v:08x}')}:{n}"
        for v, n in counts.most_common()
    )


def parse_delays(text: str) -> list[int]:
    if ":" in text:
        a, b, c = (int(x) for x in text.split(":"))
        return list(range(a, b, c))
    return [int(x) for x in text.split(",") if x]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--delays", default="0:81:1",
                   help="NOP counts as start:stop:step or CSV")
    p.add_argument("--hstall", type=int, choices=range(1, 8), default=4)
    p.add_argument("--mma", choices=("hgmma", "qgmma"), default="hgmma")
    p.add_argument("--qfmt", choices=("E4M3", "E5M2"), default="E4M3")
    p.add_argument("--dstall", type=int, choices=(0, 1), default=1,
                   help="stall field on delay NOPs; 1 is the calibrated clock ruler")
    p.add_argument("--reps", type=int, default=20)
    p.add_argument("--target", choices=("E", "O", "both"), default="both")
    p.add_argument("--pair", type=int, choices=range(16), default=15,
                   help="n64 accumulator pair: 0={R24,R25}, 15={R54,R55}")
    p.add_argument("--baseline", action="store_true",
                   help="omit marker; expected result is 17.0")
    ns = p.parse_args()
    targets = ("E", "O") if ns.target == "both" else (ns.target,)
    print("delay " + " ".join(f"{t:>18s}" for t in targets))
    for delay in parse_delays(ns.delays):
        results = [label(run_case(t, ns.pair, delay, ns.hstall, ns.dstall,
                                  ns.mma, ns.qfmt, ns.reps,
                                  marker=not ns.baseline), ns.mma)
                   for t in targets]
        print(f"{delay:5d} " + " ".join(f"{x:>18s}" for x in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
