#!/usr/bin/env python3
"""Locate the UR address-sampling point of sm_120 uniform-form LDS.

The test intentionally omits a source-release anti-dependency.  Shared[0]
and shared[4] contain distinct sentinels.  UR10 starts at zero; after issuing
``LDS [RZ+UR10]`` the warp overwrites UR10 with four.  A prefix of global
stores retains the LDS in the local LSU queue, as in probe_ldg_address_latch.
If UR10 is sampled at dequeue, a sufficiently early overwrite selects the
new sentinel; an enqueue-time UR latch always selects the old sentinel.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OLD, NEW = 0x11223344, 0x55667788


def source(prefix: int, gap: int, kind: str) -> str:
    if kind == "ur":
        load = "LDS R40, [RZ+UR10]"
        overwrite = "UMOV UR10, 0x4"
    elif kind == "gpr":
        load = "LDS R40, [R26]"
        overwrite = "IADD3 R26, R26, 0x4, RZ"
    else:
        raise ValueError(kind)
    lines = [
        "#fn ldsurlatch(out<8>, flood<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(1024)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(flood);[1:7:{}:1:0]",
        f"    MOV32I R30, 0x{OLD:08x};[7:7:{{}}:5:1]",
        f"    MOV32I R31, 0x{NEW:08x};[7:7:{{}}:5:1]",
        "    MOV32I R32, 0xaaaaaaaa;[7:7:{}:5:1]",
        "    MOV32I R33, 0xbbbbbbbb;[7:7:{}:5:1]",
        "    MOV32I R34, 0xcccccccc;[7:7:{}:5:1]",
        "    MOV32I R35, 0xdddddddd;[7:7:{}:5:1]",
        "    MOV32I R26, 0x0;[7:7:{}:5:1]",
        "    STS [RZ], R30;[7:7:{}:5:1]",
        "    STS [RZ+0x4], R31;[7:7:{}:5:1]",
        "    UMOV UR10, URZ;[7:7:{}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    for i in range(prefix):
        lines.append(
            f"    STG.E.128.STRONG.GPU [{{R6,R7}}+0x{i * 128:x}], "
            "{R32,R33,R34,R35};[7:7:{1}:1:1]")
    lines += [
        f"    {load};[4:7:{{}}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    lines += [
        f"    {overwrite};[7:7:{{}}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    IADD3 R41, R40, RZ, RZ;[7:7:{4}:5:1]",
        "    STG.E.STRONG.GPU [{R2,R3}], R41;[7:0:{0}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(prefix: int, gap: int, kind: str,
        reps: int) -> tuple[int, int, list[int]]:
    mod = CudaModule(assemble(source(prefix, gap, kind), check_deps=True))
    out = mod.devmem_alloc(4)
    flood = mod.devmem_alloc(max(0x1000, prefix * 128 + 128))
    old = new = 0
    other: list[int] = []
    try:
        for _ in range(reps):
            mod.launch("ldsurlatch", grid=(1,), block=(32,), args=[out, flood])
            mod.synchronize()
            got, = struct.unpack("<I", mod.device_read(out, 4))
            if got == OLD:
                old += 1
            elif got == NEW:
                new += 1
            else:
                other.append(got)
    finally:
        mod.devmem_free(flood)
        mod.devmem_free(out)
    return old, new, other


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefixes", default="0,4,16,64")
    p.add_argument("--gaps", default="0,2,4,8,12,16,20,24")
    p.add_argument("--kind", choices=("ur", "gpr"), default="ur")
    p.add_argument("--reps", type=int, default=10)
    ns = p.parse_args()
    prefixes = [int(x) for x in ns.prefixes.split(",") if x.strip()]
    gaps = [int(x) for x in ns.gaps.split(",") if x.strip()]
    if not prefixes or not gaps or min(prefixes + gaps) < 0 or ns.reps <= 0:
        p.error("non-negative prefixes/gaps and positive reps required")
    print(f"kind={ns.kind}")
    print("prefix gap old new other")
    for prefix in prefixes:
        for gap in gaps:
            old, new, other = run(prefix, gap, ns.kind, ns.reps)
            print(f"{prefix:6d} {gap:3d} {old:3d} {new:3d} {other}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
