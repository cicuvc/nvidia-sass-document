#!/usr/bin/env python3
"""Probe when one M128N256 UTCHMMA consumes each RHS shared-memory stripe.

Warp 0 issues one overwrite BF16/BF16->FP32 UTCHMMA.  Warps 1 and 2 replace
one 1-KiB stripe of the 8-KiB RHS tile (BF16 1.0 -> 2.0) at a separately
scheduled clock target.  The kernel exports lane 0's 256 FP32 accumulator
values plus the actual issue/store timestamps, allowing runs to be grouped by
the measured mutation-minus-MMA time rather than nominal delay alone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _group(lo: int, count: int) -> str:
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def _idesc(n: int) -> int:
    return ((1 << 4) | (1 << 7) | (1 << 10)
            | ((n >> 3) << 17) | (8 << 24))


def _clock_wait(label: str, delay: int) -> list[str]:
    return [
        f"    IADD3 R31, R30, {delay:#x}, RZ;[7:7:{{}}:5:1]",
        f"    #def_label({label})",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P3, PT, R32, R31, PT;[7:7:{}:13:1]",
        f"    @P3 BRA #label({label});[7:7:{{}}:5:1]",
    ]


def source(name: str, stripe: int, producer_delay: int,
           modifier_delay: int) -> str:
    if not 0 <= stripe < 8:
        raise ValueError("stripe must be in 0..7")
    if min(producer_delay, modifier_delay) < 0:
        raise ValueError("delays must be non-negative")

    b_stripe = 0x1800 + stripe * 0x400
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(0x4000)",
        "    #pragma NUM_MBARRIERS(1)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]",
        "    SHL R12, R4, 0x4;[7:7:{}:5:1]",
        "    IADD3 R28, R12, -0x200, RZ;[7:7:{}:5:1]",
        "    MOV32I R20, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV R21, R20;[7:7:{}:5:1]",
        "    MOV R22, R20;[7:7:{}:5:1]",
        "    MOV R23, R20;[7:7:{}:5:1]",
        "    MOV32I R24, 0x40004000;[7:7:{}:5:1]",
        "    MOV R25, R24;[7:7:{}:5:1]",
        "    MOV R26, R24;[7:7:{}:5:1]",
        "    MOV R27, R24;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P4, PT, R4, 0x40, PT;[7:7:{}:13:1]",
    ]
    # A is 4 KiB at 0x800; the N256 B tile is 8 KiB at 0x1800.
    for off in range(0x800, 0x3800, 0x400):
        lines += [
            f"    @P4 STS.128 [R12+{off:#x}], {{R20,R21,R22,R23}};"
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
        f"    UMOV UR15, {_idesc(256):#x};[7:7:{{}}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
        # Warp 0 publishes a comfortably future clock target.
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    ISETP.EQ.AND P1, PT, R6, RZ, P0;[7:7:{}:13:1]",
        "    @P1 CS2R {R30,R31}, SR_CLOCKLO;[3:7:{}:5:1]",
        "    @P1 IADD3 R30, R30, 0x800, RZ;[7:7:{3}:5:1]",
        "    @P1 STS [RZ+0x700], R30;[7:7:{}:1:0]",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R30, [RZ+0x700];[0:7:{}:1:0]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{0}:13:1]",
        "    @P0 BRA #label(producer);[7:7:{}:5:0]",
        "    ISETP.LE.U32.AND P1, PT, R5, 0x2, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(modifier);[7:7:{}:5:0]",
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(producer)",
    ]
    lines += _clock_wait("producer_wait", producer_delay)
    lines += [
        "    CS2R {R34,R35}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
        "tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, !UPT;"
        "[7:0:{}:12:1]",
        "    UMOV UR18, 0x600;[7:7:{}:5:1]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R36,R37}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    @P1 STG.E.64.STRONG.GPU [{R2,R3}+0x400], {R34,R35};"
        "[7:0:{}:1:0]",
        "    @P1 STG.E.64.STRONG.GPU [{R2,R3}+0x408], {R36,R37};"
        "[7:1:{0}:1:0]",
    ]
    # Export lane 0's 256 accumulator columns in 16-column chunks.
    for column in range(0, 256, 16):
        lines += [
            f"    LDTM.x16 {_group(40, 16)}, tmem[UR10+{column:#x}];"
            "[5:7:{}:1:0]",
        ]
        for quarter in range(4):
            req = "{5}" if quarter == 0 else "{}"
            lines += [
                f"    @P1 STG.E.128.STRONG.GPU [{{R2,R3}}+"
                f"{column * 4 + quarter * 16:#x}], "
                f"{_group(40 + quarter * 4, 4)};"
                f"[7:{quarter}:{req}:1:0]"
            ]
        lines += ["    NOP;[7:7:{0,1,2,3}:1:0]"]
    lines += [
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(modifier)",
    ]
    lines += _clock_wait("modifier_wait", modifier_delay)
    lines += [
        "    CS2R {R34,R35}, SR_CLOCKLO;[7:7:{}:5:1]",
        f"    STS.128 [R28+{b_stripe:#x}], {{R24,R25,R26,R27}};"
        "[7:7:{}:1:0]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    CS2R {R36,R37}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    SHL R38, R5, 0x4;[7:7:{}:5:1]",
        "    IADD3 R38, R38, 0x410, RZ;[7:7:{}:5:1]",
        "    IADD3 R39, R2, R38, RZ;[7:7:{}:5:1]",
        "    @P1 STG.E.64.STRONG.GPU [{R39,R3}], {R34,R35};[7:0:{}:1:0]",
        "    @P1 STG.E.64.STRONG.GPU [{R39,R3}+0x8], {R36,R37};"
        "[7:1:{0}:1:0]",
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
    ap.add_argument("--stripe", type=int, default=0)
    ap.add_argument("--producer-delay", type=int, default=0x100)
    ap.add_argument("--modifier-delay", type=int, default=0)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    name = (f"utchmma_rhs_s{ns.stripe}_p{ns.producer_delay}_"
            f"m{ns.modifier_delay}")
    src = source(name, ns.stripe, ns.producer_delay, ns.modifier_delay)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
