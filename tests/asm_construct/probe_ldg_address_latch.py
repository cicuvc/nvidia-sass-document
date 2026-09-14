#!/usr/bin/env python3
"""Locate the late-read boundary for an LDG address register (GB202).

Warp 0 issues ``prefix`` wide stores to build LSU backlog, then an LDG through
``{R20,R21}``.  After ``gap`` NOPs it changes only R20 from target+0 to
target+0x100.  The returned sentinel says whether the address was sampled
before or after that overwrite.  No source read scoreboard protects R20: the
hazard is deliberate.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OLD = 0x11112222
NEW = 0x33334444


def source(prefix: int, gap: int) -> str:
    lines = [
        "#fn ldalatch(out<8>, target<8>, flood<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R20,R21}, #param(target);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(flood);[2:7:{}:1:0]",
        "    MOV32I R32, 0xaaaaaaaa;[7:7:{}:5:1]",
        "    MOV32I R33, 0xbbbbbbbb;[7:7:{}:5:1]",
        "    MOV32I R34, 0xcccccccc;[7:7:{}:5:1]",
        "    MOV32I R35, 0xdddddddd;[7:7:{}:5:1]",
        # Resolve all parameter loads before creating the deliberate WAR.
        "    IADD3 R8, R6, RZ, RZ;[7:7:{0,1,2}:5:1]",
    ]
    for i in range(prefix):
        lines.append(
            f"    STG.E.128.STRONG.GPU [{{R6,R7}}+0x{i * 128:x}], "
            "{R32,R33,R34,R35};[7:7:{}:1:1]")
    lines += [
        "    LDG.E.STRONG.GPU R40, [{R20,R21}];[4:7:{}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    lines += [
        "    IADD3 R20, R20, 0x100, RZ;[7:7:{}:1:1]",
        "    IADD3 R41, R40, RZ, RZ;[7:7:{4}:5:1]",
        "    STG.E.STRONG.GPU [{R2,R3}], R41;[7:0:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(prefix: int, gap: int, reps: int) -> tuple[int, int, list[int]]:
    mod = CudaModule(assemble(source(prefix, gap), check_deps=True))
    out = mod.devmem_alloc(4)
    target = mod.devmem_alloc(0x200)
    flood = mod.devmem_alloc(max(0x1000, prefix * 128 + 128))
    payload = bytearray(0x200)
    struct.pack_into("<I", payload, 0, OLD)
    struct.pack_into("<I", payload, 0x100, NEW)
    mod.device_write(target, bytes(payload))
    old = new = 0
    other = []
    try:
        for _ in range(reps):
            mod.launch("ldalatch", grid=(1,), block=(32,),
                       args=[out, target, flood])
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
        mod.devmem_free(target)
        mod.devmem_free(out)
    return old, new, other


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefixes", default="0,4,8,16,24,32,40,48,56,64")
    p.add_argument("--gaps", default="0,1,2,4,8,16,32,64")
    p.add_argument("--reps", type=int, default=10)
    ns = p.parse_args()
    prefixes = [int(x) for x in ns.prefixes.split(",") if x.strip()]
    gaps = [int(x) for x in ns.gaps.split(",") if x.strip()]
    if not prefixes or not gaps or min(prefixes + gaps) < 0 or ns.reps <= 0:
        p.error("prefixes/gaps must be non-negative and reps positive")
    print("LDG address latch: O=old address, N=new address")
    print("prefix gap old new other")
    for prefix in prefixes:
        for gap in gaps:
            old, new, other = run(prefix, gap, ns.reps)
            print(f"{prefix:6d} {gap:3d} {old:3d} {new:3d} {other}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
