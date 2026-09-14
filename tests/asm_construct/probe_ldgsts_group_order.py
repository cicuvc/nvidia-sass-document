#!/usr/bin/env python3
"""Probe whether LDGSTS wait_group retires committed groups in order."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402


def source(cold_pos: int, threshold: int, routing: str) -> str:
    groups = []
    write_sbs = (0, 0, 0) if routing == "same" else (0, 1, 1)
    for i in range(3):
        addr = "{R20,R21}" if i == cold_pos else "{R22,R23}"
        groups += [
            f"    LDGSTS.E.32 [R30+0x{0x400 * (i + 1):x}], "
            f"desc[{{UR4,UR5}}][{addr}];[7:2:{{}}:1:1]",
            f"    LDGDEPBAR;[{write_sbs[i]}:7:{{}}:1:1]",
        ]
    return "\n".join([
        "#fn grouporder(out<8>, cold<8>, hot<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    #pragma SHARED(0x1000)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(cold);[2:7:{}:1:0]",
        "    LDC.64 {R8,R9}, #param(hot);[3:7:{}:1:0]",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[4:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[5:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R4, 0x18, {R2,R3};[7:7:{1,5}:5:1]",
        # The cold group touches 32 independent 128-B lines; hot is coalesced.
        "    IMAD.WIDE.U32 {R20,R21}, R4, 0x80, {R6,R7};[7:7:{2,5}:5:1]",
        "    IMAD.WIDE.U32 {R22,R23}, R4, 0x4, {R8,R9};[7:7:{3,5}:5:1]",
        "    SHF.L.U32 R30, R4, 0x2, RZ;[7:7:{5}:5:1]",
        # Warm only the hot line through an ordinary LDG.
        "    LDG.E.STRONG.GPU R40, desc[{UR4,UR5}][{R22,R23}];[5:7:{4}:1:1]",
        "    MOV RZ, R40;[7:7:{5}:5:1]",
        "    STS [R30+0x400], RZ;[7:7:{}:1:1]",
        "    STS [R30+0x800], RZ;[7:7:{}:1:1]",
        "    STS [R30+0xc00], RZ;[7:7:{}:1:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        *groups,
        "    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    DEPBAR.LE SB{0 if routing == 'same' else 1}, "
        f"0x{threshold:x};[7:7:{{}}:5:1]",
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    LDS R40, [R30+0x{0x400 if routing == 'same' else 0x800:x}];"
        "[5:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R24,R25};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x8], {R26,R27};[7:7:{}:8:0]",
        "    STG.E.STRONG.GPU [{R10,R11}+0x10], R40;[7:7:{5}:8:0]",
        "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        *( ["    DEPBAR.LE SB1, 0x0;[7:7:{}:5:1]"] if routing == "cross" else [] ),
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cold-pos", type=int, choices=range(4), default=0,
                    help="0..2 selects one cold group; 3 means all hot")
    ap.add_argument("--threshold", type=int, choices=range(4), default=2)
    ap.add_argument("--routing", choices=("same", "cross"), default="same")
    ap.add_argument("--reps", type=int, default=31)
    ns = ap.parse_args()
    mod = CudaModule(assemble(source(ns.cold_pos, ns.threshold, ns.routing), arch="sm120",
                              check_deps=False))
    out = mod.devmem_alloc(32 * 24)
    # Sweep fresh cold lines; the hot allocation is explicitly touched in-kernel.
    cold = mod.devmem_alloc(ns.reps * 0x1000 + 128)
    hot = mod.devmem_alloc(128)
    mod.devmem_set(cold, 0x11223344, (ns.reps * 0x1000 + 128) // 4)
    mod.devmem_set(hot, 0x55667788, 32)
    waits, bad = [], 0
    try:
        for rep in range(ns.reps):
            mod.launch("grouporder", grid=(1,), block=(32,),
                       args=[out, cold + rep * 0x1000, hot], shared_mem=0x1000)
            mod.synchronize()
            raw = mod.device_read(out, 32 * 24)
            vals = [struct.unpack_from("<QQI", raw, lane * 24) for lane in range(32)]
            waits.append(vals[0][1] - vals[0][0])
            read_pos = 0 if ns.routing == "same" else 1
            expect = 0x11223344 if ns.cold_pos == read_pos else 0x55667788
            bad += sum(value != expect for _, _, value in vals)
    finally:
        mod.devmem_free(hot)
        mod.devmem_free(cold)
        mod.devmem_free(out)
    print(f"routing={ns.routing} cold_pos={ns.cold_pos} "
          f"wait_group={ns.threshold} reps={ns.reps} "
          f"wait median={statistics.median(waits):.0f} "
          f"range={min(waits)}..{max(waits)} bad_lanes={bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
