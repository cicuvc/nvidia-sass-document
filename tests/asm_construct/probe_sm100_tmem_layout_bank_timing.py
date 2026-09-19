#!/usr/bin/env python3
"""Time equal-byte LDTM layouts to expose intra-instruction TMEM conflicts.

The ordinary 32-datapath and 16-datapath forms below move equal byte counts
but present different row/column sets to TMEM.  A row-half/column checkerboard
bank function can therefore change cycles per instruction without requiring
two independently admitted producer warps.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


LAYOUTS = {
    "normal_x2": ("LDTM.x2", 2, 256),
    "16x64_x1": ("LDTM.16dp64bit", 1, 128),
    "16x64_x2": ("LDTM.16dp64bit.x2", 2, 256),
    "16x64_x4": ("LDTM.16dp64bit.x4", 4, 512),
    "16x64_x8": ("LDTM.16dp64bit.x8", 8, 1024),
    "16x64_x16": ("LDTM.16dp64bit.x16", 16, 2048),
    "16x64_x32": ("LDTM.16dp64bit.x32", 32, 4096),
    "16x64_x64": ("LDTM.16dp64bit.x64", 64, 8192),
    "16x64_x128": ("LDTM.16dp64bit.x128", 128, 16384),
    "normal_x4": ("LDTM.x4", 4, 512),
    "16x256_x1": ("LDTM.16dp256bit.x1", 4, 512),
    "normal_x8": ("LDTM.x8", 8, 1024),
    "16x128_x4": ("LDTM.16dp128bit.x4", 8, 1024),
    "half0_x2": ("LDTM.16dp32bit_t0_t15.x2", 2, 128),
    "half16_x2": ("LDTM.16dp32bit_t16_t31.x2", 2, 128),
    "half0_x1": ("LDTM.16dp32bit_t0_t15", 1, 64),
    "half16_x1": ("LDTM.16dp32bit_t16_t31", 1, 64),
}


def _group(lo: int, count: int) -> str:
    if count == 1:
        return f"R{lo}"
    return "{" + ",".join(f"R{i}" for i in range(lo, lo + count)) + "}"


def source(name: str, layout: str, column: int, count: int,
           column_alt: int | None = None, unroll: int = 96,
           op: str = "ldtm") -> str:
    opcode, nregs, _ = LAYOUTS[layout]
    lines = [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(96)",
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
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]",
    ]
    if count % unroll or unroll % 6:
        raise ValueError("count must divide by unroll and unroll by six")
    lines += [
        f"    MOV32I R30, {count // unroll};[7:7:{{}}:5:1]",
        "    #def_label(timing_loop)",
    ]
    for i in range(unroll):
        sb = i % 3
        lo = 40 + sb * 8
        this_column = (column if column_alt is None or i % 2 == 0
                       else column_alt)
        addr = f"tmem[UR10+{this_column:#x}]"
        if op == "ldtm":
            lines.append(
                f"    {opcode} {_group(lo, nregs)}, {addr};"
                f"[{sb}:7:{{{sb}}}:1:0]"
            )
        elif op == "sttm":
            lines.append(
                f"    {opcode.replace('LDTM', 'STTM')} {addr}, "
                f"{_group(lo, nregs)};[7:7:{{}}:1:0]"
            )
        else:
            raise ValueError(f"unknown operation: {op}")
    lines += [
        "    IADD3 R30, R30, -0x1, RZ;[7:7:{}:5:1]",
        "    ISETP.NE.AND P1, PT, R30, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(timing_loop);[7:7:{}:5:0]",
        ("    NOP;[7:7:{0,1,2}:1:0]" if op == "ldtm" else
         "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]"),
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R4, RZ, PT;[7:7:{}:13:1]",
        "    @P0 STG.E.64.STRONG.GPU [{R2,R3}], {R16,R17};[7:0:{0}:1:0]",
        "    @P0 STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R18,R19};"
        "[7:1:{0}:1:0]",
        "    NOP;[7:7:{1}:1:0]",
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", choices=LAYOUTS, required=True)
    ap.add_argument("--op", choices=("ldtm", "sttm"), default="ldtm")
    ap.add_argument("--column", type=int, default=0)
    ap.add_argument("--column-alt", type=int,
                    help="alternate every other instruction with this column")
    ap.add_argument("--count", type=int, default=1536)
    ap.add_argument("--unroll", type=int, default=96)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    if ns.count < 6 or ns.count % ns.unroll or ns.unroll % 6:
        ap.error("count must divide by unroll and unroll by six")
    col_name = (f"c{ns.column}" if ns.column_alt is None else
                f"c{ns.column}a{ns.column_alt}")
    name = (f"tmem_bank_{ns.op}_{ns.layout}_{col_name}_n{ns.count}_"
            f"u{ns.unroll}")
    src = source(name, ns.layout, ns.column, ns.count, ns.column_alt,
                 ns.unroll, ns.op)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    _, _, nbytes = LAYOUTS[ns.layout]
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}, {nbytes} B/op")


if __name__ == "__main__":
    main()
