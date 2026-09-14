#!/usr/bin/env python3
"""Measure cp.async group accounting across divergent warp execution groups.

The useful observable is the DEPBAR.LE threshold at which the wait changes
from a memory-latency wait to an immediate pass.  Each submitted copy uses
lane-scattered cold-ish source lines so that its committed group is still
incomplete when the threshold is tested.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble  # noqa: E402


def copy(round_: int, item: int = 0) -> str:
    # One 4-byte item per active lane, with lanes on separate 128-byte lines.
    return (
        f"    LDGSTS.E.32 [R30+0x{round_ * 0x100:x}], "
        f"desc[{{UR4,UR5}}][{{R20,R21}}+0x{(round_ * 32 + item) * 0x2000:x}];"
        "[7:2:{}:1:1]"
    )


def batch(round_: int, copies: int, pred: str = "") -> list[str]:
    prefix = f"    @{pred} LDGSTS" if pred else "    LDGSTS"
    return [copy(round_, j).replace("    LDGSTS", prefix) for j in range(copies)]


def rounds(mode: str, n: int, copies: int) -> list[str]:
    out: list[str] = []
    for i in range(n):
        if mode == "single":
            out += [*batch(i, copies), "    LDGDEPBAR;[0:7:{}:1:1]"]
        elif mode == "predicated":
            # Two statically distinct commit instructions, one per half warp.
            out += [
                *batch(i, copies, "P0"),
                "    @P0 LDGDEPBAR;[0:7:{}:1:1]",
                *batch(i, copies, "!P0"),
                "    @!P0 LDGDEPBAR;[0:7:{}:1:1]",
            ]
        elif mode == "split_pc":
            # True divergence; each half executes its own copy+commit PC.
            out += [
                f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                f"    @P0 BRA #label(taken_{i});[7:7:{{}}:5:1]",
                *batch(i, copies),
                "    LDGDEPBAR;[0:7:{}:1:1]",
                f"    BRA #label(sync_{i});[7:7:{{}}:5:1]",
                f"    #def_label(taken_{i})",
                *batch(i, copies),
                "    LDGDEPBAR;[0:7:{}:1:1]",
                f"    #def_label(sync_{i})",
                "    BSYNC B0;[7:7:{}:5:1]",
                f"    #def_label(join_{i})",
            ]
        elif mode == "common_pc":
            # Both divergent execution groups reach the SAME static copy and
            # commit PCs before BSYNC performs explicit reconvergence.
            out += [
                f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                f"    @P0 BRA #label(taken_{i});[7:7:{{}}:5:1]",
                "    NOP;[7:7:{}:5:1]",
                f"    BRA #label(common_{i});[7:7:{{}}:5:1]",
                f"    #def_label(taken_{i})",
                "    NOP;[7:7:{}:5:1]",
                f"    #def_label(common_{i})",
                *batch(i, copies),
                "    LDGDEPBAR;[0:7:{}:1:1]",
                "    BSYNC B0;[7:7:{}:5:1]",
                f"    #def_label(join_{i})",
            ]
        elif mode == "reconverged":
            # Control-flow split is closed first; copy+commit sees full warp.
            out += [
                f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                f"    @P0 BRA #label(taken_{i});[7:7:{{}}:5:1]",
                "    NOP;[7:7:{}:5:1]",
                f"    BRA #label(sync_{i});[7:7:{{}}:5:1]",
                f"    #def_label(taken_{i})",
                "    NOP;[7:7:{}:5:1]",
                f"    #def_label(sync_{i})",
                "    BSYNC B0;[7:7:{}:5:1]",
                f"    #def_label(join_{i})",
                *batch(i, copies),
                "    LDGDEPBAR;[0:7:{}:1:1]",
            ]
        elif mode.startswith("brxfanout"):
            width = int(mode.removeprefix("brxfanout"))
            if width not in (2, 4, 8, 16, 32):
                raise ValueError(mode)
            # A single register-indirect branch splits the warp into N target
            # PCs.  The N consecutive BRA instructions then funnel those
            # groups to one common static copy+commit PC.  R40 = group*16.
            out += [
                f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]",
                f"    BRX {{R40,R41}}, #label(path_{i}_0);[7:7:{{}}:5:1]",
            ]
            for group in range(width):
                out += [
                    f"    #def_label(path_{i}_{group})",
                    f"    BRA #label(common_{i});[7:7:{{}}:5:1]",
                ]
            out += [
                f"    #def_label(common_{i})",
                *batch(i, copies),
                "    LDGDEPBAR;[0:7:{}:1:1]",
                "    BSYNC B0;[7:7:{}:5:1]",
                f"    #def_label(join_{i})",
            ]
        elif mode.startswith("fanout"):
            width = int(mode.removeprefix("fanout"))
            if width not in (2, 4, 8, 16, 32):
                raise ValueError(mode)
            # Peel lane groups out of the dispatch path one by one.  Every
            # group branches to one shared static copy+commit PC, then waits
            # at the same BSYNC.  R5 is lane_id >> log2(32/width).
            out.append(f"    BSSY B0, #label(join_{i});[7:7:{{}}:5:1]")
            for group in range(width - 1):
                out += [
                    f"    ISETP.EQ.AND P1, PT, R5, 0x{group:x}, PT;"
                    "[7:7:{}:13:1]",
                    f"    @P1 BRA #label(path_{i}_{group});[7:7:{{}}:5:1]",
                ]
            out.append(f"    BRA #label(path_{i}_{width - 1});[7:7:{{}}:5:1]")
            for group in range(width):
                out += [
                    f"    #def_label(path_{i}_{group})",
                    f"    BRA #label(common_{i});[7:7:{{}}:5:1]",
                ]
            out += [
                f"    #def_label(common_{i})",
                *batch(i, copies),
                "    LDGDEPBAR;[0:7:{}:1:1]",
                "    BSYNC B0;[7:7:{}:5:1]",
                f"    #def_label(join_{i})",
            ]
        else:
            raise ValueError(mode)
    return out


def source(mode: str, n: int, threshold: int, copies: int = 1,
           head_copies: int = 0) -> str:
    if mode.startswith("brxfanout"):
        fanout = int(mode.removeprefix("brxfanout"))
    elif mode.startswith("fanout"):
        fanout = int(mode.removeprefix("fanout"))
    else:
        fanout = 2
    group_shift = (32 // fanout).bit_length() - 1
    return "\n".join([
        "#fn divcommit(out<8>, src<8>) {",
        "    #pragma MAXREG_COUNT(48)",
        "    #pragma SHARED(0x4000)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(src);[2:7:{}:1:0]",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[4:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[5:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R4, 0x20, {R2,R3};[7:7:{1,5}:5:1]",
        "    IMAD.WIDE.U32 {R20,R21}, R4, 0x80, {R6,R7};[7:7:{2,5}:5:1]",
        "    SHF.L.U32 R30, R4, 0x2, RZ;[7:7:{5}:5:1]",
        f"    SHR.U32 R5, R4, 0x{group_shift:x};[7:7:{{5}}:5:1]",
        "    SHF.L.U32 R40, R5, 0x4, RZ;[7:7:{}:5:1]",
        "    MOV R41, RZ;[7:7:{}:5:1]",
        "    ISETP.LT.AND P0, PT, R4, 0x10, PT;[7:7:{5}:13:1]",
        "    CS2R {R24,R25}, SR_CLOCKLO;[7:7:{4}:5:0]",
        *batch(n + 1, head_copies),
        *( ["    LDGDEPBAR;[0:7:{}:1:1]"] if head_copies else [] ),
        *rounds(mode, n, copies),
        "    CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    DEPBAR.LE SB0, 0x{threshold:x};[7:7:{{}}:5:1]",
        "    CS2R {R28,R29}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        "    CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R24,R25};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x8], {R26,R27};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x10], {R28,R29};[7:7:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R10,R11}+0x18], {R32,R33};[7:7:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def measure(mode: str, n: int, threshold: int, reps: int,
            copies: int, head_copies: int) -> tuple[float, ...]:
    cubin = assemble(source(mode, n, threshold, copies, head_copies), arch="sm120",
                     check_deps=False)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(32 * 32)
    span = ((n + 2) * 32 + max(copies, head_copies) + 2) * 0x2000
    stride = (span + 0xffff) & ~0xffff
    src = mod.devmem_alloc(reps * stride)
    mod.devmem_set(src, 0x12345678, reps * stride // 4)
    samples: list[tuple[int, int, int]] = []
    try:
        for rep in range(reps):
            mod.launch("divcommit", grid=(1,), block=(32,),
                       args=[out, src + rep * stride], shared_mem=0x4000)
            mod.synchronize()
            t0, ti, tw, td = struct.unpack_from("<QQQQ", mod.device_read(out, 32), 0)
            samples.append((ti - t0, tw - ti, td - tw))
    finally:
        mod.devmem_free(src)
        mod.devmem_free(out)
    return tuple(statistics.median(x[i] for x in samples) for i in range(3))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modes", default="single,predicated,split_pc,common_pc,reconverged")
    ap.add_argument("--rounds", default="1,2,3")
    ap.add_argument("--thresholds", default="0,1,2,3,4,5,6")
    ap.add_argument("--copies", type=int, default=1,
                    help="LDGSTS operations in each committed subgroup batch")
    ap.add_argument("--head-copies", type=int, default=0,
                    help="long converged FIFO-head batch before divergent work")
    ap.add_argument("--reps", type=int, default=15)
    args = ap.parse_args()
    print("mode rounds LE issue_to_LE LE_wait remaining_drain")
    for mode in args.modes.split(","):
        for n in (int(x) for x in args.rounds.split(",") if x):
            for threshold in (int(x) for x in args.thresholds.split(",") if x):
                issue, wait, drain = measure(mode, n, threshold, args.reps,
                                             args.copies, args.head_copies)
                print(f"{mode:11s} {n:2d} {threshold:2d} "
                      f"{issue:11.0f} {wait:7.0f} {drain:15.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
