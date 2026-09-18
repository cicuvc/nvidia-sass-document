#!/usr/bin/env python3
"""Observe the warp arbitration quantum of the B200 UTCHMMA backend.

Warp 0 and warp 1 each issue an equal stream of M128N8K16 accumulate
UTCHMMAs to private TMEM destinations.  Warp 2 repeatedly samples one column
from each destination.  With BF16-one inputs every retirement increments the
visible FP32 value by 16, exposing the cross-warp instruction order without
putting a UTCBAR between individual operations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


IDESC_N8 = ((1 << 4) | (1 << 7) | (1 << 10) | (1 << 17) | (8 << 24))


def source(name: str, count: int, delays: tuple[int, int]) -> str:
    if count < 1 or len(delays) != 2 or min(delays) < 0:
        raise ValueError("count must be positive and delays must be two non-negative counts")
    rounds = max(128, count * 24)
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
    for off in range(0x800, 0x2800, 0x400):
        lines.append(
            f"    STS.128 [R12+{off:#x}], {{R20,R21,R22,R23}};[7:7:{{}}:1:0]")
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
        "    UIADD3 UR11, UPT, UPT, UR10, 0x80, URZ;[7:7:{}:5:1]",
        "    UMOV UR20, 0x100080;[7:7:{}:1:0]",
        "    UMOV UR21, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR22, 0x100180;[7:7:{}:1:0]",
        "    UMOV UR23, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR14, 0x0;[7:7:{}:1:0]",
        f"    UMOV UR15, {IDESC_N8:#x};[7:7:{{}}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
    ]
    for reg in range(32, 48):
        lines.append(f"    MOV R{reg}, RZ;[7:7:{{}}:5:1]")
    lines += [
        "    ISETP.EQ.AND P2, PT, R5, 0x2, PT;[7:7:{}:13:1]",
        "    @!P2 BRA #label(zero_done);[7:7:{}:5:0]",
        "    STTM.x16 tmem[UR10], {R32,R33,R34,R35,R36,R37,R38,R39,R40,R41,R42,R43,R44,R45,R46,R47};[7:7:{}:1:0]",
        "    STTM.x16 tmem[UR10+0x80], {R32,R33,R34,R35,R36,R37,R38,R39,R40,R41,R42,R43,R44,R45,R46,R47};[7:7:{}:1:0]",
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
    for producer in range(2):
        dreg = 10 + producer
        lines.append(f"    #def_label(producer{producer})")
        lines += ["    NOP;[7:7:{}:8:1]"] * delays[producer]
        lines.append("    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]")
        for _ in range(count):
            lines.append(
                "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
                f"tmem[UR{dreg}], tmem[UR14], idesc[{{UR15,UR16}}], "
                "URZ, UPT;[7:0:{}:12:1]")
        lines += [
            "    UMOV UR18, 0x600;[7:7:{}:5:1]",
            "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
            "    #!mbarrier_wait(UR18, 0)",
            "    BRA #label(work_done);[7:7:{}:5:0]",
        ]
    lines += [
        "    #def_label(observer)",
        "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
    ]
    for rnd in range(rounds):
        lines += [
            "    LDTM R32, tmem[UR10];[0:7:{}:1:0]",
            "    LDTM R33, tmem[UR10+0x80];[1:7:{}:1:0]",
            f"    @P0 STG.E.STRONG.GPU [{{R2,R3}}+{rnd * 8:#x}], R32;[7:7:{{0}}:1:0]",
            f"    @P0 STG.E.STRONG.GPU [{{R2,R3}}+{rnd * 8 + 4:#x}], R33;[7:7:{{1}}:1:0]",
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
    ap.add_argument("--count", type=int, default=8)
    ap.add_argument("--delays", default="0,0")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    delays = tuple(int(x, 0) for x in ns.delays.split(","))
    name = f"utchmma_quantum_c{ns.count}_d{delays[0]}_{delays[1]}"
    src = source(name, ns.count, delays)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
