#!/usr/bin/env python3
"""Build a batched B200 sweep of every legal LDTM/STTM layout x NUM pair.

One kernel measures all 45 legal pairs, so Modal pays one module/launch cost.
STTM cases end in FENCE.VIEW.ASYNC.T.  LDTM deliberately reuses one register
group and one scoreboard, making it a completion-latency scan rather than a
peak-throughput scan for the very wide forms that cannot have multiple disjoint
128-register destinations.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


LAYOUTS = (
    ("32dp32bit", "", 1, 7),
    ("16dp64bit", ".16dp64bit", 1, 7),
    ("16dp128bit", ".16dp128bit", 2, 6),
    ("16dp256bit", ".16dp256bit", 4, 5),
    ("16dp32bit_t0_t15", ".16dp32bit_t0_t15", 1, 7),
    ("16dp32bit_t16_t31", ".16dp32bit_t16_t31", 1, 7),
)


def cases(layout_filter: str | None = None,
          num_filter: int | None = None) -> list[tuple[str, str, int, int]]:
    out = []
    for layout, modifier, reg_factor, max_log2 in LAYOUTS:
        if layout_filter is not None and layout != layout_filter:
            continue
        for log2_num in range(max_log2 + 1):
            if num_filter is not None and 1 << log2_num != num_filter:
                continue
            out.append((layout, modifier, 1 << log2_num,
                        reg_factor << log2_num))
    if num_filter is not None:
        assert out
    elif layout_filter is None:
        assert len(out) == 45
    else:
        assert len(out) == next(
            max_log2 + 1 for layout, _, _, max_log2 in LAYOUTS
            if layout == layout_filter)
    return out


def _group(lo: int, count: int) -> str:
    if count == 1:
        return f"R{lo}"
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def _opcode(op: str, modifier: str, num: int, convert: bool) -> str:
    num_mod = "" if num == 1 else f".x{num}"
    conv_mod = (".PACK16BIT" if op == "ldtm" else ".EXPAND16BIT") \
        if convert else ""
    return ("LDTM" if op == "ldtm" else "STTM") + modifier + num_mod + conv_mod


def source(name: str, op: str, convert: bool, count: int,
           unroll: int, layout_filter: str | None = None,
           num_filter: int | None = None) -> str:
    if count % unroll or unroll % 6:
        raise ValueError("count must divide by unroll and unroll by six")
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(224)",
        "    #pragma SHARED(0x800)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    #!tmem_alloc_1cta(UR5, 512)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    LDS R10, [UR5];[0:7:{0}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        "    ISETP.EQ.AND P0, PT, R4, RZ, PT;[7:7:{}:13:1]",
    ]
    for case_index, (_, modifier, num, nregs) in enumerate(
            cases(layout_filter, num_filter)):
        opcode = _opcode(op, modifier, num, convert)
        operand = _group(64, nregs)
        lines += [
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]",
            f"    MOV32I R30, {count // unroll};[7:7:{{}}:5:1]",
            f"    #def_label(case_{case_index}_loop)",
        ]
        for _ in range(unroll):
            if op == "sttm":
                lines.append(
                    f"    {opcode} tmem[UR10], {operand};[7:7:{{}}:1:0]")
            else:
                lines.append(
                    f"    {opcode} {operand}, tmem[UR10];[0:7:{{0}}:1:0]")
        lines += [
            "    IADD3 R30, R30, -0x1, RZ;[7:7:{}:5:1]",
            "    ISETP.NE.AND P1, PT, R30, RZ, PT;[7:7:{}:13:1]",
            f"    @P1 BRA #label(case_{case_index}_loop);[7:7:{{}}:5:0]",
            ("    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]" if op == "sttm" else
             "    NOP;[7:7:{0}:1:0]"),
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
            # Keep the clock read well clear of the following stores.  In a
            # long batched probe, five nominal stalls were insufficient for
            # some short async-STTM cases: the store observed the preceding
            # case's R18:R19 and produced the characteristic delta -8.
            *["    NOP;[7:7:{}:8:1]"] * 4,
            f"    @P0 STG.E.64.STRONG.GPU [{{R2,R3}}+{case_index * 16:#x}], "
            "{R16,R17};[7:0:{}:1:0]",
            f"    @P0 STG.E.64.STRONG.GPU [{{R2,R3}}+{case_index * 16 + 8:#x}], "
            "{R18,R19};[7:1:{0}:1:0]",
            # Both timing stores claim source-read barriers.  Waiting only
            # SB1 lets the next case overwrite R16:R17 while the first STG is
            # still consuming it, corrupting the next start timestamp.
            "    NOP;[7:7:{0,1}:1:0]",
        ]
    lines += [
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--op", choices=("ldtm", "sttm"), required=True)
    ap.add_argument("--convert", action="store_true",
                    help="PACK16BIT for LDTM, EXPAND16BIT for STTM")
    ap.add_argument("--count", type=int, default=1536)
    ap.add_argument("--unroll", type=int, default=96)
    ap.add_argument("--layout", choices=tuple(item[0] for item in LAYOUTS),
                    help="emit only one layout's NUM sweep")
    ap.add_argument("--num", type=int, choices=(1, 2, 4, 8, 16, 32, 64, 128),
                    help="emit only one repetition count")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    suffix = f"_{ns.layout}" if ns.layout else ""
    suffix += f"_x{ns.num}" if ns.num else ""
    name = f"tmem_mods_{ns.op}_{'c1' if ns.convert else 'c0'}{suffix}"
    src = source(name, ns.op, ns.convert, ns.count, ns.unroll, ns.layout,
                 ns.num)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}, "
          f"{len(cases(ns.layout, ns.num))} cases")


if __name__ == "__main__":
    main()
