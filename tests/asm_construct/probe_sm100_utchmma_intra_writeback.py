#!/usr/bin/env python3
"""Capture spatially partial writeback from one M128N128 UTCHMMA.

Observer warp 1 first zeros its own 32-row TMEM chunk across all 128 D columns
with eight STTM.x16 operations.  After a CTA barrier, warp 0 submits one
overwrite UTCHMMA while the observer repeatedly snapshots columns 0..15 with
LDTM.x16.  Lane 0 exports every 16-column snapshot.  A mixture of 0.0 and
16.0 inside one snapshot exposes the intra-MMA writeback frontier; runs of two
columns test the proposed two-column retirement granularity.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _group(lo: int, count: int) -> str:
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def _emit_lds_contender(batches: int) -> list[str]:
    batch = [
        "    LDS.128 {R40,R41,R42,R43}, [R26];[0:7:{}:1:0]",
        "    LDS.128 {R44,R45,R46,R47}, [R26];[1:7:{}:1:0]",
        "    LDS.128 {R48,R49,R50,R51}, [R26];[2:7:{}:1:0]",
        "    NOP;[7:7:{0,1,2}:1:0]",
    ]
    return batch * batches


def _emit_reads(columns: list[int], capture_width: int,
                output_base: int = 0) -> list[str]:
    lines: list[str] = []
    if capture_width == 16:
        for sample, column in enumerate(columns):
            lines += [
                f"    LDTM.x16 {_group(32, 16)}, "
                f"tmem[UR10+{column:#x}];[0:7:{{0}}:1:0]",
            ]
            for quarter in range(4):
                req = "{0}" if quarter == 0 else "{}"
                lines += [
                    f"    @P0 STG.E.128.STRONG.GPU [{{R2,R3}}+"
                    f"{output_base + sample * 64 + quarter * 16:#x}], "
                    f"{_group(32 + quarter * 4, 4)};[7:7:{req}:1:0]"
                ]
        return lines

    # Submit all narrow reads before consuming any result, so STG does not
    # perturb the temporal sampling interval.  SB3--SB5 remain globally
    # unused for the allocator builtin's internal protocol.
    for sample, column in enumerate(columns):
        base = 32 + sample * capture_width
        suffix = ".x2" if capture_width == 2 else ""
        operand = (_group(base, capture_width)
                   if capture_width > 1 else f"R{base}")
        lines += [
            f"    LDTM{suffix} {operand}, tmem[UR10+{column:#x}];"
            f"[{sample}:7:{{}}:1:0]"
        ]
    for sample in range(len(columns)):
        base = 32 + sample * capture_width
        size = ".64" if capture_width == 2 else ""
        operand = (_group(base, capture_width)
                   if capture_width > 1 else f"R{base}")
        lines += [
            f"    @P0 STG.E{size}.STRONG.GPU [{{R2,R3}}+"
            f"{output_base + sample * capture_width * 4:#x}], "
            f"{operand};[7:7:{{{sample}}}:1:0]"
        ]
    return lines


def source(name: str, samples: int, observer_warp: int,
           sample_column: int, capture_width: int,
           producer_delay: int, producer_phase_stall: int = 0,
           sample_stride: int = 0, dual_order: bool = False,
           dual_order_swap: bool = False,
           producer_phase_nops: int = 1,
           lds_batches: int = 0) -> str:
    if not 1 <= samples <= 32:
        raise ValueError("samples must be 1..32")
    if capture_width not in (1, 2, 16):
        raise ValueError("capture_width must be 1, 2, or 16")
    columns = [sample_column + sample * sample_stride
               for sample in range(samples)]
    if any(column < 0 or column + capture_width > 128
           for column in columns):
        raise ValueError("every sampled column range must lie within 0..127")
    if capture_width in (1, 2) and samples > 3:
        raise ValueError("x1/x2 bursts leave three SBs for allocator builtins")
    if dual_order and (capture_width != 2 or samples != 3):
        raise ValueError("dual_order currently requires three x2 samples")
    if not 0 <= producer_phase_stall <= 15:
        raise ValueError("producer_phase_stall must be 0 (disabled) or 1..15")
    if not 1 <= producer_phase_nops <= 16:
        raise ValueError("producer_phase_nops must be 1..16")
    if lds_batches < 0:
        raise ValueError("lds_batches must be non-negative")
    output_bytes = (0x100 if dual_order else samples * capture_width * 4)
    timer_base = (output_bytes + 7) & ~7

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
        "    SHL R26, R6, 0x4;[7:7:{}:5:1]",
        "    MOV32I R20, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV R21, R20;[7:7:{}:5:1]",
        "    MOV R22, R20;[7:7:{}:5:1]",
        "    MOV R23, R20;[7:7:{}:5:1]",
    ]
    # Exactly 64 threads: four 1-KiB stripes make each 4-KiB operand tile.
    for off in (0x800, 0xC00, 0x1000, 0x1400,
                0x1800, 0x1C00, 0x2000, 0x2400):
        lines += [
            f"    STS.128 [R12+{off:#x}], {{R20,R21,R22,R23}};"
            "[7:7:{}:1:0]"
        ]
    lines += [
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_wait);[7:7:{}:5:0]",
        "    #!tmem_alloc_1cta(UR5, 512)",
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
        "    UMOV UR15, 0x8200490;[7:7:{}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
    ]
    for reg in range(32, 48):
        lines += [f"    MOV R{reg}, RZ;[7:7:{{}}:5:1]"]
    if dual_order:
        lines += [
            "    ISETP.NE.AND P2, PT, R5, RZ, PT;[7:7:{}:13:1]",
            "    @!P2 BRA #label(zero_done);[7:7:{}:5:0]",
        ]
    else:
        lines += [
            f"    ISETP.EQ.AND P2, PT, R5, {observer_warp:#x}, PT;"
            "[7:7:{}:13:1]",
            "    @!P2 BRA #label(zero_done);[7:7:{}:5:0]",
        ]
    for column in range(0, 128, 16):
        lines += [
            f"    STTM.x16 tmem[UR10+{column:#x}], {_group(32, 16)};"
            "[7:7:{}:1:0]"
        ]
    lines += [
        "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
        "    #def_label(zero_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P1, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(producer);[7:7:{}:5:0]",
    ]
    if dual_order:
        lines += [
            "    ISETP.EQ.AND P2, PT, R5, 0x1, PT;[7:7:{}:13:1]",
            "    @P2 BRA #label(observer_dual);[7:7:{}:5:0]",
            "    ISETP.EQ.AND P2, PT, R5, 0x2, PT;[7:7:{}:13:1]",
            "    @P2 BRA #label(observer_dual);[7:7:{}:5:0]",
        ]
    else:
        lines += [
            f"    ISETP.EQ.AND P2, PT, R5, {observer_warp:#x}, PT;"
            "[7:7:{}:13:1]",
            "    @P2 BRA #label(observer);[7:7:{}:5:0]",
        ]
    if lds_batches:
        lines += [
            "    ISETP.GE.U32.AND P2, PT, R5, 0x2, PT;[7:7:{}:13:1]",
            "    ISETP.LE.U32.AND P2, PT, R5, 0x5, P2;[7:7:{}:13:1]",
            "    @P2 BRA #label(lds_contender);[7:7:{}:5:0]",
        ]
    lines += [
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(producer)",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if producer_phase_stall:
        # Keep instruction addresses and fetch layout identical throughout a
        # phase sweep.  Only this NOP's scheduler stall changes.  The other
        # 15 NOPs give every generated variant the same 16-instruction pad.
        # (stall=0 is a drain encoding, so 0 means this mode is disabled.)
        lines += [f"    NOP;[7:7:{{}}:{producer_phase_stall}:1]"] * producer_phase_nops
        lines += ["    NOP;[7:7:{}:1:0]"] * (16 - producer_phase_nops)
    else:
        lines += ["    NOP;[7:7:{}:1:0]"] * producer_delay
    lines += [
        "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
        "tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, !UPT;"
        "[7:0:{}:12:1]",
        "    UMOV UR18, 0x600;[7:7:{}:5:1]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    STG.E.64.STRONG.GPU [{{R2,R3}}+{timer_base:#x}], "
        "{R16,R17};[7:0:{}:8:0]",
        f"    STG.E.64.STRONG.GPU [{{R2,R3}}+{timer_base + 8:#x}], "
        "{R18,R19};[7:1:{0}:8:0]",
        "    BRA #label(work_done);[7:7:{1}:5:0]",
    ]
    if dual_order:
        forward = columns
        reverse = list(reversed(columns))
        true_columns, false_columns = forward, reverse
        forward_warp = 2 if dual_order_swap else 1
        lines += [
            "    #def_label(observer_dual)",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    ISETP.EQ.AND P3, PT, R5, 0x2, PT;[7:7:{}:13:1]",
            "    @P3 IADD3 R2, R2, 0x40, RZ;[7:7:{}:5:1]",
            "    R2UR UR29, R5;[7:7:{}:13:1]",
            f"    UISETP.EQ.AND UP0, UPT, UR29, {forward_warp:#x}, UPT;"
            "[7:7:{}:5:1]",
        ]
        for i, (true_column, false_column) in enumerate(
                zip(true_columns, false_columns)):
            lines += [
                f"    @UP0 UIADD3 UR{30 + i}, UPT, UPT, UR10, "
                f"{true_column:#x}, URZ;[7:7:{{}}:1:1]",
                f"    @!UP0 UIADD3 UR{30 + i}, UPT, UPT, UR10, "
                f"{false_column:#x}, URZ;[7:7:{{}}:1:1]",
            ]
        for sample in range(3):
            base = 32 + sample * 2
            lines += [
                f"    LDTM.x2 {_group(base, 2)}, tmem[UR{30 + sample}];"
                f"[{sample}:7:{{}}:1:0]"
            ]
        for sample in range(3):
            base = 32 + sample * 2
            lines += [
                f"    @P0 STG.E.64.STRONG.GPU [{{R2,R3}}+{sample * 8:#x}], "
                f"{_group(base, 2)};[7:7:{{{sample}}}:1:0]"
            ]
    else:
        lines += [
            "    #def_label(observer)",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
        ]
        lines += _emit_reads(columns, capture_width, 0)
    if lds_batches:
        lines += ["    BRA #label(work_done);[7:7:{}:5:0]",
                  "    #def_label(lds_contender)"]
        lines += _emit_lds_contender(lds_batches)
    lines += [
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
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--observer-warp", type=int, default=1)
    ap.add_argument("--sample-column", type=int, default=0)
    ap.add_argument("--capture-width", type=int, choices=(1, 2, 16), default=16)
    ap.add_argument("--sample-stride", type=int, default=0)
    ap.add_argument("--dual-order", action="store_true",
                    help="warp1/2 read forward/reverse column orders")
    ap.add_argument("--dual-order-swap", action="store_true",
                    help="swap forward/reverse assignments between warp1/2")
    ap.add_argument("--producer-delay", type=int, default=0)
    ap.add_argument(
        "--producer-phase-stall", type=int, default=0,
        help="fixed-layout producer pad; vary one NOP stall over 1..15")
    ap.add_argument("--producer-phase-nops", type=int, default=1,
                    help="number of the 16 fixed-layout NOPs using phase stall")
    ap.add_argument("--lds-batches", type=int, default=0,
                    help="enable four warp2..5 LDS.128 contenders")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    timing = (f"ps{ns.producer_phase_stall}n{ns.producer_phase_nops}"
              if ns.producer_phase_stall
              else f"d{ns.producer_delay}")
    stride_name = (f"n{-ns.sample_stride}" if ns.sample_stride < 0
                   else str(ns.sample_stride))
    name = (f"utchmma_intra_s{ns.samples}_w{ns.observer_warp}"
            f"_c{ns.sample_column}_q{stride_name}_x{ns.capture_width}_"
            f"{timing}"
            f"{'_dual_swap' if ns.dual_order_swap else '_dual' if ns.dual_order else ''}"
            f"{'_lds' + str(ns.lds_batches) if ns.lds_batches else ''}")
    src = source(name, ns.samples, ns.observer_warp, ns.sample_column,
                 ns.capture_width, ns.producer_delay,
                 ns.producer_phase_stall, ns.sample_stride,
                 ns.dual_order or ns.dual_order_swap,
                 ns.dual_order_swap, ns.producer_phase_nops,
                 ns.lds_batches)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
