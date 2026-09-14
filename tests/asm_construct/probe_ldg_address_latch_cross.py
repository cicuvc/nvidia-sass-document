#!/usr/bin/env python3
"""LDG address-latch window under same/different-subcore LSU flooding."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OLD, NEW = 0x11112222, 0x33334444


def source(contender_warp: int, flood_n: int, headstart: int, gap: int) -> str:
    lines = [
        "#fn ldacross(out<8>, target<8>, flood<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R20,R21}, #param(target);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(flood);[2:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{3}:5:1]",
        "    MOV32I R32, 0xaaaaaaaa;[7:7:{}:5:1]",
        "    MOV32I R33, 0xbbbbbbbb;[7:7:{}:5:1]",
        "    MOV32I R34, 0xcccccccc;[7:7:{}:5:1]",
        "    MOV32I R35, 0xdddddddd;[7:7:{}:5:1]",
        "    IADD3 R8, R6, RZ, RZ;[7:7:{0,1,2}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        f"    ISETP.EQ.AND P0, PT, R5, 0x{contender_warp:x}, PT;"
        "[7:7:{}:13:1]",
        "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(headstart)]
    lines += ["    LDG.E.STRONG.GPU R40, [{R20,R21}];[4:7:{}:1:1]"]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    lines += [
        "    IADD3 R20, R20, 0x100, RZ;[7:7:{}:1:1]",
        "    IADD3 R41, R40, RZ, RZ;[7:7:{4}:5:1]",
        "    STG.E.STRONG.GPU [{R2,R3}], R41;[7:0:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
    ]
    for i in range(flood_n):
        lines.append(
            f"    STG.E.128.STRONG.GPU [{{R6,R7}}+0x{i * 128:x}], "
            "{R32,R33,R34,R35};[7:7:{}:1:1]")
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run(cwarp: int, flood_n: int, headstart: int, gap: int,
        reps: int) -> tuple[int, int, list[int]]:
    mod = CudaModule(assemble(source(cwarp, flood_n, headstart, gap),
                              check_deps=True))
    out = mod.devmem_alloc(4)
    target = mod.devmem_alloc(0x200)
    flood = mod.devmem_alloc(max(0x1000, flood_n * 128 + 128))
    payload = bytearray(0x200)
    struct.pack_into("<I", payload, 0, OLD)
    struct.pack_into("<I", payload, 0x100, NEW)
    mod.device_write(target, bytes(payload))
    old = new = 0
    other = []
    try:
        for _ in range(reps):
            mod.launch("ldacross", grid=(1,), block=(256,),
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
    p.add_argument("--placement", choices=("same", "diff"), default="diff")
    p.add_argument("--flood", type=int, default=128)
    p.add_argument("--headstarts", default="0,4,8,16,32")
    p.add_argument("--gaps", default="0,2,4,8,12,16,20,24,32")
    p.add_argument("--reps", type=int, default=10)
    ns = p.parse_args()
    hs = [int(x) for x in ns.headstarts.split(",") if x.strip()]
    gaps = [int(x) for x in ns.gaps.split(",") if x.strip()]
    if ns.flood < 0 or not hs or not gaps or min(hs + gaps) < 0 or ns.reps <= 0:
        p.error("non-negative flood/headstarts/gaps and positive reps required")
    cwarp = 4 if ns.placement == "same" else 1
    print(f"cross-warp LDG address latch: placement={ns.placement}")
    print("head gap old new other")
    for head in hs:
        for gap in gaps:
            old, new, other = run(cwarp, ns.flood, head, gap, ns.reps)
            print(f"{head:4d} {gap:3d} {old:3d} {new:3d} {other}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
