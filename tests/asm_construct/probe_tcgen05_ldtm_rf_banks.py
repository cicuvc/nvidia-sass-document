#!/usr/bin/env python3
"""Build sm100a LDTM destination-bank throughput probes.

The probe keeps the TMEM addresses, instruction count, queue-completion
scoreboard, loop body and output path identical.  Only the x1 destination
register sequence changes:

  even:       R40,R42,...,R54 (all bank 0)
  odd:        R41,R43,...,R55 (all bank 1)
  alternating:R40,R41,...,R47 (four writes to each bank)

Eight loads form one ordered VQ batch.  Only the last claims SB0; the first
load of the next batch waits SB0, matching the grouping emitted by ptxas.
The final CS2R also waits SB0, so the measured endpoint includes RF writeback.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_kernel  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "tests/asm_construct/tcgen05_alloc_sm100.sass"


def make_source(layout: str, groups: int) -> str:
    if layout == "even":
        regs = list(range(40, 56, 2))
    elif layout == "odd":
        regs = list(range(41, 57, 2))
    elif layout == "alternating":
        regs = list(range(40, 48))
    else:
        raise ValueError(layout)

    source = TEMPLATE.read_text()
    source = source.replace("#fn alloc32(out<8>) {",
                            f"#fn ldtm_bank_{layout}(out<8>) {{", 1)
    source = source.replace("    #pragma REGCOUNT(12)",
                            "    #pragma REGCOUNT(64)", 1)
    old = """    LDS R5, [UR5];[2:7:{}:1:0]
    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]
    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]
    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R5;[7:0:{2}:1:0]
    NOP;[7:7:{}:1:0]"""
    loads = []
    for i, reg in enumerate(regs):
        req = "{0}" if i == 0 else "{}"
        wr = 0 if i == len(regs) - 1 else 7
        loads.append(
            f"    LDTM R{reg}, tmem[UR10+0x{i:x}];"
            f"[{wr}:7:{req}:1:0]")
    new = "\n".join([
        "    LDS R5, [UR5];[2:7:{}:1:0]",
        "    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]",
        "    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]",
        "    R2UR UR10, R5;[7:7:{2}:13:1]",
        f"    MOV R30, 0x{groups:x};[7:7:{{}}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    #def_label(bank_loop)",
        *loads,
        "    IADD3 R30, R30, -0x1, RZ;[7:7:{}:5:1]",
        "    ISETP.NE.AND P1, PT, R30, RZ, PT;[7:7:{}:13:1]",
        "    @P1 BRA #label(bank_loop);[7:7:{}:5:0]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{0}:5:0]",
        "    @!P0 STG.E.128.STRONG.GPU desc[{UR8,UR9}]"
        "[{R2,R3}], {R20,R21,R22,R23};[7:0:{2}:8:0]",
        # Let the driver's injected TMEM atexit handler release the allocation.
        # The hand-transcribed deallocator below is the single-warp nvcc path
        # and is not safe when every warp executes this probe payload.
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{0}:5:0]",
    ])
    if old not in source:
        raise ValueError("allocator payload anchor not found")
    return source.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", choices=("even", "odd", "alternating"))
    parser.add_argument("--groups", type=int, default=256)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-output", type=Path)
    ns = parser.parse_args()
    if ns.groups <= 0:
        parser.error("--groups must be positive")
    source = make_source(ns.layout, ns.groups)
    output = ns.output or Path(f"/tmp/ldtm_bank_{ns.layout}.cubin")
    result = assemble_kernel(source, arch="sm100a", check_deps=False)
    output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(source)
    print(f"{ns.layout}: {ns.groups * 8} LDTM.x1 -> {output} "
          f"({len(result.code)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
