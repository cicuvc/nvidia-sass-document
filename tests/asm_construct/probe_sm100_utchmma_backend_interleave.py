#!/usr/bin/env python3
"""Observe whether an N8 UTCHMMA can interleave N256's two N128 waves."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _idesc(n: int) -> int:
    return ((1 << 4) | (1 << 7) | (1 << 10)
            | ((n >> 3) << 17) | (8 << 24))


def source(name: str, sequence: tuple[int, int], read_order: tuple[int, int, int],
           rounds: int, delays: tuple[int, int] = (0, 0)) -> str:
    if sorted(sequence) != [8, 256]:
        raise ValueError("sequence must contain N256 and N8")
    if sorted(read_order) != [0, 128, 256]:
        raise ValueError("read_order must be a permutation of 0,128,256")
    if len(delays) != 2 or min(delays) < 0:
        raise ValueError("delays must contain two non-negative NOP counts")
    sample_bytes = rounds * 3 * 4
    timer_base = (sample_bytes + 7) & ~7
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
        "    MOV32I R20, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV R21, R20;[7:7:{}:5:1]",
        "    MOV R22, R20;[7:7:{}:5:1]",
        "    MOV R23, R20;[7:7:{}:5:1]",
    ]
    # Fill A plus the full 8-KiB N256 B footprint with BF16 1.0.
    for off in range(0x800, 0x3800, 0x400):
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
        "    #!mbarrier_init(UR18, 2)",
        "    #def_label(setup_wait)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        # UTCHMMA's D operand has no encoded immediate.  Spell the disjoint
        # N8 destination as a separately computed TMEM address; writing
        # tmem[UR10+0x100] here is accepted by the generic parser but the
        # offset is not represented in the instruction encoding.
        "    UIADD3 UR11, UPT, UPT, UR10, 0x100, URZ;[7:7:{}:5:1]",
        "    UMOV UR20, 0x100080;[7:7:{}:1:0]",
        "    UMOV UR21, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR22, 0x100180;[7:7:{}:1:0]",
        "    UMOV UR23, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR14, 0x0;[7:7:{}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
    ]
    for reg in range(32, 48):
        lines += [f"    MOV R{reg}, RZ;[7:7:{{}}:5:1]"]
    lines += [
        "    ISETP.EQ.AND P2, PT, R5, 0x2, PT;[7:7:{}:13:1]",
        "    @!P2 BRA #label(zero_done);[7:7:{}:5:0]",
    ]
    for column in range(0, 272, 16):
        lines += [
            f"    STTM.x16 tmem[UR10+{column:#x}], "
            "{R32,R33,R34,R35,R36,R37,R38,R39,R40,R41,R42,R43,R44,R45,R46,R47};"
            "[7:7:{}:1:0]"
        ]
    lines += [
        "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
        "    #def_label(zero_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P1, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(producer0);[7:7:{}:5:0]",
        "    ISETP.EQ.AND P2, PT, R5, 0x1, PT;[7:7:{}:13:1]",
        "    @P2 BRA #label(producer1);[7:7:{}:5:0]",
        "    ISETP.EQ.AND P2, PT, R5, 0x2, PT;[7:7:{}:13:1]",
        "    @P2 BRA #label(observer);[7:7:{}:5:0]",
        "    BRA #label(work_done);[7:7:{}:5:0]",
    ]
    for index, n in enumerate(sequence):
        dreg = 10 if n == 256 else 11
        lines += [
            f"    #def_label(producer{index})",
            f"    UMOV UR15, {_idesc(n):#x};[7:7:{{}}:1:0]",
        ]
        # Delay the frontend arrival of either producer without consuming TC,
        # shared-memory, or TMEM resources.  Each NOP carries eight scheduler
        # stall cycles; CS2R is deliberately after the delay and immediately
        # before the UTCHMMA so it timestamps the resulting arrival order.
        lines += ["    NOP;[7:7:{}:8:1]"] * delays[index]
        lines += [
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
            f"tmem[UR{dreg}], tmem[UR14], "
            "idesc[{UR15,UR16}], URZ, !UPT;"
            "[7:0:{}:12:1]",
            "    UMOV UR18, 0x600;[7:7:{}:5:1]",
            "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
            "    #!mbarrier_wait(UR18, 0)",
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            f"    STG.E.64.STRONG.GPU [{{R2,R3}}+"
            f"{timer_base + index * 16:#x}], {{R16,R17}};[7:0:{{}}:8:0]",
            f"    STG.E.64.STRONG.GPU [{{R2,R3}}+"
            f"{timer_base + index * 16 + 8:#x}], {{R18,R19}};"
            "[7:1:{0}:8:0]",
            "    BRA #label(work_done);[7:7:{1}:5:0]",
        ]
    lines += [
        "    #def_label(observer)",
        "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
    ]
    for rnd in range(rounds):
        for sample, column in enumerate(read_order):
            lines += [
                f"    LDTM R{32 + sample}, tmem[UR10+{column:#x}];"
                f"[{sample}:7:{{}}:1:0]"
            ]
        for sample in range(3):
            offset = (rnd * 3 + sample) * 4
            lines += [
                f"    @P0 STG.E.STRONG.GPU [{{R2,R3}}+{offset:#x}], "
                f"R{32 + sample};[7:7:{{{sample}}}:1:0]"
            ]
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
    ap.add_argument("--sequence", default="256,8")
    ap.add_argument("--read-order", default="0,128,256")
    ap.add_argument("--rounds", type=int, default=32)
    ap.add_argument("--delays", default="0,0",
                    help="producer0,producer1 counts of stall-8 NOPs")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    sequence = tuple(int(x, 0) for x in ns.sequence.split(","))
    read_order = tuple(int(x, 0) for x in ns.read_order.split(","))
    delays = tuple(int(x, 0) for x in ns.delays.split(","))
    seq_name = "_".join(map(str, sequence))
    read_name = "_".join(map(str, read_order))
    delay_name = "_".join(map(str, delays))
    name = (f"utchmma_ilv_s{seq_name}_r{read_name}_n{ns.rounds}"
            f"_d{delay_name}")
    src = source(name, sequence, read_order, ns.rounds, delays)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
