#!/usr/bin/env python3
"""Block SHFL's final RF commit while an unbarriered MUFU consumes it."""

from __future__ import annotations

import collections
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


STALE = 0x3E800000  # rcp(4.0)
FRESH = 0x40000000  # rcp(0.5)


def source(n: int, phase: int, placement: str, parity: str,
           predicated: bool, gap: int) -> str:
    p = 0 if parity == "E" else 1
    dsts = [50 + p + 2 * i for i in range(20)]
    warps = ((4,) if placement == "same" else
             (1,) if placement == "diff" else
             () if placement == "none" else None)
    if warps is None:
        raise ValueError(placement)
    vpad, cpad = max(0, -phase), max(0, phase)
    guard = "@P6 " if predicated else ""
    lines = [
        "#fn m2rblock(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{4}:5:1]",
        "    MOV R14, R2;[7:7:{1}:5:1]",
        "    MOV32I R24, 0x3f000000;[7:7:{}:5:1]",
        "    MOV32I R40, 0x40800000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f000000;[7:7:{}:5:1]",
    ]
    for reg in dsts:
        lines.append(f"    MOV32I R{reg}, 0;[7:7:{{}}:5:1]")
    lines += [
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
    ]
    for warp in warps:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, {warp}, PT;[7:7:{{}}:13:1]",
            "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        ]
    lines += ["    BRA #label(done);[7:7:{}:5:1]", "#def_label(victim)"]
    lines += ["    NOP;[7:7:{}:1:0]" for _ in range(vpad)]
    lines += [
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        # SHFL is the MIO2RF producer; SB4 tracks final completion.
        "    SHFL.IDX PT, R40, R24, RZ, 0x1f;[4:7:{}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap - 1)]
    lines += [
        # No req={4}: MUFU captures through the path under test.  Its odd
        # destination avoids the contender's even-bank write stream.
        "    MUFU.RCP R21, R40;[5:7:{}:1:1]",
        # Timestamp the producer's real scoreboard/RF completion.
        "    IADD3 R32, R40, RZ, RZ;[7:7:{4}:5:1]",
        "    CS2R {R34,R35}, SR_CLOCKLO;[7:7:{}:5:0]",
        # Validate the MUFU consumer only after its own completion.
        "    IADD3 R22, R21, RZ, RZ;[7:7:{5}:5:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R30,R31};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R34,R35};[7:7:{}:8:0]",
        "    STG.E.STRONG.GPU [{R2,R3}+0x20], R22;[7:7:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
    ]
    lines += ["    NOP;[7:7:{}:1:0]" for _ in range(cpad)]
    for i in range(n):
        lines.append(
            f"    {guard}FFMA R{dsts[i % len(dsts)]}, R24, R27, R28;"
            "[7:7:{}:1:0:7]")
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run(n: int, phase: int, placement: str, parity: str,
        predicated: bool, gap: int, reps: int = 20) -> tuple[list[int], list[int]]:
    mod = CudaModule(assemble(
        # The missing producer req is the condition under test.
        source(n, phase, placement, parity, predicated, gap), check_deps=False))
    out = mod.devmem_alloc(0x100)
    times, values = [], []
    try:
        for rep in range(reps + 1):
            mod.device_write(out, bytes(0x100))
            mod.launch("m2rblock", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            value, = struct.unpack("<I", mod.device_read(out + 0x20, 4))
            if rep:
                times.append((t1 - t0) & ((1 << 64) - 1))
                values.append(value)
    finally:
        mod.devmem_free(out)
    return times, values


def main() -> int:
    cases = (
        ("solo", "none", "E", False),
        ("same-E", "same", "E", False),
        ("same-E-off", "same", "E", True),
        ("same-O", "same", "O", False),
        ("diff-E", "diff", "E", False),
    )
    print("SHFL R40(E)->MUFU boundary under FFMA final-RF blockade")
    print("phase gap case        producer completion    MUFU result")
    for phase in (-24, -20, -16, -12, -8, -4, 0):
        for gap in range(10, 15):
            for name, placement, parity, predicated in cases:
                times, values = run(32, phase, placement, parity,
                                    predicated, gap)
                vc = collections.Counter(
                    "F" if x == FRESH else "S" if x == STALE else hex(x)
                    for x in values)
                print(f"{phase:5d} {gap:3d} {name:10} "
                      f"{statistics.median(times):6.1f} "
                      f"{min(times):3d}..{max(times):3d}  {dict(vc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
