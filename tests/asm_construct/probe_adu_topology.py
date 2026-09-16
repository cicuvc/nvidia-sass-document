#!/usr/bin/env python3
"""Classify GB202 ADU users and locate ADU relative to MIO operand queues.

The kernel intentionally has no parameters and no memory epilogue, making
the selected instruction stream the only scalable contribution to NCU pipe
counters.  Of particular interest is
``sm__mio_pq_read_cycles_active_pipe_adu``: BRX with RZ needs no physical GPR
read, while BRX with a real zero-valued GPR pair performs the same sequence
of control transfers but must collect a 64-bit target operand.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


CASES = (
    "nop", "bra", "bra_far", "bra_pred", "bra_div", "div_control",
    "brx_rz", "brx_reg", "brx_div", "ldc_imm", "ldc_reg", "ldcu_imm", "bar",
)


def source(case: str, count: int, pred_off: bool, targets: int = 2) -> str:
    guard = "@P6 " if pred_off else ""
    lines = [
        "#fn aduprobe() {",
        "    #pragma MAXREG_COUNT(96)",
        "    MOV32I R24, 0x0;[7:7:{}:5:1]",
        "    MOV32I R25, 0x0;[7:7:{}:5:1]",
        "    S2R R26, SR_TID.X;[1:7:{}:5:1]",
        "    LOP3.LUT R27, R26, 0x1, RZ, 0xc0, !PT;[7:7:{1}:5:1]",
        "    ISETP.EQ.AND P0, PT, R27, RZ, PT;[7:7:{}:13:1]",
    ]
    if case == "brx_div":
        # Each path occupies NOP+BRA = 32 bytes.  Lane (mod targets) selects
        # one of them; R25 remains the zero high half.
        lines += [
            f"    LOP3.LUT R24, R26, 0x{targets - 1:x}, RZ, 0xc0, !PT;"
            "[7:7:{}:5:1]",
            "    SHL R24, R24, 0x5;[7:7:{}:5:1]",
        ]
    for i in range(count):
        rd = 40 + i % 40
        if case == "nop":
            lines.append(f"    {guard}NOP;[7:7:{{}}:1:1]")
        elif case == "bra":
            lines += [
                f"    {guard}BRA #label(next_{i});[7:7:{{}}:6:0]",
                f"    #def_label(next_{i})",
            ]
        elif case == "bra_far":
            lines += [
                f"    {guard}BRA #label(next_{i});[7:7:{{}}:6:0]",
                "    NOP;[7:7:{}:1:1]",
                f"    #def_label(next_{i})",
            ]
        elif case == "bra_pred":
            lines += [
                f"    {guard}@P0 BRA #label(next_{i});[7:7:{{}}:6:0]",
                "    NOP;[7:7:{}:1:1]",
                f"    #def_label(next_{i})",
            ]
        elif case == "bra_div":
            lines += [
                f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                f"    @P0 BRA #label(taken_{i});[7:7:{{}}:6:0]",
                "    NOP;[7:7:{}:1:1]",
                f"    BRA #label(join_{i});[7:7:{{}}:6:0]",
                f"    #def_label(taken_{i})",
                "    NOP;[7:7:{}:1:1]",
                f"    #def_label(join_{i})",
                "    BSYNC B0;[7:7:{}:5:1]",
            ]
        elif case == "div_control":
            lines += [
                f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                "    NOP;[7:7:{}:1:1]",
                f"    #def_label(join_{i})",
                "    BSYNC B0;[7:7:{}:5:1]",
            ]
        elif case == "brx_rz":
            lines += [
                f"    {guard}BRX RZ, #label(next_{i});[7:7:{{}}:6:0]",
                f"    #def_label(next_{i})",
            ]
        elif case == "brx_reg":
            lines += [
                f"    {guard}BRX {{R24,R25}}, #label(next_{i});[7:7:{{}}:6:0]",
                f"    #def_label(next_{i})",
            ]
        elif case == "brx_div":
            lines += [
                f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                f"    BRX {{R24,R25}}, #label(path0_{i});[7:7:{{}}:6:0]",
            ]
            for target in range(targets):
                lines += [
                    f"    #def_label(path{target}_{i})",
                    "    NOP;[7:7:{}:1:1]",
                    f"    BRA #label(join_{i});[7:7:{{}}:6:0]",
                ]
            lines += [f"    #def_label(join_{i})",
                      "    BSYNC B0;[7:7:{}:5:1]"]
        elif case == "ldc_imm":
            lines.append(
                f"    {guard}LDC R{rd}, c[0x0][0x0];[7:7:{{}}:1:1]")
        elif case == "ldc_reg":
            lines.append(
                f"    {guard}LDC R{rd}, c[0x0][R24+0x0];[7:7:{{}}:1:1]")
        elif case == "ldcu_imm":
            lines.append(
                f"    {guard}LDCU UR{8 + i % 40}, c[0x0][0x0];[7:7:{{}}:1:1]")
        elif case == "bar":
            lines.append(f"    {guard}BAR.SYNC 0;[7:7:{{}}:5:1]")
        else:
            raise ValueError(case)
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=CASES, required=True)
    p.add_argument("--count", type=int, default=256)
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--pred-off", action="store_true")
    p.add_argument("--targets", type=int, choices=(1, 2, 4, 8, 16, 32),
                   default=2, help="distinct lane targets for brx_div")
    ns = p.parse_args()
    if ns.count <= 0 or ns.reps <= 0:
        p.error("count and reps must be positive")
    if ns.pred_off and ns.case in ("bra_pred", "bra_div", "div_control",
                                    "brx_div"):
        p.error("--pred-off is not supported by the explicit-divergence cases")

    cubin = assemble(source(ns.case, ns.count, ns.pred_off, ns.targets),
                     check_deps=True)
    mod = CudaModule(cubin)
    for _ in range(ns.reps):
        mod.launch("aduprobe", grid=(1,), block=(32,), args=[])
        mod.synchronize()
    print(f"{ns.case}: count={ns.count} pred_off={ns.pred_off} "
          f"targets={ns.targets} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
