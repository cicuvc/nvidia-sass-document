#!/usr/bin/env python3
"""Align hot LDG.32 completions from two warps and probe per-subcore RF banks.

Warp 0 is the timed victim.  Warp 4 is the established same-subcore contender;
warp 1 is the different-subcore control.  ``phase`` pads either victim or
contender before its timed load, allowing both return phases to be swept.  The
victim writes R40 (even); the contender writes R42 (even) or R41 (odd).

The endpoint is warp 0's actual SB4 release.  A same-subcore E contender that
adds delay beyond the O contender and beyond the warp-1 E/O difference is a
direct two-warp same-bank writeback collision.
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


def source(phase: int, contender_parity: str, active: bool = True) -> str:
    vpad = max(0, -phase)
    cpad = max(0, phase)
    creg = 42 if contender_parity == "E" else 41
    lines = [
        "#fn scmio(out<8>, data<8>, contender_warp<4>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(data);[2:7:{}:1:0]",
        "    LDC R12, #param(contender_warp);[3:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{4}:5:1]",
        # Warm exactly the timed line in every warp and retire it.
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
    if active:
        lines += [
            f"    LDG.E R{creg}, desc[{{UR4,UR5}}][{{R6,R7}}];[4:7:{{}}:1:1]",
            f"    IADD3 R33, R{creg}, RZ, RZ;[7:7:{{4}}:5:1]",
        ]
    else:
        # Preserve the contender path's dynamic instruction count without a
        # memory request, scoreboard claim, or GPR write.
        lines += ["    NOP;[7:7:{}:1:1]", "    NOP;[7:7:{}:5:1]"]
    lines += [
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_case(phase: int, parity: str, contender_warp: int,
             reps: int, active: bool = True) -> list[int]:
    mod = CudaModule(assemble(source(phase, parity, active), check_deps=True))
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(128)
    mod.device_write(data, struct.pack("<32I", *([0x12345678] * 32)))
    try:
        vals = []
        for rep in range(reps + 1):
            mod.launch("scmio", grid=(1,), block=(256,),
                       args=[out, data, contender_warp])
            mod.synchronize()
            t0, t1, got = struct.unpack("<QQI", mod.device_read(out, 20))
            if got != 0x12345678:
                raise RuntimeError(f"bad victim LDG result 0x{got:08x}")
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
        return vals
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phases", default="-12,-8,-4,-2,-1,0,1,2,4,8,12")
    p.add_argument("--reps", type=int, default=50)
    ns = p.parse_args()
    phases = [int(x) for x in ns.phases.split(",") if x.strip()]
    if not phases or ns.reps <= 0:
        p.error("phases must be nonempty and reps positive")
    print("two-warp hot LDG.32 return alignment; victim warp0 -> R40(E)")
    print("phase sameE sameO sameC E-C O-C diffE diffO  bankDID | distributions")
    for phase in phases:
        rows = {(place, parity): run_case(
                    phase, parity, 4 if place == "same" else 1, ns.reps)
                for place in ("same", "diff") for parity in ("E", "O")}
        rows[("same", "C")] = run_case(phase, "E", 4, ns.reps, False)
        # Scheduling occasionally selects a rare mode (for example one 46 in
        # an otherwise solid 52-cycle population).  Median is the primary
        # phase-comparison statistic; the full histogram remains visible.
        med = {k: statistics.median(v) for k, v in rows.items()}
        ds = med[("same", "E")] - med[("same", "O")]
        dd = med[("diff", "E")] - med[("diff", "O")]
        dist = " ".join(
            f"{pl}{pa}:{dict(sorted(collections.Counter(rows[(pl, pa)]).items()))}"
            for pl, pa in (("same", "E"), ("same", "O"),
                           ("same", "C"), ("diff", "E"), ("diff", "O")))
        sc = med[("same", "C")]
        print(f"{phase:5d} {med[('same','E')]:5.1f} {med[('same','O')]:5.1f} "
              f"{sc:5.1f} {med[('same','E')]-sc:+4.1f} "
              f"{med[('same','O')]-sc:+4.1f} {med[('diff','E')]:5.1f} "
              f"{med[('diff','O')]:5.1f} {ds-dd:+8.1f} | {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
