#!/usr/bin/env python3
"""Use a narrow half-STTM as a phase probe behind a wide x256 STTM."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble_kernel  # noqa: E402


def source(name: str, wide_row: int, probe_column: int, gap: int,
           count: int, unroll: int) -> str:
    if count % unroll:
        raise ValueError("count must be divisible by unroll")
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(80)",
        "    #pragma SHARED(0x800)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    #!tmem_alloc_1cta(UR5, 512)",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR11, R10;[7:7:{0}:13:1]",
    ]
    # Keep row-0 and row-16 code positions identical: once the loop becomes
    # issue/frontend-bound, shifting it by one 16-byte instruction is itself
    # a measurable confounder.
    lines += [
        f"    IADD3 R11, R10, {wide_row << 16:#x}, RZ;[7:7:{{0}}:5:1]",
        "    R2UR UR10, R11;[7:7:{}:13:1]",
    ]
    for reg in range(40, 45):
        lines += [f"    MOV32I R{reg}, {0xA5000000 + reg:#x};[7:7:{{}}:5:1]"]
    lines += [
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]",
        f"    MOV32I R30, {count // unroll};[7:7:{{}}:5:1]",
        "    #def_label(loop)",
    ]
    addr = ("tmem[UR11]" if probe_column == 0 else
            f"tmem[UR11+{probe_column:#x}]")
    for _ in range(unroll):
        lines += [
            "    STTM.16dp256bit tmem[UR10], {R40,R41,R42,R43};"
            "[7:7:{}:1:0]"
        ]
        lines += ["    NOP;[7:7:{}:1:0]"] * gap
        lines += [
            f"    STTM.16dp32bit_t0_t15 {addr}, R44;[7:7:{{}}:1:0]"
        ]
    lines += [
        "    IADD3 R30, R30, -0x1, RZ;[7:7:{}:5:1]",
        "    ISETP.NE.AND P1, PT, R30, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(loop);[7:7:{}:5:0]",
        "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R16,R17};[7:0:{0}:1:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R18,R19};[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(count: int, unroll: int, gaps: tuple[int, ...], reps: int) -> None:
    for gap in gaps:
        for wide_row in (0, 16):
            for probe_column in (0, 1):
                name = f"tmem_phase_r{wide_row}_c{probe_column}_g{gap}"
                result = assemble_kernel(
                    source(name, wide_row, probe_column, gap, count, unroll),
                    arch="sm100a", check_deps=False)
                mod = CudaModule(result.code)
                out = mod.devmem_alloc(16)
                samples = []
                try:
                    for _ in range(reps):
                        mod.launch(name, grid=(1,), block=(32,), args=[out])
                        mod.synchronize()
                        start, end = struct.unpack(
                            "<QQ", mod.device_read(out, 16))
                        samples.append((end - start) & ((1 << 64) - 1))
                finally:
                    mod.devmem_free(out)
                print(f"gap={gap} wide_row={wide_row:2d} "
                      f"probe_col={probe_column}: {samples}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=3072)
    ap.add_argument("--unroll", type=int, default=32)
    ap.add_argument("--gaps", default="0,1,2,4,7")
    ap.add_argument("--reps", type=int, default=3)
    ns = ap.parse_args()
    gaps = tuple(int(value, 0) for value in ns.gaps.split(","))
    run(ns.count, ns.unroll, gaps, ns.reps)


if __name__ == "__main__":
    main()
