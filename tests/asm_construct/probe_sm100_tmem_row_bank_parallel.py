#!/usr/bin/env python3
"""Test whether row bit 4 changes cross-warp x256 TMEM-bank parallelism."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble_kernel  # noqa: E402


def _group(lo: int, count: int) -> str:
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def source(name: str, split_row: bool, split_column: bool, count: int,
           unroll: int, layout: str = "x256") -> str:
    if count % unroll:
        raise ValueError("count must be divisible by unroll")
    address_stride = ((0x100000 if split_row else 0) +
                      (1 if split_column else 0))
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(80)",
        "    #pragma SHARED(0x800)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R8,R9}, R5, 0x10, {R2,R3};[7:7:{0}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_done);[7:7:{}:5:0]",
        "    #!tmem_alloc_1cta(UR5, 512)",
        "    #def_label(setup_done)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    SHR R6, R5, 0x2;[7:7:{}:5:1]",
        f"    IMAD R11, R6, {address_stride:#x}, R10;[7:7:{{0}}:5:1]",
        "    R2UR UR10, R11;[7:7:{}:13:1]",
    ]
    for reg in range(40, 44):
        lines += [f"    MOV32I R{reg}, {0xA5000000 + reg:#x};[7:7:{{}}:5:1]"]
    lines += [
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P2, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    ISETP.EQ.OR P2, PT, R5, 0x4, P2;[7:7:{}:13:1]",
        "    @!P2 BRA #label(traffic_done);[7:7:{}:5:0]",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]",
        f"    MOV32I R30, {count // unroll};[7:7:{{}}:5:1]",
        "    #def_label(loop)",
    ]
    instruction = (
        "    STTM.16dp256bit tmem[UR10], {R40,R41,R42,R43};"
        "[7:7:{}:1:0]" if layout == "x256" else
        "    STTM.16dp32bit_t0_t15 tmem[UR10], R40;[7:7:{}:1:0]"
    )
    lines += [instruction] * unroll
    lines += [
        "    IADD3 R30, R30, -0x1, RZ;[7:7:{}:5:1]",
        "    ISETP.NE.AND P1, PT, R30, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(loop);[7:7:{}:5:0]",
        "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{0}:1:0]",
        "    STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    #def_label(traffic_done)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(done);[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    #def_label(done)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(count: int, unroll: int, reps: int, layout: str) -> None:
    cases = ((False, False), (False, True),
             (True, False), (True, True))
    for split_row, split_column in cases:
        label = (f"{'split' if split_row else 'same'}_row_"
                 f"{'split' if split_column else 'same'}_col")
        name = f"tmem_row_bank_{layout}_{label}"
        result = assemble_kernel(source(name, split_row, split_column,
                                        count, unroll, layout),
                                 arch="sm100a", check_deps=False)
        mod = CudaModule(result.code)
        out = mod.devmem_alloc(80)
        samples = []
        try:
            for _ in range(reps):
                mod.launch(name, grid=(1,), block=(160,), args=[out])
                mod.synchronize()
                words = struct.unpack("<10Q", mod.device_read(out, 80))
                starts = (words[0], words[8])
                ends = (words[1], words[9])
                samples.append({
                    "warp_cycles": tuple((ends[i] - starts[i]) &
                                         ((1 << 64) - 1) for i in range(2)),
                    "cta_span": max(ends) - min(starts),
                    "start_skew": starts[1] - starts[0],
                })
        finally:
            mod.devmem_free(out)
        print(f"{label}: {samples}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=6144)
    ap.add_argument("--unroll", type=int, default=96)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--layout", choices=("x256", "half_x1"), default="x256")
    ns = ap.parse_args()
    run(ns.count, ns.unroll, ns.reps, ns.layout)


if __name__ == "__main__":
    main()
