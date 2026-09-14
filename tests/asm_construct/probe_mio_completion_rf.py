#!/usr/bin/env python3
"""Parity collision between variable-latency completion and FFMA RF writes.

One scoreboarded producer writes an even or odd GPR.  A dense reuse-fed FFMA
stream then writes only one parity, followed by the first req-waiting consumer.
Sweeping the storm length aligns the completion with the ALU write stream.
LDG/LDS/SHFL are MIO2RF-class according to NCU; MUFU is XU-class and provides
the important test of whether it nevertheless joins the final RF-bank arbiter.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


PRODUCERS = ("ldg", "lds", "shfl", "mufu")


def source(producer: str, result_parity: str, storm_parity: str, n: int) -> str:
    rd = 40 if result_parity == "E" else 41
    p = 0 if storm_parity == "E" else 1
    dsts = [50 + p + 2 * i for i in range(20)]
    lines = [
        "#fn miocrf(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(1024)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(data);[2:7:{}:1:0]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f000000;[7:7:{}:5:1]",
    ]
    for r in dsts:
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    # Warm LDG's exact line and retire setup dependencies.  This load remains
    # in every case so only the selected timed producer differs.
    lines += [
        "    LDG.E R30, [{R6,R7}];[3:7:{2}:5:1]",
        "    IADD3 R31, R30, RZ, RZ;[7:7:{3}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if producer == "ldg":
        inst = f"LDG.E R{rd}, [{{R6,R7}}]"
    elif producer == "lds":
        inst = f"LDS R{rd}, [RZ]"
    elif producer == "shfl":
        inst = f"SHFL.BFLY PT, R{rd}, R24, 0x1, 0x1f"
    elif producer == "mufu":
        inst = f"MUFU.RCP R{rd}, R24"
    else:
        raise ValueError(producer)
    lines.append(f"    {inst};[4:7:{{}}:1:1]")
    for i in range(n):
        lines.append(
            f"    FFMA R{dsts[i % len(dsts)]}, R24, R27, R28;"
            "[7:7:{}:1:0:7]")
    lines += [
        f"    IADD3 R32, R{rd}, RZ, RZ;[7:7:{{4}}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(producer: str, rp: str, sp: str, n: int, reps: int) -> list[int]:
    mod = CudaModule(assemble(source(producer, rp, sp, n), check_deps=True))
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(128)
    mod.devmem_set(data, 0x3f800000, 32)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("miocrf", grid=(1,), block=(32,), args=[out, data])
            mod.synchronize()
            if rep:
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return vals


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--producer", choices=PRODUCERS, default="mufu")
    p.add_argument("--counts", default="0,4,8,12,16,20,24,28,32,40,48")
    p.add_argument("--reps", type=int, default=10)
    ns = p.parse_args()
    counts = [int(x) for x in ns.counts.split(",") if x.strip()]
    if not counts or min(counts) < 0 or ns.reps <= 0:
        p.error("counts must be non-negative and reps positive")
    print(f"{ns.producer} scoreboard completion vs parity-only FFMA writes")
    print(" N  EE  EO dE  OO  OE dO | median deltas")
    for n in counts:
        rows = {(rp, sp): run(ns.producer, rp, sp, n, ns.reps)
                for rp in ("E", "O") for sp in ("E", "O")}
        best = {k: min(v) for k, v in rows.items()}
        med = {k: statistics.median(v) for k, v in rows.items()}
        print(f"{n:2d} {best['E','E']:3d} {best['E','O']:3d} "
              f"{best['E','E']-best['E','O']:+3d} "
              f"{best['O','O']:3d} {best['O','E']:3d} "
              f"{best['O','O']-best['O','E']:+3d} | "
              f"{med['E','E']-med['E','O']:+4.1f} "
              f"{med['O','O']-med['O','E']:+4.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
