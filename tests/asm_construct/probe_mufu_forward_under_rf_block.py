#!/usr/bin/env python3
"""Test MUFU->MIO early visibility while blocking the final RF write port.

Warp 0 produces R40 (even bank) with MUFU, samples it through LSU without
waiting the MUFU scoreboard, then waits the producer scoreboard and records
completion time.  One contender warp on either the same or another subcore
generates a dense parity-only FFMA write stream.  The probe scans the gap-5--9
stale/fresh boundary.  If same-bank contention delays scoreboard completion
relative to matched odd/off controls without moving that value boundary, the
value reached the MIO late collector before RF commit.
"""

from __future__ import annotations

import collections
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


POISON = 0x40800000  # 4.0
FRESH = 0x3F000000   # rcp(2.0) = 0.5


def source(n: int, phase: int, placement: str, parity: str,
           predicated: bool, gap: int) -> str:
    p = 0 if parity == "E" else 1
    dsts = [50 + p + 2 * i for i in range(20)]
    if placement == "same":
        contender_warps = (4,)
    elif placement == "diff":
        contender_warps = (1,)
    elif placement == "none":
        contender_warps = ()
    else:
        raise ValueError(placement)
    vpad, cpad = max(0, -phase), max(0, phase)
    guard = "@P6 " if predicated else ""

    lines = [
        "#fn mufublock(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{4}:5:1]",
        "    MOV R14, R2;[7:7:{1}:5:1]",
        "    MOV32I R24, 0x40000000;[7:7:{}:5:1]",
        f"    MOV32I R40, 0x{POISON:08x};[7:7:{{}}:5:1]",
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
    for warp in contender_warps:
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, {warp}, PT;[7:7:{{}}:13:1]",
            "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        ]
    lines += [
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
    ]
    lines += ["    NOP;[7:7:{}:1:0]" for _ in range(vpad)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    MUFU.RCP R40, R24;[4:7:{}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap - 1)]
    lines += [
        # Deliberately no req={4}: this is the forwarding observation.
        "    STG.E.STRONG.GPU [{R2,R3}+0x20], R40;[7:7:{}:1:1]",
        # This consumer does wait and therefore timestamps architectural
        # producer completion after final RF arbitration.
        "    IADD3 R32, R40, RZ, RZ;[7:7:{4}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:7:{}:8:0]",
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
    commits, values = [], []
    try:
        for rep in range(reps + 1):
            mod.device_write(out, bytes(0x100))
            mod.launch("mufublock", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            t0, tc = struct.unpack("<QQ", mod.device_read(out, 16))
            value, = struct.unpack("<I", mod.device_read(out + 0x20, 4))
            if rep:
                commits.append((tc - t0) & ((1 << 64) - 1))
                values.append(value)
    finally:
        mod.devmem_free(out)
    return commits, values


def main() -> int:
    n = 32
    phases = (-16, -12, -8)
    cases = (
        ("solo", "none", "E", False),
        ("same-E", "same", "E", False),
        ("same-E-off", "same", "E", True),
        ("same-O", "same", "O", False),
        ("diff-E", "diff", "E", False),
    )
    print("MUFU R40(E)->STG boundary under parity-only FFMA RF-write storms")
    print("phase gap case        commit median/range   stored-value counts")
    for phase in phases:
        for gap in range(5, 10):
            for name, placement, parity, predicated in cases:
                commits, values = run(
                    n, phase, placement, parity, predicated, gap)
                vc = collections.Counter(
                    "F" if x == FRESH else "S" if x == POISON else hex(x)
                    for x in values)
                print(f"{phase:5d} {gap:3d} {name:10} "
                      f"{statistics.median(commits):6.1f} "
                      f"{min(commits):3d}..{max(commits):3d}   {dict(vc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
