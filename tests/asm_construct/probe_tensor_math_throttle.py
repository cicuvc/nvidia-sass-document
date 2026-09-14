#!/usr/bin/env python3
"""Generate same/different-subcore tensor-MMA streams for NCU probes.

Warp 0 always executes a selected HMMA, IMMA, or QMMA stream.  The contender
may use the same or a different MMA opcode.  It is warp 4 (same subcore) or
warp 1 (different subcore), and executes either an active stream, the identical
@P6 predicated-off stream, or nothing.  Results rotate through 47 independent
four-register groups and are never read, avoiding the non-scoreboarded
result-latency hazard.

Example NCU invocation (the script warms once, hence launch-skip 1):

  sudo ncu --launch-skip 1 --launch-count 1 --metrics \
    smsp__warps_issue_stalled_math_pipe_throttle.sum,\
smsp__pipe_tensor_cycles_active.sum,\
smsp__pipe_tensor_subpipe_hmma_cycles_active.sum \
    python3 tests/asm_construct/probe_tensor_math_throttle.py \
      --op hmma --count 512 --placement same_ab
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


PLACEMENTS = {
    "solo": (7, 0),
    "same_ab": (4, 1),
    "same_ctrl": (4, 2),
    "diff_ab": (1, 1),
    "diff_ctrl": (1, 2),
}


def mma_body(op: str, n: int, guard: str = "") -> list[str]:
    prefix = f"{guard} " if guard else ""
    lines = []
    for i in range(n):
        # Avoid R220..R223: that destination group assembles, but including
        # R223 in an HMMA result faults 715 on this GB202.  Forty-seven groups
        # still exceed the result latency before a destination is reused.
        rd = 32 + 4 * (i % 47)
        dst = f"{{R{rd},R{rd+1},R{rd+2},R{rd+3}}}"
        if op == "hmma":
            inst = (f"HMMA.16816.F32.BF16 {dst}, "
                    "{R16,R17,R18,R19}, {R20,R21}, "
                    "{R24,R25,R26,R27}")
        elif op == "imma":
            inst = (f"IMMA.16816.U8.U8 {dst}, {{R16,R17}}.ROW, R20.COL, "
                    "{R24,R25,R26,R27}, !UPT")
        elif op == "qmma":
            inst = (f"QMMA.16832.F32.E4M3.E4M3 {dst}, "
                    "{R16,R17,R18,R19}, {R20,R21}, "
                    "{R24,R25,R26,R27}")
        else:  # argparse and source() keep this unreachable.
            raise ValueError(op)
        lines.append(f"    {prefix}{inst};[7:7:{{}}:1:0]")
    return lines


def source(op: str, contender_op: str, n: int) -> str:
    lines = [
        "#fn hmath(contender_warp<4>, kind<4>) {",
        "    #pragma MAXREG_COUNT(224)",
        "    LDC R12, #param(contender_warp);[1:7:{}:1:0]",
        "    LDC R13, #param(kind);[2:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[3:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{3}:5:1]",
        "    MOV32I R16, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R17, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R18, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R19, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R20, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R21, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R24, 0;[7:7:{}:5:1]",
        "    MOV32I R25, 0;[7:7:{}:5:1]",
        "    MOV32I R26, 0;[7:7:{}:5:1]",
        "    MOV32I R27, 0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, R12, PT;[7:7:{1}:13:1]",
        "    @!P0 BRA #label(done);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R13, 0x1, PT;[7:7:{2}:13:1]",
        "    @P0 BRA #label(active);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R13, 0x2, PT;[7:7:{2}:13:1]",
        "    @P0 BRA #label(control);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
    ]
    lines += mma_body(op, n)
    lines += ["    BRA #label(drain);[7:7:{}:5:1]", "#def_label(active)"]
    lines += mma_body(contender_op, n)
    lines += ["    BRA #label(drain);[7:7:{}:5:1]", "#def_label(control)"]
    lines += mma_body(contender_op, n, "@P6")
    lines += ["#def_label(drain)"]
    # Results are COUPLED_EMULATABLE rather than scoreboarded.  They are not
    # consumed, but leave a conservative drain window before EXIT.
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(16)]
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--op", choices=("hmma", "imma", "qmma"), default="hmma")
    p.add_argument("--contender-op", choices=("hmma", "imma", "qmma"),
                   help="contender opcode (default: same as --op)")
    p.add_argument("--count", type=int, default=512)
    p.add_argument("--placement", choices=PLACEMENTS, default="same_ab")
    ns = p.parse_args()
    if ns.count <= 0:
        p.error("--count must be positive")
    contender_op = ns.contender_op or ns.op
    mod = CudaModule(assemble(source(ns.op, contender_op, ns.count),
                              check_deps=True))
    warp, kind = PLACEMENTS[ns.placement]
    # Warm the exact runtime path, then provide one identical profiling launch.
    for _ in range(2):
        mod.launch("hmath", grid=(1,), block=(256,), args=[warp, kind])
        mod.synchronize()
    print(f"{ns.op.upper()}+{contender_op.upper()} count={ns.count} "
          f"placement={ns.placement}: completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
