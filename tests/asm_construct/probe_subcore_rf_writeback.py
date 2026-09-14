#!/usr/bin/env python3
"""Cross-warp localization of the parity-banked GPR write port on GB202.

Warp 0 times a warmed LDG.32 -> R40(E) through its real SB4 release.  A
contender warp issues a reuse-fed FFMA stream whose destinations are all E or
all O.  Warp 4 is on warp 0's subcore; warp 1 is the different-subcore control.
Predicated-off FFMA streams retain fetch/issue/dispatch but perform no operand
read, execution, or GPR write.

For each parity, the structural writeback score is:

  (same_active - same_pred) - (diff_active - diff_pred)

Only the E score should be positive if the LDG and FFMA results share a 1W
even-bank port local to the subcore.  The E-minus-O score removes remaining
parity-independent execution effects.
"""

from __future__ import annotations

import argparse
import collections
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


def source(n: int, parity: str, pred: bool, phase: int) -> str:
    p = 0 if parity == "E" else 1
    dsts = [42 + p + 2 * i for i in range(20)]
    vpad, cpad = max(0, -phase), max(0, phase)
    guard = "@P6 " if pred else ""
    lines = [
        "#fn scrfwb(out<8>, data<8>, contender_warp<4>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(data);[2:7:{}:1:0]",
        "    LDC R12, #param(contender_warp);[3:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{4}:5:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f000000;[7:7:{}:5:1]",
    ]
    for r in dsts:
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    lines += [
        "    LDG.E R30, desc[{UR4,UR5}][{R6,R7}];[5:7:{0,2}:5:1]",
        "    IADD3 R31, R30, RZ, RZ;[7:7:{5}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, R12, PT;[7:7:{3}:13:1]",
        "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
    ]
    lines += ["    NOP;[7:7:{}:1:0]" for _ in range(vpad)]
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    LDG.E R40, desc[{UR4,UR5}][{R6,R7}];[4:7:{}:1:1]",
        "    IADD3 R32, R40, RZ, RZ;[7:7:{4}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]",
        "    STG.E.STRONG.GPU [{R2,R3}+0x10], R32;[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
    ]
    lines += ["    NOP;[7:7:{}:1:0]" for _ in range(cpad)]
    for i in range(n):
        lines.append(
            f"    {guard}FFMA R{dsts[i % len(dsts)]}, R24, R27, R28;"
            "[7:7:{}:1:0:7]")
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run_case(n: int, parity: str, pred: bool, phase: int,
             contender_warp: int, reps: int) -> list[int]:
    mod = CudaModule(assemble(source(n, parity, pred, phase), check_deps=True))
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(128)
    mod.device_write(data, struct.pack("<32I", *([0x12345678] * 32)))
    try:
        vals = []
        for rep in range(reps + 1):
            mod.launch("scrfwb", grid=(1,), block=(256,),
                       args=[out, data, contender_warp])
            mod.synchronize()
            t0, t1, got = struct.unpack("<QQI", mod.device_read(out, 20))
            if got != 0x12345678:
                raise RuntimeError(f"bad victim result 0x{got:08x}")
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
        return vals
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--counts", default="8,16,24,32,40,48,64")
    p.add_argument("--phases", default="-8,-4,0,4,8")
    p.add_argument("--reps", type=int, default=30)
    ns = p.parse_args()
    counts = [int(x) for x in ns.counts.split(",") if x.strip()]
    phases = [int(x) for x in ns.phases.split(",") if x.strip()]
    if not counts or min(counts) < 0 or not phases or ns.reps <= 0:
        p.error("counts must be nonnegative; phases nonempty; reps positive")
    print("cross-warp FFMA-write storm vs warp0 hot LDG->R40(E)")
    print(" N phase  sEa sEp  sOa sOp  dEa dEp  dOa dOp | Escore Oscore E-O")
    for n in counts:
        for phase in phases:
            rows = {}
            for place, warp in (("s", 4), ("d", 1)):
                for parity in ("E", "O"):
                    for pred in (False, True):
                        rows[(place, parity, pred)] = run_case(
                            n, parity, pred, phase, warp, ns.reps)
            med = {k: statistics.median(v) for k, v in rows.items()}
            es = ((med[("s", "E", False)] - med[("s", "E", True)])
                  - (med[("d", "E", False)] - med[("d", "E", True)]))
            os = ((med[("s", "O", False)] - med[("s", "O", True)])
                  - (med[("d", "O", False)] - med[("d", "O", True)]))
            vals = [med[(pl, pa, pr)] for pl in ("s", "d")
                    for pa in ("E", "O") for pr in (False, True)]
            print(f"{n:2d} {phase:5d} " + " ".join(f"{v:4.0f}" for v in vals)
                  + f" | {es:+6.1f} {os:+6.1f} {es-os:+5.1f}")
            # Print distributions only where a structural score is nonzero.
            if es or os:
                for k, v in rows.items():
                    print(f"    {k}: {dict(sorted(collections.Counter(v).items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
