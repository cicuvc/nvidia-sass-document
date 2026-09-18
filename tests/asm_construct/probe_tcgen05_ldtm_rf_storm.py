#!/usr/bin/env python3
"""Build LDTM.x16 versus fixed-pipe RF-write storm probes for sm100a."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_kernel  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "tests/asm_construct/tcgen05_alloc_sm100.sass"


def make_source(kind: str, gap: int, groups: int,
                no_ldtm: bool = False) -> str:
    source = TEMPLATE.read_text()
    prefix = "fixed_only" if no_ldtm else "ldtm_storm"
    name = f"{prefix}_{kind}_g{gap}"
    source = source.replace("#fn alloc32(out<8>) {", f"#fn {name}(out<8>) {{", 1)
    source = source.replace("    #pragma REGCOUNT(12)",
                            "    #pragma REGCOUNT(128)", 1)
    old = """    LDS R5, [UR5];[2:7:{}:1:0]
    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]
    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]
    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R5;[7:0:{2}:1:0]
    NOP;[7:7:{}:1:0]"""
    if kind == "even":
        storm_regs = range(80, 96, 2)
    elif kind == "alternating":
        storm_regs = range(80, 88)
    elif kind == "nop":
        storm_regs = ()
    else:
        raise ValueError(kind)
    storm = ([f"    FFMA R{r}, R60, R61, R62;[7:7:{{}}:1:0]"
              for r in storm_regs]
             if kind != "nop" else
             ["    NOP;[7:7:{}:1:0]" for _ in range(8)])
    new = "\n".join([
        "    LDS R5, [UR5];[2:7:{}:1:0]",
        "    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]",
        "    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]",
        "    R2UR UR10, R5;[7:7:{2}:13:1]",
        "    MOV32I R60, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R61, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R62, 0x3f000000;[7:7:{}:5:1]",
        f"    MOV R30, 0x{groups:x};[7:7:{{}}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    #def_label(storm_loop)",
        ("    NOP;[7:7:{}:1:0]" if no_ldtm else
         "    LDTM.x16 {R40,R41,R42,R43,R44,R45,R46,R47,"
         "R48,R49,R50,R51,R52,R53,R54,R55}, tmem[UR10];[0:7:{0}:1:0]"),
        *["    NOP;[7:7:{}:1:0]" for _ in range(gap)],
        *storm,
        "    IADD3 R30, R30, -0x1, RZ;[7:7:{}:5:1]",
        "    ISETP.NE.AND P1, PT, R30, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(storm_loop);[7:7:{}:5:0]",
        ("    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]" if no_ldtm else
         "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{0}:5:0]"),
        "    @!P0 STG.E.128.STRONG.GPU desc[{UR8,UR9}]"
        "[{R2,R3}], {R20,R21,R22,R23};[7:0:{2}:8:0]",
    ])
    if old not in source:
        raise ValueError("allocator payload anchor not found")
    return name, source.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("nop", "even", "alternating"))
    parser.add_argument("--gap", type=int, default=0)
    parser.add_argument("--groups", type=int, default=256)
    parser.add_argument("--no-ldtm", action="store_true")
    parser.add_argument("--output", type=Path)
    ns = parser.parse_args()
    if ns.gap < 0 or ns.groups <= 0:
        parser.error("gap must be non-negative and groups positive")
    name, source = make_source(ns.kind, ns.gap, ns.groups, ns.no_ldtm)
    output = ns.output or Path(f"/tmp/{name}.cubin")
    result = assemble_kernel(source, arch="sm100a", check_deps=False)
    output.write_bytes(result.code)
    print(f"{name} -> {output} ({len(result.code)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
