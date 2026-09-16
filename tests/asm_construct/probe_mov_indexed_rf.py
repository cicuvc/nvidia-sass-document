#!/usr/bin/env python3
"""Measure MOV uniform-indexed GPR read/write paths on SM120."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


def setup() -> list[str]:
    lines = []
    for j in range(16):
        lines.append(f"    UMOV UR{8+j}, 0x{64+j:x};[7:7:{{}}:5:1]")
    for r in range(64, 192):
        lines.append(f"    MOV32I R{r}, 0x{r:08x};[7:7:{{}}:5:1]")
    return lines


def mov_inst(direction: str, indexed: bool, i: int) -> str:
    j = i % 16
    src = 64 + j
    dst = 128 + j
    if direction == "read":
        return (f"MOV R{dst}, R[UR{8+j}]" if indexed else
                f"MOV R{dst}, R{src}")
    return (f"MOV R[UR{8+j}], R{128+j}" if indexed else
            f"MOV R{src}, R{128+j}")


def rate_source(direction: str, indexed: bool, count: int) -> str:
    lines = [
        "#fn midxrate(out<8>) {",
        "    #pragma MAXREG_COUNT(208)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        *setup(),
        "    CS2R {R4,R5}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += [f"    {mov_inst(direction, indexed, i)};[7:7:{{}}:1:1]"
              for i in range(count)]
    lines += [
        "    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R4,R5};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R6,R7};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_clock(source: str, reps: int, fn: str = "midxrate",
              block: int = 32) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(source, check_deps=False))
    out = mod.devmem_alloc(32)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch(fn, grid=(1,), block=(block,), args=[out])
            mod.synchronize()
            a, b = struct.unpack("<QQ", mod.device_read(out, 16))
            if rep:
                vals.append((b - a) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return vals


def rate_main(ns: argparse.Namespace) -> int:
    print("dir count direct-min direct-med index-min index-med delta/inst")
    for direction in ("read", "write"):
        for n in ns.counts:
            d = run_clock(rate_source(direction, False, n), ns.reps)
            x = run_clock(rate_source(direction, True, n), ns.reps)
            delta = statistics.median(x) - statistics.median(d)
            print(f"{direction:5s} {n:5d} {min(d):10d} "
                  f"{statistics.median(d):10.1f} {min(x):9d} "
                  f"{statistics.median(x):9.1f} {delta/n:+10.4f}")
    return 0


def selector_source(gap: int, overwrite: bool) -> str:
    lines = [
        "#fn midxsel(out<8>) {",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    UMOV UR4, 0x28;[7:7:{}:5:1]",
        "    MOV32I R40, 0x11111111;[7:7:{}:5:1]",
        "    MOV32I R44, 0x22222222;[7:7:{}:5:1]",
    ]
    op = "    MOV R50, R[UR4];[7:7:{}:1:1]"
    wr = "    UMOV UR4, 0x2c;[7:7:{}:1:1]"
    pad = ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    lines += ([op] + pad + [wr]) if overwrite else ([wr] + pad + [op])
    lines += [
        "    STG.E.STRONG.GPU [{R2,R3}], R50;[7:1:{1}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def selector_main(ns: argparse.Namespace) -> int:
    print("direction gap value")
    for overwrite in (False, True):
        for gap in range(ns.max_gap + 1):
            reset_context()
            mod = CudaModule(assemble(selector_source(gap, overwrite),
                                      check_deps=False))
            out = mod.devmem_alloc(16)
            try:
                mod.launch("midxsel", grid=(1,), block=(32,), args=[out])
                mod.synchronize()
                val, = struct.unpack("<I", mod.device_read(out, 4))
            finally:
                mod.devmem_free(out)
            direction = "overwrite" if overwrite else "producer"
            print(f"{direction:9s} {gap:3d} 0x{val:08x}")
    return 0


def interference_source(indexed: bool, contender_warp: int, contender_n: int,
                        victim_n: int, victim: str) -> str:
    lines = [
        "#fn midxinterf(out<8>) {",
        "    #pragma MAXREG_COUNT(208)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    MOV32I R196, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R198, 0x40000000;[7:7:{}:5:1]",
        "    UMOV UR60, 0;[7:7:{}:5:1]",
        "    UMOV UR61, 1;[7:7:{}:5:1]",
        "    UMOV UR62, 2;[7:7:{}:5:1]",
        *setup(),
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        f"    ISETP.EQ.AND P0, PT, R5, 0x{contender_warp:x}, PT;[7:7:{{}}:13:1]",
        "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
        "    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    if victim == "scalar":
        lines += ["    FADD RZ, R196, R198;[7:7:{}:1:1]"
                  for _ in range(victim_n)]
    else:
        lines += ["    UIADD3 UR60, UPT, UPT, UR61, UR62, URZ;[7:7:{}:1:1]"
                  for _ in range(victim_n)]
    lines += [
        "    CS2R {R8,R9}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R6,R7};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R8,R9};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
    ]
    lines += [f"    {mov_inst('read', indexed, i)};[7:7:{{}}:1:1]"
              for i in range(contender_n)]
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def interference_main(ns: argparse.Namespace) -> int:
    print(f"victim={ns.victim}: direct/indexed MOV contender")
    print("place mode       min median cycles/victim")
    for place, warp in (("same", 4), ("diff", 1)):
        for indexed in (False, True):
            vals = run_clock(interference_source(
                indexed, warp, ns.contender_count, ns.victim_count, ns.victim),
                ns.reps, fn="midxinterf", block=256)
            mode = "indexed" if indexed else "direct"
            print(f"{place:5s} {mode:7s} {min(vals):6d} "
                  f"{statistics.median(vals):7.1f} "
                  f"{statistics.median(vals)/ns.victim_count:10.4f}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    pr = sub.add_parser("rate")
    pr.add_argument("--counts", default="256,512,1024,2048")
    pr.add_argument("--reps", type=int, default=20)
    ps = sub.add_parser("selector")
    ps.add_argument("--max-gap", type=int, default=8)
    pi = sub.add_parser("interference")
    pi.add_argument("--victim", choices=("scalar", "uniform"), default="scalar")
    pi.add_argument("--victim-count", type=int, default=4096)
    pi.add_argument("--contender-count", type=int, default=4096)
    pi.add_argument("--reps", type=int, default=20)
    ns = p.parse_args()
    if ns.mode == "rate":
        ns.counts = [int(x) for x in ns.counts.split(",")]
        return rate_main(ns)
    if ns.mode == "interference":
        return interference_main(ns)
    return selector_main(ns)


if __name__ == "__main__":
    raise SystemExit(main())
