#!/usr/bin/env python3
"""Measure Hopper HGMMA interaction with MIO/LSU/XU instruction streams.

Warpgroup 0 (warps 0..3) runs an HGMMA m64n16k16 chain.  Warpgroup 1
(warps 4..7) runs a selectable contender on all four subcores.  Both sides
record issue-span clocks independently; HGMMA additionally records the time
after its gsb0 DEPBAR.  ``solo_h`` and ``solo_c`` retain the same 256-thread
CTA and control flow, so overlay ratios do not include an occupancy change.

The first HGMMA overwrites its accumulator and the tail writes gsb0.
Intermediate MMAs have no group-scoreboard write, matching ptxas's normal
chained form.  ``--operand ss`` reads both inputs from shared memory;
``--operand rs`` supplies A from R56..R59 and reads only B from shared.  The
descriptors point at valid 1-KiB-aligned regions inside the CTA's 16-KiB
allocation; operand values need not be initialized for timing.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OPS = ("nop", "iadd", "bmov", "mufu", "shfl", "shfl_zd", "shfl_zz",
       "lds", "lds_zd", "lds_conflict", "ldsm", "sts", "ldg", "stg",
       "ffma_we", "ffma_wo", "ffma_wb", "ffma_we_off", "ffma_wo_off",
       "ffma_wb_off", "ffma_wz", "ffma_we_m0", "ffma_we_m1",
       "ffma_we_m2", "ffma_we_m3", "ffma_we_m4", "ffma_we_m5",
       "ffma_we_m6", "ffma_we_m7", "mov_we", "mov_wo", "mov_wb",
       "mov_wz", "ffma_ro")
MODES = ("solo_h", "solo_c", "overlay", "pred_h")


def hgmma_body(n: int, shape: int = 16, operand: str = "ss",
                mma: str = "hgmma",
                qfmt: str = "E4M3",
                accum: str = "rmw",
                pred_off: bool = False) -> list[str]:
    guard = "@P6 " if pred_off else ""
    nregs = {8: 4, 16: 8, 64: 32}[shape]
    dst = "{" + ",".join(f"R{i}" for i in range(24, 24 + nregs)) + "}"
    lines: list[str] = []
    opcode = (f"HGMMA.64x{shape}x16.F32.BF16" if mma == "hgmma" else
              f"QGMMA.64x{shape}x32.F32.{qfmt}.{qfmt}")
    for i in range(n):
        overwrite = i == 0 or accum == "overwrite"
        src = "RZ" if overwrite else dst
        scale = "!UPT" if overwrite else "UPT"
        gsb = ", gsb0" if i == n - 1 else ""
        operands = (f"gdesc[UR4], {src}" if operand == "ss" else
                    f"{{R56,R57,R58,R59}}, gdesc[UR8], {src}")
        lines.append(f"    {guard}{opcode} {dst}, "
                     f"{operands}, {scale}{gsb};[7:7:{{}}:4:0]")
    return lines


def contender_body(op: str, n: int) -> list[str]:
    lines: list[str] = []
    for i in range(n):
        rd = 64 + i % 48
        if op == "nop":
            inst = "NOP"
        elif op == "iadd":
            inst = f"IADD3 R{rd}, R40, RZ, RZ"
        elif op == "mufu":
            inst = f"MUFU.RCP R{rd}, R40"
        elif op == "bmov":
            inst = f"BMOV.32 R{rd}, MACTIVE"
        elif op == "shfl":
            inst = f"SHFL.BFLY PT, R{rd}, R40, 0x1, 0x1f"
        elif op == "shfl_zd":
            inst = "SHFL.BFLY PT, RZ, R40, 0x1, 0x1f"
        elif op == "shfl_zz":
            inst = "SHFL.BFLY PT, RZ, RZ, 0x1, 0x1f"
        elif op == "lds":
            inst = f"LDS R{rd}, [RZ]"
        elif op == "lds_zd":
            inst = "LDS RZ, [RZ]"
        elif op == "lds_conflict":
            inst = f"LDS R{rd}, [R42]"
        elif op == "ldsm":
            base = 64 + 4 * (i % 12)
            inst = (f"LDSM.16.M88.4 "
                    f"{{R{base},R{base+1},R{base+2},R{base+3}}}, [R43]")
        elif op == "sts":
            inst = "STS [R43], R40"
        elif op == "ldg":
            inst = (f"LDG.E.STRONG.GPU R{rd}, "
                    f"[{{R16,R17}}+0x{(i % 256) * 128:x}]")
        elif op == "stg":
            inst = (f"STG.E.STRONG.GPU [{{R16,R17}}+0x{(i % 256) * 128:x}], "
                    "R40")
        elif op == "ffma_ro":
            # Read-only RF stress: E/O/E source-bank pattern, no reuse flags,
            # and RZ destination.  Rotate through 30 pairs so no operand can
            # remain resident in an implementation-specific collector cache.
            r0 = 64 + 2 * (i % 30)
            r1 = 65 + 2 * ((i + 7) % 30)
            r2 = 64 + 2 * ((i + 13) % 30)
            lines.append(
                f"    FFMA RZ, R{r0}, R{r1}, R{r2};[7:7:{{}}:1:0]"
            )
            continue
        elif op.startswith("ffma_w"):
            if op == "ffma_wz":
                dst = 255
            elif "wb" in op:
                parity = i & 1
                dst = 64 + parity + 2 * (i % 24)
            else:
                parity = 0 if "we" in op else 1
                dst = 64 + parity + 2 * (i % 24)
            guard = "@P6 " if op.endswith("_off") else ""
            dtext = "RZ" if dst == 255 else f"R{dst}"
            mask = int(op.rsplit("m", 1)[1]) if "_m" in op else 7
            reuse = "" if mask == 0 else f":{mask}"
            lines.append(
                f"    {guard}FFMA {dtext}, R116, R117, R118;"
                f"[7:7:{{}}:1:0{reuse}]"
            )
            continue
        elif op.startswith("mov_w"):
            if op == "mov_wz":
                dtext = "RZ"
            else:
                parity = (i & 1) if op == "mov_wb" else (0 if op == "mov_we" else 1)
                dtext = f"R{64 + parity + 2 * (i % 24)}"
            lines.append(f"    MOV32I {dtext}, 0x3f800000;[7:7:{{}}:1:0]")
            continue
        else:
            raise ValueError(op)
        lines.append(f"    {inst};[7:7:{{}}:1:1]")
    return lines


def source(op: str, hn: int, cn: int, mode: str, shape: int = 16,
           operand: str = "ss",
           mma: str = "hgmma",
           qfmt: str = "E4M3",
           accum: str = "rmw",
           hdelay: int = 0, cdelay: int = 0) -> str:
    run_h = mode in ("solo_h", "overlay", "pred_h")
    # pred_h keeps the same second warpgroup active.  With roughly twice as
    # many predicated-off HGMMAs as active n16 HGMMAs, its scheduling span is
    # comparable and isolates warpgroup/control dispatch from TC/MIO work.
    run_c = mode in ("solo_c", "overlay", "pred_h")
    lines = [
        "#fn hgmio(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(128)",
        "    #pragma SHARED(16384)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x20, {R2,R3};[7:7:{0,2}:5:1]",
        "    IMAD.WIDE.U32 {R16,R17}, R4, 0x4, {R14,R15};[7:7:{1,2}:5:1]",
        "    LOP3.LUT R42, R4, 0x1f, RZ, 0xc0;[7:7:{2}:5:1]",
        "    IMAD.U32 R42, R42, 0x80, RZ;[7:7:{}:5:1]",
        "    LOP3.LUT R43, R4, 0x1f, RZ, 0xc0;[7:7:{2}:5:1]",
        "    IMAD.U32 R43, R43, 0x10, RZ;[7:7:{}:5:1]",
        "    IADD3 R43, R43, 0x1000, RZ;[7:7:{}:5:1]",
        "    MOV32I R40, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R56, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R57, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R58, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R59, 0x3f803f80;[7:7:{}:5:1]",
        # E/O/E sources for the parity-controlled FFMA write storm.  Reuse
        # mask 7 makes all but the first FFMA almost pure write traffic.
        "    MOV32I R116, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R117, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R118, 0x3f000000;[7:7:{}:5:1]",
        # Raw PTX matrix descriptors: A at 0x400, B at 0xc00.
        "    UMOV UR4, 0x400040;[7:7:{}:5:1]",
        "    UMOV UR5, 0x0;[7:7:{}:5:1]",
        "    UMOV UR6, 0x4000c0;[7:7:{}:5:1]",
        "    UMOV UR7, 0x0;[7:7:{}:5:1]",
        "    UMOV UR8, 0x4000c0;[7:7:{}:5:1]",
        "    UMOV UR9, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.LT.U32.AND P0, PT, R5, 0x4, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(hpath);[7:7:{}:5:1]",
        "    BRA #label(cpath);[7:7:{}:5:1]",
        "#def_label(hpath)",
    ]
    if run_h:
        lines += [
            "    WARPGROUP.ARRIVE;[7:7:{}:5:1]",
        ]
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(hdelay)]
        lines += ["    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]"]
        lines += hgmma_body(hn, shape, operand, mma, qfmt, accum,
                            pred_off=(mode == "pred_h"))
        lines += [
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        ]
        if mode != "pred_h":
            lines += ["    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]"]
        lines += [
            "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    BRA #label(record);[7:7:{}:5:1]",
        ]
    else:
        lines += [
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    BRA #label(record);[7:7:{}:5:1]",
        ]
    lines += ["#def_label(cpath)"]
    if run_c:
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(cdelay)]
        lines += ["    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]"]
        lines += contender_body(op, cn)
        lines += [
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    MOV R22, R20;[7:7:{}:5:1]",
            "    MOV R23, R21;[7:7:{}:5:1]",
        ]
    else:
        lines += [
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    MOV R22, R20;[7:7:{}:5:1]",
            "    MOV R23, R21;[7:7:{}:5:1]",
        ]
    lines += [
        "#def_label(record)",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R18,R19};[7:3:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R20,R21};[7:3:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x10], {R22,R23};[7:3:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def measure(op: str, hn: int, cn: int, mode: str, reps: int, shape: int = 16,
            operand: str = "ss",
            mma: str = "hgmma",
            qfmt: str = "E4M3",
            accum: str = "rmw",
            hdelay: int = 0, cdelay: int = 0) -> tuple[float, float, float]:
    cubin = assemble(source(op, hn, cn, mode, shape, operand, mma, qfmt, accum,
                            hdelay, cdelay),
                     arch="sm90", check_deps=True)
    mod = CudaModule(cubin)
    out = mod.devmem_alloc(256 * 32)
    data = mod.devmem_alloc(256 * 128 + 4096)
    mod.devmem_set(data, 0x3f803f80, (256 * 128 + 4096) // 4)
    hissue: list[int] = []
    hdrain: list[int] = []
    cissue: list[int] = []
    try:
        for rep in range(reps + 1):
            mod.launch("hgmio", grid=(1,), block=(256,), args=[out, data])
            mod.synchronize()
            if rep:
                h0, h1, h2 = struct.unpack(
                    "<QQQ", mod.device_read(out, 24))
                c0, c1, _ = struct.unpack(
                    "<QQQ", mod.device_read(out + 128 * 32, 24))
                hissue.append((h1 - h0) & ((1 << 64) - 1))
                hdrain.append((h2 - h0) & ((1 << 64) - 1))
                cissue.append((c1 - c0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return (statistics.median(hissue), statistics.median(hdrain),
            statistics.median(cissue))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--op", choices=OPS, default="mufu")
    p.add_argument("--hgmma-count", type=int, default=64)
    p.add_argument("--contender-count", type=int, default=512)
    p.add_argument("--shape", type=int, choices=(8, 16, 64), default=16)
    p.add_argument("--operand", choices=("ss", "rs"), default="ss")
    p.add_argument("--mma", choices=("hgmma", "qgmma"), default="hgmma")
    p.add_argument("--qfmt", choices=("E4M3", "E5M2"), default="E4M3")
    p.add_argument("--accum", choices=("rmw", "overwrite"), default="rmw")
    p.add_argument("--mode", choices=MODES + ("matrix",), default="matrix")
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--hdelay", type=int, default=0,
                   help="NOP instructions before the HGMMA clock starts")
    p.add_argument("--cdelay", type=int, default=0,
                   help="NOP instructions before contender clock starts")
    ns = p.parse_args()
    if min(ns.hgmma_count, ns.contender_count, ns.reps) <= 0:
        p.error("counts and reps must be positive")
    modes = MODES if ns.mode == "matrix" else (ns.mode,)
    for mode in modes:
        hi, hd, ci = measure(ns.op, ns.hgmma_count, ns.contender_count,
                             mode, ns.reps, ns.shape, ns.operand,
                             ns.mma, ns.qfmt, ns.accum, ns.hdelay, ns.cdelay)
        print(f"mma={ns.mma:6s} op={ns.op:12s} mode={mode:7s} "
              f"Hissue/op={hi/ns.hgmma_count:8.3f} "
              f"Hdrain/op={hd/ns.hgmma_count:8.3f} "
              f"Cissue/op={ci/ns.contender_count:8.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
