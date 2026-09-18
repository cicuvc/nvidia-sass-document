#!/usr/bin/env python3
"""Build a native sm_100a UBLKCP.S.G.MULTICAST cluster probe.

The kernel must be launched as one 2-CTA cluster.  Both CTAs initialise and
wait on their own same-offset mbarrier; only cluster rank 0 issues the copies,
with mask 0b11.  This is intentionally separate from the TMEM stress probe so
an invalid multicast protocol cannot poison a larger experiment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def source(name: str, size: int, copies: int, multicast: bool = True) -> str:
    if size % 16 or not 16 <= size <= 16384:
        raise ValueError("size must be 16..16384 and 16-byte aligned")
    count = ((0x3 << 16) if multicast else 0) | (size // 16)
    modifier = ".MULTICAST" if multicast else ""
    predicate = "@UP0 " if multicast else ""
    ops = "\n".join(
        f"    {predicate}UBLKCP.S.G{modifier} "
        "{UR6,UR7}, {UR10,UR11}, UR12;[7:2:{0}:1:0]"
        for _ in range(copies))
    return f"""#fn {name}(out<8>) {{
    #pragma MAXREG_COUNT(32)
    #pragma SHARED(0x800)
    #pragma NUM_MBARRIERS(1)
    #pragma CLUSTER(2,1,1)
    LDC.64 {{R2,R3}}, #param(out);[0:7:{{}}:1:0]
    S2R R4, SR_CgaCtaId;[1:7:{{}}:2:0]
    S2R R5, SR_TID.X;[2:7:{{}}:2:0]
    S2UR UR8, SR_CgaCtaId;[0:7:{{}}:1:0]
    UMOV UR6, 0x400;[7:7:{{}}:1:0]
    UMOV UR7, 0x600;[7:7:{{}}:1:0]
    ULEA UR6, UR8, UR6, 0x18;[7:7:{{0}}:9:1]
    ULEA UR7, UR8, UR7, 0x18;[7:7:{{}}:9:1]
    #!mbarrier_init(UR7, 1)
    IADD3 R6, P5, R2, 0x1000, RZ;[7:7:{{0}}:5:1]
    IADD3.X R7, R3, RZ, RZ, P5, !PT;[7:7:{{}}:5:1]
    R2UR UR10, R6;[0:7:{{}}:1:0]
    R2UR UR11, R7;[0:7:{{}}:1:0]
    UMOV UR12, {count:#x};[7:7:{{}}:1:0]
    FENCE.VIEW.ASYNC.S;[7:7:{{}}:5:1]
    UCGABAR_ARV;[7:7:{{}}:5:1]
    UCGABAR_WAIT;[7:7:{{}}:5:1]
    UISETP.EQ.AND UP0, UPT, UR8, URZ, UPT;[7:7:{{0}}:1:0]
    CS2R {{R16,R17}}, SR_CLOCKLO;[7:7:{{}}:5:0]
{ops}
    UCGABAR_ARV;[7:7:{{2}}:5:1]
    UCGABAR_WAIT;[7:7:{{}}:5:1]
    ISETP.EQ.AND P6, PT, R5, RZ, PT;[7:7:{{2}}:13:1]
    MOV32I R0, {size * copies:#x};[7:7:{{}}:5:1]
    @P6 SYNCS.ARRIVE.TRANS64.RED {{RZ,RZ}}, [RZ+UR7], R0;[7:2:{{2}}:1:0]
    #def_label(poll)
    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR7], RZ;[1:7:{{}}:2:0]
    @!P2 BRA #label(poll);[7:7:{{1}}:5:0]
    CS2R {{R18,R19}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    IMAD.WIDE.U32 {{R8,R9}}, R4, 0x20, {{R2,R3}};[7:7:{{1}}:5:1]
    @P6 STG.E.64.STRONG.GPU [{{R8,R9}}], {{R16,R17}};[7:0:{{}}:8:0]
    @P6 STG.E.64.STRONG.GPU [{{R8,R9}}+8], {{R18,R19}};[7:1:{{0}}:8:0]
    LDS R20, [UR6];[2:7:{{}}:1:0]
    @P6 STG.E.STRONG.GPU [{{R8,R9}}+0x10], R20;[7:2:{{1,2}}:8:0]
    EXIT;[7:7:{{2}}:5:0]
}}"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=4096)
    ap.add_argument("--copies", type=int, default=32)
    ap.add_argument("--plain", action="store_true",
                    help="cluster-launch control: each CTA issues a plain S.G")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    name = "ublk_multicast"
    src = source(name, ns.size, ns.copies, not ns.plain)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
