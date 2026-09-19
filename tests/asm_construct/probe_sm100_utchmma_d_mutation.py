#!/usr/bin/env python3
"""Distinguish early D capture from late UTCHMMA accumulator RMW.

All four 32-row TMEM chunks of an M128N8 accumulator start at FP32 1.0.
Warp 0 submits one BF16-one x BF16-one K16 accumulate, whose undisturbed
answer is 17.0.  At a swept phase, warp 1 overwrites its own chunk with 64.0
through STTM.x8.  The final tile has three diagnostic outcomes:

  17.0: MMA used the original D;
  64.0: STTM happened after the MMA writeback;
  80.0: MMA consumed the in-flight STTM value, proving a late D read/RMW.

The output is 1024 tile words (thread-major, eight columns per thread), then
five u64 clocks: MMA pre-issue/admission-upper-bound/done and mutation
start/done.  The first instruction after UTCHMMA provides an upper bound on
actual admission, since a blocked UTCHMMA prevents its warp from advancing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _group(lo: int, count: int) -> str:
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def _clock_wait(label: str) -> list[str]:
    return [
        f"    #def_label({label})",
        "    CS2R {R56,R57}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P3, PT, R56, R20, PT;[7:7:{}:13:1]",
        f"    @P3 BRA #label({label});[7:7:{{}}:5:1]",
    ]


def source(name: str, phase: int) -> str:
    if phase < 0:
        raise ValueError("phase must be non-negative")

    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(0x3000)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]",
        "    SHL R12, R4, 0x4;[7:7:{}:5:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        *[f"    MOV R{reg}, R24;[7:7:{{}}:5:1]" for reg in range(25, 32)],
        "    MOV32I R32, 0x42800000;[7:7:{}:5:1]",
        *[f"    MOV R{reg}, R32;[7:7:{{}}:5:1]" for reg in range(33, 40)],
        "    MOV32I R60, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV R61, R60;[7:7:{}:5:1]",
        "    MOV R62, R60;[7:7:{}:5:1]",
        "    MOV R63, R60;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P4, PT, R4, 0x40, PT;[7:7:{}:13:1]",
    ]
    # Four 1-KiB stripes for each BF16 operand tile.
    for off in (0x800, 0xc00, 0x1000, 0x1400,
                0x1800, 0x1c00, 0x2000, 0x2400):
        lines += [
            f"    @P4 STS.128 [R12+{off:#x}], {{R60,R61,R62,R63}};"
            "[7:7:{}:1:0]"
        ]
    lines += [
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_wait);[7:7:{}:5:0]",
        "    #!tmem_alloc_1cta(UR5, 32)",
        "    UMOV UR18, 0x600;[7:7:{}:1:0]",
        "    #!mbarrier_init(UR18, 1)",
        "    #def_label(setup_wait)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        "    UMOV UR20, 0x100080;[7:7:{}:1:0]",
        "    UMOV UR21, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR22, 0x100180;[7:7:{}:1:0]",
        "    UMOV UR23, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR14, 0x0;[7:7:{}:1:0]",
        # M128N8K16, BF16 x BF16 -> FP32.
        "    UMOV UR15, 0x8020490;[7:7:{}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
        # Every warp initializes its own 32-row chunk to 1.0.
        f"    STTM.x8 tmem[UR10], {_group(24, 8)};[7:7:{{}}:1:0]",
        "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # Warp-0 lane 0 publishes a future common clock target.
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    ISETP.EQ.AND P1, PT, R6, RZ, P0;[7:7:{}:13:1]",
        "    @P1 CS2R {R58,R59}, SR_CLOCKLO;[0:7:{}:5:1]",
        "    @P1 IADD3 R58, R58, 0x800, RZ;[7:7:{0}:5:1]",
        "    @P1 STS [RZ+0x700], R58;[7:7:{}:1:0]",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R20, [RZ+0x700];[0:7:{}:1:0]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{0}:13:1]",
        "    @P0 BRA #label(producer);[7:7:{}:5:0]",
        "    ISETP.EQ.AND P1, PT, R5, 0x1, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(modifier);[7:7:{}:5:0]",
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(producer)",
    ]
    lines += _clock_wait("producer_wait")
    lines += [
        "    CS2R {R48,R49}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
        "tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, UPT;"
        "[7:0:{}:12:1]",
        "    CS2R {R50,R51}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    UMOV UR18, 0x600;[7:7:{}:5:1]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R64,R65}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P6, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P6 STG.E.64.STRONG.GPU [{R2,R3}+0x1000], {R48,R49};"
        "[7:0:{}:1:0]",
        "    @P6 STG.E.64.STRONG.GPU [{R2,R3}+0x1008], {R50,R51};"
        "[7:1:{0}:1:0]",
        "    @P6 STG.E.64.STRONG.GPU [{R2,R3}+0x1010], {R64,R65};"
        "[7:2:{1}:1:0]",
        "    NOP;[7:7:{0,2}:1:0]",
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(modifier)",
    ]
    lines += _clock_wait("modifier_wait")
    lines += ["    NOP;[7:7:{}:1:0]"] * phase
    lines += [
        "    CS2R {R52,R53}, SR_CLOCKLO;[7:7:{}:5:1]",
        f"    STTM.x8 tmem[UR10], {_group(32, 8)};[7:7:{{}}:1:0]",
        "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
        "    CS2R {R54,R55}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P6, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P6 STG.E.64.STRONG.GPU [{R2,R3}+0x1018], {R52,R53};"
        "[7:0:{}:1:0]",
        "    @P6 STG.E.64.STRONG.GPU [{R2,R3}+0x1020], {R54,R55};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{0,1}:1:0]",
        "    #def_label(work_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # Export all 128 rows x 8 columns in thread-major order.
        f"    LDTM.x8 {_group(40, 8)}, tmem[UR10];[2:7:{{}}:1:0]",
        "    IMAD.WIDE.U32 {R8,R9}, R4, 0x20, {R2,R3};[7:7:{0}:5:1]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}], {_group(40, 4)};"
        "[7:0:{2}:1:0]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}+0x10], {_group(44, 4)};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(dealloc_done);[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 32)",
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
    ap.add_argument("--phase", type=int, required=True,
                    help="stall-1 NOPs before the mutating STTM")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    name = f"utchmma_d_mutation_p{ns.phase}"
    src = source(name, ns.phase)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
