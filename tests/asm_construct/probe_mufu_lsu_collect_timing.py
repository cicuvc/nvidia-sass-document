#!/usr/bin/env python3
"""Time STG source release after independent versus dependent MUFU work."""

from __future__ import annotations

import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(mode: str) -> str:
    if mode == "none":
        producer = []
    elif mode == "independent":
        producer = ["    MUFU.RCP R20, R1;[7:7:{}:1:1]"]
    elif mode == "dependent":
        producer = ["    MUFU.RCP R10, R1;[7:7:{}:1:1]"]
    else:
        raise ValueError(mode)
    lines = [
        "#fn timing(out<8>) {",
        "    LDC.64 {R6,R7}, #param(out);[2:7:{}:1:0]",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[3:7:{}:1:0]",
        "    MOV32I R1, 0x40000000;[7:7:{2,3}:5:1]",
        "    MOV32I R10, 0x40800000;[7:7:{}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:5:0]",
    ]
    lines += producer
    lines += [
        # SB1 is a read/source-release barrier.  The IADD waits until the STG
        # late collector has consumed both data and address operands.
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x40], R10;[7:1:{}:1:1]",
        "    IADD3 R21, RZ, RZ, RZ;[7:7:{1}:5:1]",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:5:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}], {R30,R31};[7:7:{}:8:0]",
        "    STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x8], {R32,R33};[7:7:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(mode: str, reps: int = 30) -> tuple[list[int], list[int]]:
    mod = CudaModule(assemble(source(mode), check_deps=False))
    out = mod.devmem_alloc(0x100)
    elapsed = []
    values = []
    try:
        for i in range(reps + 1):
            mod.device_write(out, bytes(0x100))
            mod.launch("timing", grid=(1,), block=(1,), args=[out])
            mod.synchronize()
            lo0, hi0, lo1, hi1 = struct.unpack("<4I", mod.device_read(out, 16))
            value, = struct.unpack("<I", mod.device_read(out + 0x40, 4))
            if i:
                t0 = (hi0 << 32) | lo0
                t1 = (hi1 << 32) | lo1
                elapsed.append((t1 - t0) & ((1 << 64) - 1))
                values.append(value)
    finally:
        mod.devmem_free(out)
    return elapsed, values


def main() -> int:
    for mode in ("none", "independent", "dependent"):
        elapsed, values = run(mode)
        counts = {hex(v): values.count(v) for v in sorted(set(values))}
        print(f"{mode:11} median={statistics.median(elapsed):5.1f} "
              f"mean={statistics.mean(elapsed):6.2f} "
              f"range={min(elapsed)}..{max(elapsed)} stored={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
