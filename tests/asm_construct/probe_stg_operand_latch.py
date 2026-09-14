#!/usr/bin/env python3
"""Test whether STG address and store-data GPRs are sampled late.

The target STG deliberately has no source-release barrier.  Older STG.E.128
requests fill the local LSU queue.  Immediately after enqueue, an ALU write
changes either the 64-bit address low word, the data word, or both.  Distinct
destination offsets and marker values reveal each operand's sampling point.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OLD_DATA = 0x11223344
NEW_DATA = 0x55667788
MARKER = 0xA5C3E17B


def source(prefix: int, gap: int, kind: str) -> str:
    target_addr = ("[{R20,R21}+UR10]" if kind == "uraddr"
                   else "[{R20,R21}]")
    lines = [
        "#fn stglatch(target<8>, flood<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R20,R21}, #param(target);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(flood);[1:7:{}:1:0]",
        "    MOV32I R30, 0x%08x;[7:7:{}:5:1]" %
        (MARKER if kind in ("addr", "uraddr") else OLD_DATA),
        "    MOV32I R32, 0xaaaaaaaa;[7:7:{}:5:1]",
        "    MOV32I R33, 0xbbbbbbbb;[7:7:{}:5:1]",
        "    MOV32I R34, 0xcccccccc;[7:7:{}:5:1]",
        "    MOV32I R35, 0xdddddddd;[7:7:{}:5:1]",
        "    UMOV UR10, URZ;[7:7:{}:5:1]",
        "    UMOV UR11, URZ;[7:7:{}:5:1]",
    ]
    for i in range(prefix):
        lines.append(
            f"    STG.E.128.STRONG.GPU [{{R6,R7}}+0x{i * 128:x}], "
            "{R32,R33,R34,R35};[7:7:{1}:1:1]")
    lines += [
        f"    STG.E.STRONG.GPU {target_addr}, R30;[7:7:{{0}}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    if kind in ("addr", "both"):
        lines.append("    IADD3 R20, R20, 0x100, RZ;[7:7:{}:1:1]")
    if kind == "uraddr":
        lines.append("    UMOV UR10, 0x100;[7:7:{}:1:1]")
    if kind in ("data", "both"):
        lines.append(
            f"    MOV32I R30, 0x{NEW_DATA:08x};[7:7:{{}}:1:1]")
    lines += [
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(prefix: int, gap: int, kind: str,
        reps: int) -> dict[tuple[int, int], int]:
    mod = CudaModule(assemble(source(prefix, gap, kind), check_deps=True))
    target = mod.devmem_alloc(0x200)
    flood = mod.devmem_alloc(max(0x1000, prefix * 128 + 128))
    outcomes: dict[tuple[int, int], int] = {}
    try:
        # Exclude the first-launch/module warmup outlier; it otherwise appears
        # as one stale-side sample in almost every sharp boundary case.
        mod.device_write(target, bytes(0x200))
        mod.launch("stglatch", grid=(1,), block=(32,), args=[target, flood])
        mod.synchronize()
        for _ in range(reps):
            mod.device_write(target, bytes(0x200))
            mod.launch("stglatch", grid=(1,), block=(32,),
                       args=[target, flood])
            mod.synchronize()
            raw = mod.device_read(target, 0x104)
            pair = (struct.unpack_from("<I", raw, 0)[0],
                    struct.unpack_from("<I", raw, 0x100)[0])
            outcomes[pair] = outcomes.get(pair, 0) + 1
    finally:
        mod.devmem_free(flood)
        mod.devmem_free(target)
    return outcomes


def fmt(outcomes: dict[tuple[int, int], int]) -> str:
    return " ".join(
        f"({old:08x},{new:08x})x{count}"
        for (old, new), count in sorted(outcomes.items()))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=("addr", "uraddr", "data", "both"),
                   default="addr")
    p.add_argument("--prefixes", default="0,1,2,3,4,6,8,16")
    p.add_argument("--gaps", default="0,2,4,8,12,16,20,24")
    p.add_argument("--reps", type=int, default=10)
    ns = p.parse_args()
    prefixes = [int(x) for x in ns.prefixes.split(",") if x.strip()]
    gaps = [int(x) for x in ns.gaps.split(",") if x.strip()]
    if not prefixes or not gaps or min(prefixes + gaps) < 0 or ns.reps <= 0:
        p.error("non-negative prefixes/gaps and positive reps required")
    print(f"kind={ns.kind}")
    print("prefix gap (old-address-value,new-address-value)xcount")
    for prefix in prefixes:
        for gap in gaps:
            print(f"{prefix:6d} {gap:3d} " +
                  fmt(run(prefix, gap, ns.kind, ns.reps)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
