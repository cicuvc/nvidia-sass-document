#!/usr/bin/env python3
"""Build controlled-parity sm70/sm80 FADD/FFMA RF-bank probe cubins."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble  # noqa: E402


CASES = {
    "nop": None,
    "fadd_ee": ("FADD", ("R4", "R10"), 0),
    "fadd_oo": ("FADD", ("R5", "R11"), 0),
    "fadd_eo": ("FADD", ("R4", "R9"), 0),
    "ffma_eee": ("FFMA", ("R4", "R10", "R8"), 0),
    "ffma_ooo": ("FFMA", ("R5", "R11", "R9"), 0),
    "ffma_eeo": ("FFMA", ("R4", "R10", "R9"), 0),
    "ffma_eoe": ("FFMA", ("R4", "R9", "R10"), 0),
    "ffma_oee": ("FFMA", ("R9", "R4", "R10"), 0),
    "ffma_eee_ra": ("FFMA", ("R4", "R10", "R8"), 1),
    "ffma_eee_rb": ("FFMA", ("R4", "R10", "R8"), 2),
    "ffma_eee_rab": ("FFMA", ("R4", "R10", "R8"), 3),
    "ffma_eee_rabc": ("FFMA", ("R4", "R10", "R8"), 7),
}


def source(case: str, n: int) -> str:
    spec = CASES[case]
    lines = [
        "#fn thr(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        # Match nvcc's verified Volta address sequence: the 64-bit constant
        # operand is the addend of IMAD.WIDE, not two scalar MOVs.
        "    S2R R0, SR_TID.X;[7:7:{}:6:0]",
        "    MOV R6, 0x10;[7:7:{}:6:0]",
        "    IMAD.WIDE.U32 {R2,R3}, R0, R6, c[0x0][0x160];[7:7:{}:6:0]",
    ]
    for r in (4, 5, 8, 9, 10, 11):
        lines.append(f"    MOV R{r}, 0x3f800000;[7:7:{{}}:6:0]")
    for r in range(40, 80):
        lines.append(f"    MOV R{r}, RZ;[7:7:{{}}:6:0]")
    lines += [
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:6:0]",
        "    NOP;[7:7:{}:1:1]",
    ]
    for i in range(n):
        if spec is None:
            lines.append("    NOP;[7:7:{}:1:0]")
        else:
            opcode, operands, reuse = spec
            sched = f"[7:7:{{}}:1:0:{reuse}]" if reuse else "[7:7:{}:1:0]"
            args = ", ".join(operands)
            lines.append(f"    {opcode} R{40 + i % 40}, {args};{sched}")
    lines += [
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:6:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R30,R31};[0:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R32,R33};[0:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=512)
    ap.add_argument("--out", type=Path, default=Path("/tmp/v100_rf"))
    ap.add_argument("--arch", choices=("sm70", "sm80"), default="sm70")
    ns = ap.parse_args()
    ns.out.mkdir(parents=True, exist_ok=True)
    for name in CASES:
        cubin = assemble(source(name, ns.count), arch=ns.arch, check_deps=False)
        (ns.out / f"rf_{name}.cubin").write_bytes(cubin)
    print(f"built {len(CASES)} {ns.arch} cubins in {ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
