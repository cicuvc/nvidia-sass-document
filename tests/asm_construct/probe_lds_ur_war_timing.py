#!/usr/bin/env python3
"""Check whether an LDS UR source implicitly stalls a following UR writer."""

from __future__ import annotations

import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(prefix: int, kind: str) -> str:
    if kind == "ur":
        load = "LDS R40, [RZ+UR10]"
        overwrite = "UMOV UR10, 0x4"
        copy = "MOV R41, UR10"
    elif kind == "gpr":
        load = "LDS R40, [R26]"
        overwrite = "IADD3 R26, R26, 0x4, RZ"
        copy = "IADD3 R41, R26, RZ, RZ"
    else:
        raise ValueError(kind)
    lines = [
        "#fn ldsurwar(out<8>, flood<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(1024)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(flood);[1:7:{}:1:0]",
        "    MOV32I R26, 0x0;[7:7:{}:5:1]",
        "    MOV32I R32, 0xaaaaaaaa;[7:7:{}:5:1]",
        "    MOV32I R33, 0xbbbbbbbb;[7:7:{}:5:1]",
        "    MOV32I R34, 0xcccccccc;[7:7:{}:5:1]",
        "    MOV32I R35, 0xdddddddd;[7:7:{}:5:1]",
        "    UMOV UR10, URZ;[7:7:{}:5:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    for i in range(prefix):
        lines.append(
            f"    STG.E.128.STRONG.GPU [{{R6,R7}}+0x{i * 128:x}], "
            "{R32,R33,R34,R35};[7:7:{1}:1:1]")
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    {load};[7:7:{{}}:1:1]",
        f"    {overwrite};[7:7:{{}}:5:1]",
        f"    {copy};[7:7:{{}}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[7:0:{}:8:0]",
        "    STG.E.STRONG.GPU [{R2,R3}+0x10], R41;[7:0:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    for kind in ("ur", "gpr"):
        for prefix in (0, 4, 16, 64):
            mod = CudaModule(assemble(source(prefix, kind), check_deps=True))
            out = mod.devmem_alloc(20)
            flood = mod.devmem_alloc(max(0x1000, prefix * 128 + 128))
            vals = []
            copies = []
            try:
                for _ in range(11):
                    mod.launch("ldsurwar", grid=(1,), block=(32,),
                               args=[out, flood])
                    mod.synchronize()
                    t0, t1, copied = struct.unpack(
                        "<QQI", mod.device_read(out, 20))
                    vals.append((t1 - t0) & ((1 << 64) - 1))
                    copies.append(copied)
            finally:
                mod.devmem_free(flood)
                mod.devmem_free(out)
            print(f"{kind:4s} prefix={prefix:2d} "
                  f"median={statistics.median(vals):.0f} "
                  f"range={min(vals)}..{max(vals)} copies={sorted(set(copies))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
