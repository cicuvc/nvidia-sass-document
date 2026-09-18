#!/usr/bin/env python3
"""Build clean B200 UTCHMMA/shared-read contention probes.

All kernels are generated directly in the assembler dialect. Warp 0 owns a
512-column TMEM allocation and optionally issues UTCHMMA. Warps 1--4 map to
the four subcores and each issue a scoreboard-closed LDS.128 stream. Output is
one {start,end} u64 pair per warp.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _lds_loop(batches: int) -> list[str]:
    batch = [
        "    LDS.128 {R40,R41,R42,R43}, [R26];[0:7:{}:1:0]",
        "    LDS.128 {R44,R45,R46,R47}, [R26];[1:7:{}:1:0]",
        "    LDS.128 {R48,R49,R50,R51}, [R26];[2:7:{}:1:0]",
        "    NOP;[7:7:{0,1,2}:1:0]",
    ]
    return batch * batches


def _mma_ops(count: int) -> list[str]:
    lines = []
    for i in range(count):
        if i % 2 == 0:
            batch = i // 2
            lines += [f"    UMOV UR18, {0x600 + batch * 8:#x};"
                      "[7:7:{}:5:1]"]
        lines += [
            "    PLOP3.LUT P4, PT, PT, PT, PT, 0x80, 0x8;[7:7:{}:13:1]",
            f"    #def_label(mma_elect_{i})",
            "    @P4 ELECT P5, URZ, PT;[7:7:{}:1:0]",
            "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
            "tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, !UPT;"
            "[7:0:{0}:12:1]",
            "    @P5 PLOP3.LUT P4, PT, P5, PT, PT, 0x8, 0x80;[7:7:{}:2:0]",
            "    PLOP3.LUT P5, PT, PT, PT, PT, 0x8, 0x80;[7:7:{}:11:1]",
            f"    @P4 BRA.U.ANY #label(mma_elect_{i});[7:7:{{}}:5:0]",
        ]
        if i % 2 == 1 or i + 1 == count:
            lines += [
                "    UTCBAR.1CTA [UR18], URZ;[7:0:{0}:12:1]",
                "    #!mbarrier_wait(UR18, 0)",
            ]
    return lines


def source(name: str, with_mma: bool, with_lds: bool,
           mma_count: int, lds_batches: int) -> str:
    barrier_count = (mma_count + 1) // 2 if with_mma else 1
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(0x3000)",
        f"    #pragma NUM_MBARRIERS({barrier_count})",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]",
        "    SHL R26, R6, 0x4;[7:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R8,R9}, R5, 0x10, {R2,R3};[7:7:{0}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_wait);[7:7:{}:5:0]",
        "    #!tmem_alloc_1cta(UR5, 512)",
    ]
    for barrier in range(barrier_count):
        lines += [
            f"    UMOV UR18, {0x600 + barrier * 8:#x};[7:7:{{}}:1:0]",
            "    #!mbarrier_init(UR18, 1)",
        ]
    lines += [
        "    #def_label(setup_wait)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    UMOV UR20, 0x100080;[7:7:{}:1:0]",
        "    UMOV UR21, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR22, 0x100180;[7:7:{}:1:0]",
        "    UMOV UR23, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR14, 0x0;[7:7:{}:1:0]",
        "    UMOV UR15, 0x8200490;[7:7:{}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if with_mma:
        lines += [
            "    ISETP.EQ.AND P1, PT, R5, RZ, PT;[7:7:{}:13:1]",
            "    @P1 BRA #label(mma_path);[7:7:{}:5:0]",
        ]
    if with_lds:
        lines += [
            "    ISETP.GE.U32.AND P2, PT, R5, 0x1, PT;[7:7:{}:13:1]",
            "    ISETP.LE.U32.AND P2, PT, R5, 0x4, P2;[7:7:{}:13:1]",
            "    @P2 BRA #label(lds_path);[7:7:{}:5:0]",
        ]
    lines += ["    BRA #label(work_done);[7:7:{}:5:0]"]

    if with_mma:
        lines += [
            "    #def_label(mma_path)",
            "    LDS R10, [UR5];[0:7:{}:1:0]",
            "    R2UR UR10, R10;[7:7:{0}:13:1]",
            "    BSSY B0, #label(mma_reconv);[7:7:{}:1:0]",
            "    ISETP.NE.AND P3, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P3 BRA #label(mma_reconv);[7:7:{}:5:0]",
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        ] + _mma_ops(mma_count) + [
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    #def_label(mma_reconv)",
            "    BSYNC B0;[7:7:{}:5:0]",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
            "    BRA #label(work_done);[7:7:{1}:5:0]",
        ]
    if with_lds:
        lines += [
            "    #def_label(lds_path)",
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        ] + _lds_loop(lds_batches) + [
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
            "    BRA #label(work_done);[7:7:{1}:5:0]",
        ]
    lines += [
        "    #def_label(work_done)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(dealloc_done);[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    #def_label(dealloc_done)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("lds", "mma", "combined"), required=True)
    ap.add_argument("--mma-count", type=int, default=4)
    ap.add_argument("--lds-batches", type=int, default=12,
                    help="three LDS.128 instructions per batch")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    if ns.mode != "lds" and not 1 <= ns.mma_count <= 4:
        ap.error("current verified completion protocol supports 1--4 MMA "
                 "operations (at most two independent 2-MMA groups)")
    name = {"lds": "lds4_control", "mma": "utchmma_only",
            "combined": "utchmma_lds4"}[ns.mode]
    src = source(name, ns.mode != "lds", ns.mode != "mma",
                 ns.mma_count, ns.lds_batches)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
