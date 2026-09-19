#!/usr/bin/env python3
"""Recover TMEM layout permutations with unique (source lane, register) tags."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


LAYOUT_REGS = {"64": 2, "128": 8, "256": 4, "half0": 2, "half16": 2}
# A 16-datapath layout covers only rows 0..15 of the canonical 32-row view.
# Its column footprint is (bits-per-datapath / 32) * repeat-count.
CANON_WIDTH = {"64": 4, "128": 16, "256": 8, "half0": 2, "half16": 2}


def _group(lo: int, count: int) -> str:
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def _layout_ops(op: str, layout: str, reg: int) -> list[str]:
    mnem = "STTM" if op == "st" else "LDTM"
    if op == "st":
        operand = lambda mods, regs, addr: (  # noqa: E731
            f"    {mnem}.{mods} {addr}, {_group(reg, regs)};"
            "[7:7:{}:1:0]")
    else:
        operand = lambda mods, regs, addr: (  # noqa: E731
            f"    {mnem}.{mods} {_group(reg, regs)}, {addr};"
            "[1:7:{0}:1:0]")
    if layout == "64":
        return [operand("16dp64bit.x2", 2, "tmem[UR10]")]
    if layout == "128":
        return [operand("16dp128bit.x4", 8, "tmem[UR10]")]
    if layout == "256":
        return [operand("16dp256bit.x1", 4, "tmem[UR10]")]
    half = "t0_t15" if layout == "half0" else "t16_t31"
    return [operand(f"16dp32bit_{half}.x2", 2, "tmem[UR10]")]


def source(name: str, layout: str, direction: str) -> str:
    nregs = LAYOUT_REGS[layout]
    canon = CANON_WIDTH[layout]
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(80)",
        "    #pragma SHARED(0x800)",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHL R12, R4, 0x10;[7:7:{1}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    #!tmem_alloc_1cta(UR5, 32)",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
    ]
    # Each source register contains 0x80000000 | lane<<16 | register-index.
    for i in range(16):
        lines += [
            f"    IADD3 R{20 + i}, R12, {0x80000000 + i:#x}, RZ;"
            "[7:7:{}:5:1]"
        ]
    for i in range(16):
        lines += [f"    MOV32I R{40 + i}, 0xfeed0000;[7:7:{{}}:5:1]"]

    if direction == "canonical-to-layout":
        lines += [
            f"    STTM.x{canon} tmem[UR10], {_group(20, canon)};"
            "[7:7:{}:1:0]",
            "    FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]",
        ]
        lines += _layout_ops("ld", layout, 40)
    else:
        lines += _layout_ops("st", layout, 20)
        lines += [
            "    FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]",
            f"    LDTM.x{canon} {_group(40, canon)}, tmem[UR10];"
            "[1:7:{0}:1:0]",
        ]
    lines += [
        "    NOP;[7:7:{1}:1:0]",
        "    IMAD.WIDE.U32 {R8,R9}, R4, 0x40, {R2,R3};[7:7:{0}:5:1]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}], {_group(40, 4)};"
        "[7:0:{1}:1:0]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}+0x10], {_group(44, 4)};"
        "[7:1:{0}:1:0]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}+0x20], {_group(48, 4)};"
        "[7:0:{1}:1:0]",
        f"    STG.E.128.STRONG.GPU [{{R8,R9}}+0x30], {_group(52, 4)};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 32)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", choices=tuple(LAYOUT_REGS), required=True)
    ap.add_argument("--direction",
                    choices=("canonical-to-layout", "layout-to-canonical"),
                    required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    short = "c2l" if ns.direction == "canonical-to-layout" else "l2c"
    name = f"tmem_tomo_{ns.layout}_{short}"
    src = source(name, ns.layout, ns.direction)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
