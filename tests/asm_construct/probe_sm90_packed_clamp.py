#!/usr/bin/env python3
"""H100 packed-FP16 front-end clamp and packed/scalar handoff probe.

Mirrors the B200 (sm_100) packed-FMA experiments in
notes/sm100/arch/b200_fixed_admission_depth.md:

- B200 clamps same-warp packed-FMA issue to a 2-cycle minimum even with
  stall=1/yield=0, but the unused slot accepts IADD3/NOP (alternating
  aggregate 1.0/cyc) while scalar FFMA is blocked (0.5/cyc).
- B200 shows a packed->scalar handoff clock: the first scalar FFMA after
  packed work costs 2 cycles, later ones 1; scalar->packed costs nothing
  extra.

Single warp, CS2R window, [7:7:{}:1:0] brackets, RF-clean operands
(E+O+imm = one collection cycle; no reuse dependence).
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402

SCHED = "[7:7:{}:1:0]"
PACKED = "HFMA2 RZ, R24, R25, 0f3f803f80"
SCALAR = "FFMA RZ, R24, R25, 0f3f800000"
INTOP = "IADD3 RZ, R24, R25, RZ"
IMADOP = "IMAD RZ, R24, R25, RZ"
DADDOP = "DADD {RZ,RZ}, {RZ,RZ}, {RZ,RZ}"
MMAOP = "HFMA2.MMA RZ, R24, R25, 0f3f803f80"


def stream(mode: str, n: int) -> list[str]:
    if mode == "pure_packed":
        ops = [PACKED] * n
    elif mode == "pure_ffma":
        ops = [SCALAR] * n
    elif mode == "pure_int":
        ops = [INTOP] * n
    elif mode == "alt_packed_int":
        ops = [PACKED if i % 2 == 0 else INTOP for i in range(n)]
    elif mode == "alt_packed_ffma":
        ops = [PACKED if i % 2 == 0 else SCALAR for i in range(n)]
    elif mode == "alt_packed_nop":
        ops = [PACKED if i % 2 == 0 else "NOP" for i in range(n)]
    elif mode == "alt_int_imad":
        ops = [INTOP if i % 2 == 0 else IMADOP for i in range(n)]
    elif mode == "alt_int_dadd":
        ops = [INTOP if i % 2 == 0 else DADDOP for i in range(n)]
    elif mode == "alt_imad_dadd":
        ops = [IMADOP if i % 2 == 0 else DADDOP for i in range(n)]
    elif mode == "alt_imad_packed":
        ops = [IMADOP if i % 2 == 0 else PACKED for i in range(n)]
    elif mode == "alt_packed_dadd":
        ops = [PACKED if i % 2 == 0 else DADDOP for i in range(n)]
    elif mode == "alt_mma_dadd":
        ops = [MMAOP if i % 2 == 0 else DADDOP for i in range(n)]
    elif mode == "alt_mma_packed":
        ops = [MMAOP if i % 2 == 0 else PACKED for i in range(n)]
    elif mode == "alt_int_nop":
        ops = [INTOP if i % 2 == 0 else "NOP" for i in range(n)]
    elif mode == "alt_imad_nop":
        ops = [IMADOP if i % 2 == 0 else "NOP" for i in range(n)]
    elif mode == "alt_dadd_nop":
        ops = [DADDOP if i % 2 == 0 else "NOP" for i in range(n)]
    elif mode == "alt_int_ffma":
        ops = [INTOP if i % 2 == 0 else SCALAR for i in range(n)]
    elif mode == "alt_imad_ffma":
        ops = [IMADOP if i % 2 == 0 else SCALAR for i in range(n)]
    elif mode == "handoff_p2s":
        ops = [PACKED] * 32 + [SCALAR] * n
    elif mode == "handoff_s2p":
        ops = [SCALAR] * 32 + [PACKED] * n
    else:
        raise ValueError(mode)
    return [f"    {op};{SCHED}" for op in ops]


def source(mode: str, n: int) -> str:
    lines = [
        "#fn pkclamp(out<8>) {",
        "    #pragma MAXREG_COUNT(40)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:2:0]",
        "    S2R R0, SR_TID.X;[2:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R2,R3}, R0, 0x10, {R2,R3};[7:7:{0,2}:5:1]",
        "    MOV R24, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV R25, 0x40003c00;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += stream(mode, n)
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[0:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+0x8], {R22,R23};[0:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(mode: str, n: int, reps: int) -> float:
    mod = CudaModule(assemble(source(mode, n), arch="sm90",
                              check_deps=False))
    out = mod.devmem_alloc(32 * 16)
    vals: list[int] = []
    try:
        for rep in range(reps + 1):
            mod.launch("pkclamp", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            if rep:
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return statistics.median(vals)


MODES = ("pure_packed", "pure_ffma", "pure_int", "alt_packed_int",
         "alt_packed_ffma", "alt_packed_nop", "handoff_p2s", "handoff_s2p",
         "alt_int_imad", "alt_int_dadd", "alt_imad_dadd", "alt_imad_packed",
         "alt_packed_dadd", "alt_mma_dadd", "alt_mma_packed",
         "alt_int_ffma", "alt_imad_ffma",
         "alt_int_nop", "alt_imad_nop", "alt_dadd_nop")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--counts", default="1,2,4,8,16,32")
    p.add_argument("--reps", type=int, default=9)
    ns = p.parse_args()
    for n in [int(x) for x in ns.counts.split(",")]:
        t = measure(ns.mode, n, ns.reps)
        nops = 32 + n if ns.mode.startswith("handoff") else n
        print(f"N={n:3d} span={t:8.1f} per_op={t / max(nops, 1):7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
