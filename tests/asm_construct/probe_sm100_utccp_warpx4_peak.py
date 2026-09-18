#!/usr/bin/env python3
"""Build a clean four-warp UTCCP.warpx4 peak-throughput probe for B200."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def source(name: str, batches: int, ops_per_batch: int,
           schedule: str, warps: int) -> str:
    if schedule not in ("serial", "none", "round3"):
        raise ValueError(schedule)
    ops: list[str] = []
    for i in range(ops_per_batch):
        if schedule == "serial":
            sched = "[7:0:{0}:12:1]"
        elif schedule == "none":
            sched = "[7:7:{}:1:0]"
        else:
            # Keep three scoreboards globally free for the allocator builtin.
            sb = i % 3
            sched = f"[7:{sb}:{{{sb}}}:1:0]"
        ops.append(
            "    UTCCP.T.S.4x32dp128bit tmem[UR10], "
            f"gdesc[{{UR12,UR13}}];{sched}")

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
        "    UMOV UR18, 0x600;[7:7:{}:1:0]",
        f"    #!mbarrier_init(UR18, {warps})",
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
        "    BSSY B0, #label(cp_join);[7:7:{}:1:0]",
        "    ISETP.NE.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(cp_join);[7:7:{}:5:0]",
        f"    UMOV UR20, {batches:#x};[7:7:{{}}:1:0]",
        "    #def_label(cp_loop)",
    ] + ops + [
        "    UIADD3 UR20, UPT, UPT, UR20, -0x1, URZ;[7:7:{}:5:1]",
        "    UISETP.NE.AND UP0, UPT, UR20, URZ, UPT;[7:7:{}:1:0]",
        "    BRA.U UP0, #label(cp_loop);[7:7:{}:5:0]",
        ("    UTCBAR.1CTA [UR18], URZ;[7:0:{0,1,2}:12:1]"
         if schedule == "round3" else
         "    UTCBAR.1CTA [UR18], URZ;[7:0:{0}:12:1]"),
        "    #def_label(cp_join)",
        "    BSYNC B0;[7:7:{}:5:0]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
        "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
        "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
        "    BAR.SYNC 0;[7:7:{1}:5:1]",
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
    ap.add_argument("--schedule", choices=("serial", "none", "round3"),
                    required=True)
    ap.add_argument("--batches", type=int, default=32)
    ap.add_argument("--ops-per-batch", type=int, default=16)
    ap.add_argument("--warps", type=int, default=4)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    if not 1 <= ns.warps <= 16:
        ap.error("--warps must be in [1,16]")
    name = f"utccp_w4_{ns.schedule}_{ns.warps}w"
    src = source(name, ns.batches, ns.ops_per_batch, ns.schedule, ns.warps)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
