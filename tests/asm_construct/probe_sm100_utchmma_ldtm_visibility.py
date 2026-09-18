#!/usr/bin/env python3
"""Build a B200 probe for observing in-flight UTCHMMA D through LDTM.

Warp 0 submits one overwrite followed by ``mma_count`` accumulating MMAs to the
same D in a single completion epoch.  Warp 1 concurrently samples column zero
with LDTM.x1 and lane 0 stores the samples consecutively to global memory.
Intermediate multiples of 16 prove that tensor results retire to ordinary TMEM
before the final UTCBAR becomes visible.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def source(name: str, mma_count: int, samples: int, mode: str,
           initialize_shared: bool, observer_warp: int) -> str:
    if not 1 <= mma_count <= 256:
        raise ValueError("mma_count must be 1..256")
    if not 1 <= samples <= 1024:
        raise ValueError("samples must be 1..1024")

    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(80)",
        "    #pragma SHARED(0x3000)",
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
    if initialize_shared:
        # 64 threads x 16 B x four stripes = 4 KiB per operand.
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
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P1, PT, R5, RZ, PT;[7:7:{}:13:1]",
        ("    @P1 BRA #label(producer);[7:7:{}:5:0]" if mode != "observer"
         else "    @P1 BRA #label(work_done);[7:7:{}:5:0]"),
        f"    ISETP.EQ.AND P2, PT, R5, {observer_warp:#x}, PT;"
        "[7:7:{}:13:1]",
        ("    @P2 BRA #label(observer);[7:7:{}:5:0]" if mode != "producer"
         else "    @P2 BRA #label(work_done);[7:7:{}:5:0]"),
        "    BRA #label(work_done);[7:7:{}:5:0]",
        "    #def_label(producer)",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
        "tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, !UPT;"
        "[7:0:{}:12:1]",
    ]
    lines += [
        "    UTCHMMA.1CTA gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
        "tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, UPT;"
        "[7:0:{}:12:1]"
        for _ in range(mma_count)
    ]
    lines += [
        # The uniform address producer needs the normal UDP forwarding gap
        # before UTCBAR consumes it.  Shorter/no-yield schedules can hang.
        "    UMOV UR18, 0x600;[7:7:{}:5:1]",
        "    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]",
        "    #!mbarrier_wait(UR18, 0)",
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    STG.E.64.STRONG.GPU [{{R2,R3}}+{samples * 4:#x}], "
        "{R16,R17};[7:0:{}:8:0]",
        f"    STG.E.64.STRONG.GPU [{{R2,R3}}+{samples * 4 + 8:#x}], "
        "{R18,R19};[7:1:{0}:8:0]",
        "    BRA #label(work_done);[7:7:{1}:5:0]",
        "    #def_label(observer)",
        "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
    ]
    for i in range(samples):
        lines += [
            "    LDTM R40, tmem[UR10];[0:7:{0}:1:0]",
            f"    @P0 STG.E.STRONG.GPU [{{R2,R3}}+{i * 4:#x}], R40;"
            "[7:7:{0}:1:0]",
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
    ap.add_argument("--mma-count", type=int, default=64)
    ap.add_argument("--samples", type=int, default=512)
    ap.add_argument("--mode", choices=("combined", "producer", "observer"),
                    default="combined")
    ap.add_argument("--zero-operands", action="store_true",
                    help="skip shared A/B initialization for bring-up")
    ap.add_argument("--observer-warp", type=int, default=1)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    name = f"utchmma_ldtm_{ns.mode}_m{ns.mma_count}_s{ns.samples}"
    src = source(name, ns.mma_count, ns.samples, ns.mode,
                 not ns.zero_operands, ns.observer_warp)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
