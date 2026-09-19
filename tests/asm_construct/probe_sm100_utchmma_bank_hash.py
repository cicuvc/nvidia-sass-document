#!/usr/bin/env python3
"""Probe the TMEM row-half/column-pair bank hash with masked UTCHMMA.

``mask`` validates the four-word UTCHMMA disable-output-lane vector by
clearing an M128N8 tile, issuing one overwrite MMA, and exporting all 128x8
FP32 values.

``collision`` phase-locks one masked M128N8 overwrite against an aligned
half-STTM.x2 burst or one half-LDTM.x2 at a disjoint logical column.  The
LDTM variant times the load's own scoreboard completion directly; it avoids
both STTM admission and the trailing RAW readback hiding a narrow array-arbiter
stall.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _group(lo: int, count: int) -> str:
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def _idesc() -> int:
    # M128N8K16, BF16 x BF16 -> FP32, no input-D scaling.
    return (8 << 24) | (1 << 17) | 0x490


def _mask_words(mask: str) -> tuple[int, int, int, int]:
    masks = {
        "all": (0, 0, 0, 0),
        "none": (0xffffffff,) * 4,
        "lower": (0xffff0000,) * 4,
        "upper": (0x0000ffff,) * 4,
        "word0": (0, 0xffffffff, 0xffffffff, 0xffffffff),
        "word1": (0xffffffff, 0, 0xffffffff, 0xffffffff),
        "word2": (0xffffffff, 0xffffffff, 0, 0xffffffff),
        "word3": (0xffffffff, 0xffffffff, 0xffffffff, 0),
    }
    return masks[mask]


def _common_setup(name: str, block_words: int) -> list[str]:
    return [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(0x2000)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]",
        "    SHL R12, R4, 0x4;[7:7:{}:5:1]",
        "    MOV32I R20, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV R21, R20;[7:7:{}:5:1]",
        "    MOV R22, R20;[7:7:{}:5:1]",
        "    MOV R23, R20;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P4, PT, R4, 0x40, PT;[7:7:{}:13:1]",
        # Four 1-KiB stripes for A, then the first stripe of N8 B.
        *[
            f"    @P4 STS.128 [R12+{off:#x}], {{R20,R21,R22,R23}};"
            "[7:7:{}:1:0]"
            for off in (0x800, 0xc00, 0x1000, 0x1400, 0x1800)
        ],
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_wait);[7:7:{}:5:0]",
        f"    #!tmem_alloc_1cta(UR5, {block_words})",
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
        f"    UMOV UR15, {_idesc():#x};[7:7:{{}}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
    ]


def _set_mask(mask: str) -> list[str]:
    return [
        f"    UMOV UR{28 + i}, {word:#x};[7:7:{{}}:1:0]"
        for i, word in enumerate(_mask_words(mask))
    ]


def _mma() -> str:
    return (
        "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
        "tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], UR28, !UPT;"
        "[7:0:{}:12:1]"
    )


def _tail(block_words: int) -> list[str]:
    return [
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(dealloc_done);[7:7:{}:5:0]",
        f"    #!tmem_dealloc_1cta(UR5, {block_words})",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    #def_label(dealloc_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]


def mask_source(name: str, mask: str) -> str:
    lines = _common_setup(name, 32) + _set_mask(mask)
    # Clear columns 0..7 independently in all four chunks.
    lines += [
        f"    MOV R{reg}, RZ;[7:7:{{}}:5:1]" for reg in range(24, 32)
    ] + [
        # mask mode launches exactly four warps, one per TMEM chunk.
        f"    STTM.x8 tmem[UR10], {_group(24, 8)};[7:7:{{}}:1:0]",
        "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P2, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P2 BRA #label(mask_mma);[7:7:{}:5:0]",
        "    BRA #label(mask_mma_done);[7:7:{}:5:0]",
        "    #def_label(mask_mma)",
        _mma(),
        "    UMOV UR18, 0x600;[7:7:{}:5:1]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    #def_label(mask_mma_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P3, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @!P3 BRA #label(mask_export_done);[7:7:{}:5:0]",
        f"    LDTM.x8 {_group(40, 8)}, tmem[UR10];[2:7:{{}}:1:0]",
        "    IMAD.WIDE.U32 {R8,R9}, R4, 0x20, {R2,R3};[7:7:{0}:5:1]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}], {_group(40, 4)};"
        "[7:0:{2}:1:0]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}+0x10], {_group(44, 4)};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    #def_label(mask_export_done)",
    ]
    lines += _tail(32)
    return "\n".join(lines)


def _clock_wait(label: str, phase: int) -> list[str]:
    return [
        f"    IADD3 R31, R30, {phase}, RZ;[7:7:{{}}:5:1]",
        f"    #def_label({label})",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P3, PT, R32, R31, PT;[7:7:{}:13:1]",
        f"    @P3 BRA #label({label});[7:7:{{}}:5:1]",
    ]


def collision_source(name: str, mma_half: str, sttm_half: str, column: int,
                     phase: int, sttm_count: int, client: str = "sttm") -> str:
    lines = _common_setup(name, 32) + _set_mask(mma_half) + [
        "    MOV32I R24, 0x51515151;[7:7:{}:5:1]",
        "    MOV R25, R24;[7:7:{}:5:1]",
        # Warp 0 publishes a future common epoch.
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    ISETP.EQ.AND P1, PT, R6, RZ, P0;[7:7:{}:13:1]",
        "    @P1 CS2R {R30,R31}, SR_CLOCKLO;[0:7:{}:5:1]",
        # Leave enough headroom for the CTA barrier even on a cold launch.
        "    @P1 IADD3 R30, R30, 0x100000, RZ;[7:7:{0}:5:1]",
        "    @P1 STS [RZ+0x700], R30;[7:7:{}:1:0]",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R30, [RZ+0x700];[0:7:{}:1:0]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{0}:13:1]",
        "    @P0 BRA #label(collision_mma);[7:7:{}:5:0]",
        "    ISETP.EQ.AND P1, PT, R5, 0x1, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(collision_sttm);[7:7:{}:5:0]",
        "    BRA #label(collision_done);[7:7:{}:5:0]",
        "    #def_label(collision_mma)",
    ]
    lines += _clock_wait("mma_wait", 0)
    lines += [
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]",
        _mma(),
        "    UMOV UR18, 0x600;[7:7:{}:5:1]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    @P1 STG.E.64.STRONG.GPU [{R2,R3}], {R16,R17};[7:0:{}:1:0]",
        "    @P1 STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R18,R19};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    BRA #label(collision_done);[7:7:{}:5:0]",
        "    #def_label(collision_sttm)",
    ]
    lines += _clock_wait("sttm_wait", 0)
    # The exported clocks, not this nominal count, are the experiment's x
    # axis.  Straight-line NOPs avoid relying on a cross-warp clock-spin loop
    # whose predicate dependency proved ineffective on B200.
    lines += ["    NOP;[7:7:{}:1:0]"] * phase
    lines += ["    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]"]
    half = 't0_t15' if sttm_half == 'lower' else 't16_t31'
    if client == "sttm":
        lines += [
            f"    STTM.16dp32bit_{half}.x2 "
            f"tmem[UR10+{column:#x}], {{R24,R25}};[7:7:{{}}:1:0]"
            for _ in range(sttm_count)
        ] + [
            "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
            f"    LDTM.16dp32bit_{half}.x2 "
            f"{{R40,R41}}, tmem[UR10+{column:#x}];[2:7:{{}}:1:0]",
            "    NOP;[7:7:{2}:1:0]",
        ]
    elif client == "ldtm":
        lines += [
            f"    LDTM.16dp32bit_{half}.x2 "
            f"{{R40,R41}}, tmem[UR10+{column:#x}];[2:7:{{}}:1:0]",
            "    NOP;[7:7:{2}:1:0]",
        ]
    else:
        raise ValueError(f"unknown collision client: {client}")
    lines += [
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P2, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P2 STG.E.64.STRONG.GPU [{R2,R3}+0x10], {R16,R17};"
        "[7:0:{}:1:0]",
        "    @P2 STG.E.64.STRONG.GPU [{R2,R3}+0x18], {R18,R19};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    #def_label(collision_done)",
    ]
    lines += _tail(32)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("mask", "collision"), required=True)
    ap.add_argument("--mask",
                    choices=("all", "none", "lower", "upper", "word0",
                             "word1", "word2", "word3"), default="lower")
    ap.add_argument("--column", type=int, choices=(8, 10), default=8)
    ap.add_argument("--phase", type=int, default=0)
    ap.add_argument("--sttm-half", choices=("lower", "upper"),
                    default="lower")
    ap.add_argument("--sttm-count", type=int, default=1)
    ap.add_argument("--client", choices=("sttm", "ldtm"), default="sttm")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    if ns.mode == "collision" and ns.mask not in ("lower", "upper"):
        ap.error("collision mode requires --mask lower or upper")
    if ns.sttm_count < 1:
        ap.error("--sttm-count must be positive")
    name = (f"utchmma_mask_{ns.mask}" if ns.mode == "mask" else
            f"utchmma_bank_m{ns.mask}_s{ns.sttm_half}_c{ns.column}_"
            f"p{ns.phase}_n{ns.sttm_count}_{ns.client}")
    src = (mask_source(name, ns.mask) if ns.mode == "mask" else
           collision_source(name, ns.mask, ns.sttm_half, ns.column,
                            ns.phase, ns.sttm_count, ns.client))
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
