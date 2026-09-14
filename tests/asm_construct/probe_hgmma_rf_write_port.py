#!/usr/bin/env python3
"""Test whether HGMMA accumulator words commit through parity-banked RF 1W.

Warpgroup 0 issues one n8 overwrite HGMMA after initializing R24..R27 to a
poison word.  Without waiting gsb0, it samples either R24 (even bank) or R25
(odd bank) after a swept NOP delay.  Warpgroup 1 concurrently runs a dense
all-reuse FFMA stream whose destinations are exclusively even or odd.  An
identical all-lanes-false FFMA stream is the scheduling/control baseline.

A normal parity-banked write port predicts a target-parity x writer-parity
interaction in the poison->fresh visibility boundary.  A fully independent TC
write port predicts no such diagonal interaction.  This intentionally reads
an HGMMA result before DEPBAR and therefore is a microarchitectural race, not
an example of valid application scheduling.
"""

from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


POISON = 0xDEADBEEF
FRESH = 0x41800000       # dot(bf16 ones[16], bf16 ones[16]) = 16.0
MARKER = 0x40000000      # scalar overwrite after the async HGMMA


def source(target: str, writer: str, active: bool, delay: int,
           storm: int, hstall: int = 4) -> str:
    # Use the tail pair of an n64 accumulator.  The first n8 words are already
    # visible before a lone STG reaches its late-read point; R54/R55 retain a
    # sizeable pre-DEPBAR stale window.
    treg = 54 if target == "E" else 55
    parity = 0 if writer == "E" else 1
    guard = "" if active else "@P6 "
    lines = [
        "#fn hgwbedge(out<8>) {",
        "    #pragma MAXREG_COUNT(128)",
        "    #pragma SHARED(16384)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x4, {R2,R3};[7:7:{0,1}:5:1]",
        "    SHF.L.U32 R12, R4, 0x4, RZ;[7:7:{1}:5:1]",
        "    MOV32I R8, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R9, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R10, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R11, 0x3f803f80;[7:7:{}:5:1]",
        "    STS.128 [R12], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x1000], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x2000], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x3000], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    MOV32I R116, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R117, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R118, 0x3f000000;[7:7:{}:5:1]",
        "    UMOV UR4, 0x400040;[7:7:{}:5:1]",
        "    UMOV UR5, 0x0;[7:7:{}:5:1]",
        "    UMOV UR6, 0x4000c0;[7:7:{}:5:1]",
        "    UMOV UR7, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P0, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(hpath);[7:7:{}:5:1]",
        "    BRA #label(cpath);[7:7:{}:5:1]",
        "#def_label(hpath)",
        "    WARPGROUP.ARRIVE;[7:7:{}:5:1]",
        "    HGMMA.64x64x16.F32.BF16 "
        "{R24,R25,R26,R27,R28,R29,R30,R31,R32,R33,R34,R35,R36,R37,"
        "R38,R39,R40,R41,R42,R43,R44,R45,R46,R47,R48,R49,R50,R51,"
        "R52,R53,R54,R55}, "
        f"gdesc[UR4], RZ, !UPT, gsb0;[7:7:{{}}:{hstall}:0]",
    ]
    # Accumulator poison must be initialized before ARRIVE, but generating it
    # here keeps the wide register list readable above.
    poison = [f"    MOV32I R{r}, 0x{POISON:08x};[7:7:{{}}:5:1]"
              for r in range(24, 56)]
    bar = lines.index("    BAR.SYNC 0;[7:7:{}:5:1]")
    lines[bar:bar] = poison
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(delay)]
    lines += [
        # WAW race: if this scalar write commits first, the later HGMMA write
        # wins (FRESH); if HGMMA committed first, MARKER wins.  Unlike an ALU
        # read, this does not invoke HGMMA-result forwarding/interlock.
        f"    MOV32I R{treg}, 0x{MARKER:08x};[7:7:{{}}:5:1]",
        "    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]",
        f"    STG.E.STRONG.GPU [{{R6,R7}}], R{treg};[7:2:{{}}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "#def_label(cpath)",
    ]
    for i in range(storm):
        dst = 64 + parity + 2 * (i % 16)
        lines.append(f"    {guard}FFMA R{dst}, R116, R117, R118;"
                     "[7:7:{}:1:0:7]")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run_case(target: str, writer: str, active: bool, delay: int,
             storm: int, reps: int, hstall: int = 4) -> collections.Counter[int]:
    cubin = assemble(source(target, writer, active, delay, storm, hstall),
                     arch="sm90", check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(256 * 4)
    counts: collections.Counter[int] = collections.Counter()
    try:
        for rep in range(reps + 1):
            mod.devmem_set(out, 0xAAAAAAAA, 256)
            mod.launch("hgwbedge", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            if rep:
                value = struct.unpack("<I", mod.device_read(out, 4))[0]
                counts[value] += 1
    finally:
        mod.devmem_free(out)
    return counts


def label(counts: collections.Counter[int]) -> str:
    parts = []
    for value, count in counts.most_common():
        kind = ("S" if value == POISON else "M" if value == MARKER else
                "Z" if value == 0 else "F" if value == FRESH else
                f"?{value:08x}")
        parts.append(f"{kind}{count}")
    return "/".join(parts)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--delays", default="0:41:2", help="start:stop:step or CSV")
    p.add_argument("--storm", type=int, default=192)
    p.add_argument("--reps", type=int, default=20)
    p.add_argument("--hstall", type=int, choices=range(1, 8), default=4)
    ns = p.parse_args()
    if ":" in ns.delays:
        a, b, c = (int(x) for x in ns.delays.split(":"))
        delays = list(range(a, b, c))
    else:
        delays = [int(x) for x in ns.delays.split(",") if x]
    print("delay  EE-act EO-act OE-act OO-act  EE-off EO-off OE-off OO-off")
    for delay in delays:
        row = []
        for active in (True, False):
            for target in ("E", "O"):
                for writer in ("E", "O"):
                    row.append(label(run_case(target, writer, active, delay,
                                              ns.storm, ns.reps, ns.hstall)))
        print(f"{delay:5d}  " + " ".join(f"{x:>6s}" for x in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
