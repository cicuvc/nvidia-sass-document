#!/usr/bin/env python3
"""Validate XU admission credits using MUFU late-source liveness."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OLD_BITS, NEW_BITS = 0x3F800000, 0x40000000  # 1.0, 2.0
OLD_RCP, NEW_RCP = 0x3F800000, 0x3F000000    # 1.0, 0.5


def source(prefix: int, gap: int) -> str:
    lines = [
        "#fn xuqlatch(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        f"    MOV32I R24, 0x{OLD_BITS:08x};[7:7:{{}}:5:1]",
    ]
    lines += [f"    MUFU.RCP R{40 + i}, RZ;[7:7:{{}}:1:1]"
              for i in range(prefix)]
    lines += ["    MUFU.RCP R80, R24;[4:7:{}:1:1]"]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    lines += [
        f"    MOV32I R24, 0x{NEW_BITS:08x};[7:7:{{}}:5:1]",
        "    IADD3 R81, R80, RZ, RZ;[7:7:{4}:5:1]",
        "    STG.E.STRONG.GPU [{R2,R3}], R81;[7:0:{0}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(prefix: int, gap: int, reps: int) -> tuple[int, int, list[int]]:
    mod = CudaModule(assemble(source(prefix, gap), check_deps=True))
    out = mod.devmem_alloc(4)
    old = new = 0
    other = []
    try:
        for _ in range(reps):
            mod.launch("xuqlatch", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            got, = struct.unpack("<I", mod.device_read(out, 4))
            if got == OLD_RCP:
                old += 1
            elif got == NEW_RCP:
                new += 1
            else:
                other.append(hex(got))
    finally:
        mod.devmem_free(out)
    return old, new, other


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefixes", default="0,1,2,3,4,5,6")
    p.add_argument("--gaps", default="0,2,4,8,12,16")
    p.add_argument("--reps", type=int, default=10)
    ns = p.parse_args()
    prefixes = [int(x) for x in ns.prefixes.split(",") if x.strip()]
    gaps = [int(x) for x in ns.gaps.split(",") if x.strip()]
    print("prefix gap old new other")
    for prefix in prefixes:
        for gap in gaps:
            old, new, other = run(prefix, gap, ns.reps)
            print(f"{prefix:6d} {gap:3d} {old:3d} {new:3d} {other}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
