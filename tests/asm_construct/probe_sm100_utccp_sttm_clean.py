#!/usr/bin/env python3
"""Build clean B200 UTCCP.warpx4/STTM shared-write-backend probes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _utccp_ops(count: int) -> list[str]:
    return [
        "    UTCCP.T.S.4x32dp128bit tmem[UR10], "
        "gdesc[{UR12,UR13}];[7:7:{}:1:0]"
        for _ in range(count)
    ]


def _sttm_ops(count: int, column: int, width: int, layout: str,
              half_split_offset: int) -> list[str]:
    addr = "tmem[UR10]" if column == 0 else f"tmem[UR10+0x{column:x}]"
    if layout == "16x32bx2":
        upper_column = column + half_split_offset
        upper_addr = ("tmem[UR10]" if upper_column == 0 else
                      f"tmem[UR10+0x{upper_column:x}]")
        lines = []
        for _ in range(count):
            lines += [
                "    STTM.16dp32bit_t0_t15.x2 "
                f"{addr}, {{R24,R25}};[7:7:{{}}:1:0]",
                "    STTM.16dp32bit_t16_t31.x2 "
                f"{upper_addr}, {{R24,R25}};[7:7:{{}}:1:0]",
            ]
        return lines
    regs = ",".join(f"R{reg}" for reg in range(24, 24 + width))
    return [
        f"    STTM.x{width} {addr}, {{{regs}}};"
        "[7:7:{}:1:0]"
        for _ in range(count)
    ]


def _sttm_half_ops(count: int, upper: bool, column: int) -> list[str]:
    addr = "tmem[UR10]" if column == 0 else f"tmem[UR10+0x{column:x}]"
    half = "t16_t31" if upper else "t0_t15"
    return [
        f"    STTM.16dp32bit_{half}.x2 {addr}, {{R24,R25}};"
        "[7:7:{}:1:0]"
        for _ in range(count)
    ]


def source(name: str, mode: str, cp_batches: int, cp_ops: int,
           st_batches: int, st_ops: int, st_column: int, st_width: int,
           st_scope: str, st_layout: str,
           half_split_offset: int) -> str:
    with_cp = mode in ("cp", "mixed")
    with_st = mode in ("st", "mixed")
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma SHARED(0x2000)",
        "    #pragma NUM_MBARRIERS(1)",
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
        "    #!tmem_alloc_1cta(UR5, 32)",
    ]
    if with_cp:
        lines += [
            "    UMOV UR18, 0x600;[7:7:{}:1:0]",
            "    #!mbarrier_init(UR18, 4)",
        ]
    lines += [
        "    #def_label(setup_wait)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        "    UMOV UR12, 0x10090;[7:7:{}:1:0]",
        "    UMOV UR13, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR18, 0x600;[7:7:{}:1:0]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if with_cp:
        lines += [
            "    ISETP.LT.U32.AND P1, PT, R5, 0x4, PT;[7:7:{}:13:1]",
            "    @P1 BRA #label(cp_path);[7:7:{}:5:0]",
        ]
    if with_st:
        if st_scope == "chunk0":
            lines += [
                "    ISETP.EQ.AND P2, PT, R5, 0x4, PT;[7:7:{}:13:1]",
                "    ISETP.EQ.OR P2, PT, R5, 0x8, P2;[7:7:{}:13:1]",
            ]
        else:
            lines += [
                "    ISETP.GE.U32.AND P2, PT, R5, 0x4, PT;"
                "[7:7:{}:13:1]",
                "    ISETP.LE.U32.AND P2, PT, R5, 0xb, P2;"
                "[7:7:{}:13:1]",
            ]
        lines += ["    @P2 BRA #label(st_path);[7:7:{}:5:0]"]
    lines += ["    BRA #label(quiesce);[7:7:{}:5:0]"]

    if with_cp:
        lines += [
            "    #def_label(cp_path)",
            "    BSSY B0, #label(cp_join);[7:7:{}:1:0]",
            "    ISETP.NE.AND P3, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P3 BRA #label(cp_join);[7:7:{}:5:0]",
            f"    MOV32I R20, {cp_batches:#x};[7:7:{{}}:5:1]",
            "    #def_label(cp_loop)",
        ] + _utccp_ops(cp_ops) + [
            "    IADD3 R20, R20, -0x1, RZ;[7:7:{}:5:1]",
            "    ISETP.NE.AND P4, PT, R20, RZ, PT;[7:7:{}:13:1]",
            "    @P4 BRA #label(cp_loop);[7:7:{}:5:0]",
            "    UTCBAR.1CTA [UR18], URZ;[7:0:{0}:12:1]",
            "    #def_label(cp_join)",
            "    BSYNC B0;[7:7:{}:5:0]",
            "    #!mbarrier_wait(UR18, 0)",
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    BRA #label(record);[7:7:{}:5:0]",
        ]

    if with_st:
        if st_layout == "16x32bx2_independent":
            lines += [
                "    #def_label(st_path)",
                "    ISETP.EQ.AND P5, PT, R5, 0x4, PT;"
                "[7:7:{}:13:1]",
                "    @P5 BRA #label(st_lower);[7:7:{}:5:0]",
                "    BRA #label(st_upper);[7:7:{}:5:0]",
                "    #def_label(st_lower)",
                f"    MOV32I R20, {st_batches:#x};[7:7:{{}}:5:1]",
                "    #def_label(st_lower_loop)",
            ] + _sttm_half_ops(st_ops, False, st_column) + [
                "    IADD3 R20, R20, -0x1, RZ;[7:7:{}:5:1]",
                "    ISETP.NE.AND P4, PT, R20, RZ, PT;"
                "[7:7:{}:13:1]",
                "    @P4 BRA #label(st_lower_loop);[7:7:{}:5:0]",
                "    BRA #label(st_finish);[7:7:{}:5:0]",
                "    #def_label(st_upper)",
                f"    MOV32I R20, {st_batches:#x};[7:7:{{}}:5:1]",
                "    #def_label(st_upper_loop)",
            ] + _sttm_half_ops(
                st_ops, True, st_column + half_split_offset) + [
                "    IADD3 R20, R20, -0x1, RZ;[7:7:{}:5:1]",
                "    ISETP.NE.AND P4, PT, R20, RZ, PT;"
                "[7:7:{}:13:1]",
                "    @P4 BRA #label(st_upper_loop);[7:7:{}:5:0]",
                "    #def_label(st_finish)",
                "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
                "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
                "    BRA #label(record);[7:7:{}:5:0]",
            ]
        else:
            lines += [
                "    #def_label(st_path)",
                f"    MOV32I R20, {st_batches:#x};[7:7:{{}}:5:1]",
                "    #def_label(st_loop)",
            ] + _sttm_ops(st_ops, st_column, st_width, st_layout,
                          half_split_offset) + [
                "    IADD3 R20, R20, -0x1, RZ;[7:7:{}:5:1]",
                "    ISETP.NE.AND P4, PT, R20, RZ, PT;[7:7:{}:13:1]",
                "    @P4 BRA #label(st_loop);[7:7:{}:5:0]",
                "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
                "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
                "    BRA #label(record);[7:7:{}:5:0]",
            ]

    lines += [
        "    #def_label(record)",
        "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
        "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
        "    BRA #label(quiesce);[7:7:{1}:5:0]",
        "    #def_label(quiesce)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(dealloc_done);[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 32)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    #def_label(dealloc_done)",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("cp", "st", "mixed"), required=True)
    ap.add_argument("--cp-batches", type=int, default=64)
    ap.add_argument("--cp-ops", type=int, default=16)
    ap.add_argument("--st-batches", type=int, default=256)
    ap.add_argument("--st-ops", type=int, default=16)
    ap.add_argument("--st-column", type=int, choices=range(16), default=0)
    ap.add_argument("--st-width", type=int, choices=(4, 8), default=8)
    ap.add_argument("--st-layout", choices=(
        "32x32b", "16x32bx2", "16x32bx2_independent"),
                    default="32x32b")
    ap.add_argument("--half-split-offset", type=int, default=16)
    ap.add_argument("--st-scope", choices=("chunk0", "all"),
                    default="chunk0")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    suffix = "all" if ns.st_scope == "all" else "c0"
    layout_tag = (f"hi{ns.half_split_offset}" if
                  ns.st_layout == "16x32bx2_independent" else
                  f"hs{ns.half_split_offset}" if
                  ns.st_layout == "16x32bx2" else f"x{ns.st_width}")
    name = f"clean_{ns.mode}_{layout_tag}_{suffix}_o{ns.st_column}"
    src = source(name, ns.mode, ns.cp_batches, ns.cp_ops,
                 ns.st_batches, ns.st_ops, ns.st_column, ns.st_width,
                 ns.st_scope, ns.st_layout, ns.half_split_offset)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
