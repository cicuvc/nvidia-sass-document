#!/usr/bin/env python3
"""Measure pairwise UTCSHIFT service between 32-column TMEM tiles on B200."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _shift_ops(count: int, ureg: int) -> list[str]:
    return [
        f"    UTCSHIFT.DOWN tmem[UR{ureg}];[7:7:{{}}:1:1]"
        for _ in range(count)
    ]


def source(name: str, tile0: int, tile1: int, count: int) -> str:
    if tile0 % 32 or tile1 % 32 or not (0 <= tile0 < 512 and 0 <= tile1 < 512):
        raise ValueError("tile starts must be multiples of 32 in 0..480")
    if count < 1:
        raise ValueError("count must be positive")
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma SHARED(0x1000)",
        "    #pragma NUM_MBARRIERS(2)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R8,R9}, R5, 0x10, {R2,R3};[7:7:{0}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_wait);[7:7:{}:5:0]",
        "    #!tmem_alloc_1cta(UR5, 512)",
        "    UMOV UR18, 0x600;[7:7:{}:1:0]",
        "    #!mbarrier_init(UR18, 1)",
        "    UMOV UR18, 0x608;[7:7:{}:1:0]",
        "    #!mbarrier_init(UR18, 1)",
        "    #def_label(setup_wait)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(shift0);[7:7:{}:5:0]",
        "    ISETP.EQ.AND P1, PT, R5, 0x1, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(shift1);[7:7:{}:5:0]",
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(shift0)",
        f"    UIADD3 UR11, UPT, UPT, UR10, {tile0:#x}, URZ;[7:7:{{}}:5:1]",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]",
    ]
    lines += _shift_ops(count, 11)
    lines += [
        "    UMOV UR18, 0x600;[7:7:{}:1:0]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P2, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P2 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:1:0]",
        "    @P2 STG.E.64.STRONG.GPU [{R8,R9}+0x8], {R18,R19};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(shift1)",
        f"    UIADD3 UR11, UPT, UPT, UR10, {tile1:#x}, URZ;[7:7:{{}}:5:1]",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]",
    ]
    lines += _shift_ops(count, 11)
    lines += [
        "    UMOV UR18, 0x608;[7:7:{}:1:0]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P2, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P2 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:1:0]",
        "    @P2 STG.E.64.STRONG.GPU [{R8,R9}+0x8], {R18,R19};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    #def_label(work_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(dealloc_done);[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    #def_label(dealloc_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tile0", type=int, default=0)
    ap.add_argument("--tile1", type=int, required=True)
    ap.add_argument("--count", type=int, default=64)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    name = f"utcshift_pair_{ns.tile0}_{ns.tile1}_n{ns.count}"
    src = source(name, ns.tile0, ns.tile1, ns.count)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
