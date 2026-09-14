#!/usr/bin/env python3
"""Probe whether two hot LDG.32 completions serialize by destination RF bank.

Two loads use independent scoreboards (SB4/SB5) and different warmed cache
lines.  Their destination layout is EE, EO, OE, or OO.  A single consumer
waits for both barriers, so the measured endpoint is actual completion rather
than a latency-table guess.  ``--gaps`` scans issue separation.  ``--storm``
optionally inserts a reuse-fed, one-parity FFMA write stream after both loads.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


REGS = {"EE": (40, 42), "EO": (40, 41), "OE": (41, 40), "OO": (41, 43)}


def source(layout: str, gap: int, storm: int, storm_parity: str) -> str:
    ra, rb = REGS[layout]
    p = 0 if storm_parity == "E" else 1
    dsts = [50 + p + 2 * i for i in range(20)]
    lines = [
        "#fn mioburst(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(data);[2:7:{}:1:0]",
        "    S2R R8, SR_TID.X;[3:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R8, 0x20, {R2,R3};"
        "[7:7:{1,3}:5:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f000000;[7:7:{}:5:1]",
    ]
    for r in dsts:
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    # Warm and retire both distinct cache lines before the timed pair.
    lines += [
        "    LDG.E R30, desc[{UR4,UR5}][{R6,R7}];[4:7:{0,2}:5:1]",
        "    LDG.E R31, desc[{UR4,UR5}][{R6,R7}+0x80];[5:7:{}:5:1]",
        "    IADD3 R33, R30, R31, RZ;[7:7:{4,5}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    LDG.E R{ra}, desc[{{UR4,UR5}}][{{R6,R7}}];[4:7:{{}}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:0]" for _ in range(gap)]
    lines.append(
        f"    LDG.E R{rb}, desc[{{UR4,UR5}}][{{R6,R7}}+0x80];"
        "[5:7:{}:1:1]")
    for i in range(storm):
        lines.append(
            f"    FFMA R{dsts[i % len(dsts)]}, R24, R27, R28;"
            "[7:7:{}:1:0:7]")
    lines += [
        f"    IADD3 R32, R{ra}, R{rb}, RZ;[7:7:{{4,5}}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    STG.E.STRONG.GPU [{R10,R11}+0x10], R32;[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_case(layout: str, gap: int, storm: int, storm_parity: str,
             reps: int) -> list[int]:
    cubin = assemble(source(layout, gap, storm, storm_parity), check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(32 * 32)
    data = mod.devmem_alloc(256)
    payload = bytearray(256)
    struct.pack_into("<I", payload, 0, 0x11111111)
    struct.pack_into("<I", payload, 0x80, 0x22222222)
    mod.device_write(data, bytes(payload))
    try:
        vals = []
        for rep in range(reps + 1):
            mod.launch("mioburst", grid=(1,), block=(32,), args=[out, data])
            mod.synchronize()
            t0, t1, got = struct.unpack("<QQI", mod.device_read(out, 20))
            if got != 0x33333333:
                raise RuntimeError(f"bad pair result 0x{got:08x}")
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
        return vals
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gaps", default="0,1,2,3,4,6,8,12,16")
    p.add_argument("--storm", type=int, default=0)
    p.add_argument("--reps", type=int, default=20)
    ns = p.parse_args()
    gaps = [int(x) for x in ns.gaps.split(",") if x.strip()]
    if not gaps or min(gaps) < 0 or ns.storm < 0 or ns.reps <= 0:
        p.error("gaps/storm must be non-negative and reps positive")
    for parity in (("E", "O") if ns.storm else ("E",)):
        print(f"two hot LDG.32 completions; storm={ns.storm} parity={parity}")
        print("gap  EEbest EO... OE... OObest | EEmed  EOmed  OEmed  OOmed")
        for gap in gaps:
            rows = {layout: run_case(layout, gap, ns.storm, parity, ns.reps)
                    for layout in REGS}
            best = {k: min(v) for k, v in rows.items()}
            med = {k: statistics.median(v) for k, v in rows.items()}
            print(f"{gap:3d} {best['EE']:7d} {best['EO']:5d} {best['OE']:5d} "
                  f"{best['OO']:7d} | {med['EE']:5.1f} {med['EO']:6.1f} "
                  f"{med['OE']:6.1f} {med['OO']:6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
