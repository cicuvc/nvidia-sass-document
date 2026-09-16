#!/usr/bin/env python3
"""Probe SM120 HMMA indexedRF overhead and uniform-selector timing."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


def hmma(indexed: bool, j: int) -> str:
    base = 64 + 4 * (j % 16)
    acc = f"R[UR{8 + j % 16}]" if indexed else \
          f"{{R{base},R{base+1},R{base+2},R{base+3}}}"
    return (f"HMMA.16816.F32.BF16 {acc}, {{RZ,RZ,RZ,RZ}}, "
            f"{{RZ,RZ}}, {acc}, UPT;[7:7:{{}}:1:0]")


def setup() -> list[str]:
    lines = []
    for j in range(16):
        lines.append(f"    UMOV UR{8+j}, 0x{64+4*j:x};[7:7:{{}}:5:1]")
    for r in range(64, 128):
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    return lines


def timed_source(indexed: bool, count: int) -> str:
    lines = [
        "#fn hidxrate(out<8>) {",
        "    #pragma MAXREG_COUNT(160)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        *setup(),
        "    CS2R {R4,R5}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    " + hmma(indexed, i) for i in range(count)]
    lines += [
        "    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R4,R5};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R6,R7};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_clock_source(source: str, fn: str, block: int, reps: int) -> list[int]:
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
    print("count fixed-min fixed-med indexed-min indexed-med delta/inst")
    for n in ns.counts:
        f = run_clock_source(timed_source(False, n), "hidxrate", 32, ns.reps)
        x = run_clock_source(timed_source(True, n), "hidxrate", 32, ns.reps)
        d = statistics.median(x) - statistics.median(f)
        print(f"{n:5d} {min(f):9d} {statistics.median(f):9.1f} "
              f"{min(x):11d} {statistics.median(x):11.1f} {d/n:+10.4f}")
    return 0


def interference_source(indexed: bool, contender_warp: int, tensor_n: int,
                        victim_n: int, victim: str) -> str:
    lines = [
        "#fn hidxinterf(out<8>) {",
        "    #pragma MAXREG_COUNT(160)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    MOV32I R132, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R134, 0x40000000;[7:7:{}:5:1]",
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
        lines += ["    FADD RZ, R132, R134;[7:7:{}:1:1]"
                  for _ in range(victim_n)]
    else:
        lines += ["    UIADD3 UR60, UPT, UPT, UR61, UR62, URZ;[7:7:{}:1:1]"
                  for _ in range(victim_n)]
    lines += [
        "    CS2R {R8,R9}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R6,R7};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R8,R9};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
    ]
    lines += ["    " + hmma(indexed, i) for i in range(tensor_n)]
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(16)]
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def interference_main(ns: argparse.Namespace) -> int:
    print(f"victim={ns.victim}: fixed/indexed HMMA contender")
    print("place mode       min median cycles/victim")
    for place, warp in (("same", 4), ("diff", 1)):
        for indexed in (False, True):
            vals = run_clock_source(interference_source(
                indexed, warp, ns.tensor_count, ns.victim_count, ns.victim),
                "hidxinterf", 256, ns.reps)
            mode = "indexed" if indexed else "fixed"
            print(f"{place:5s} {mode:7s} {min(vals):6d} "
                  f"{statistics.median(vals):7.1f} "
                  f"{statistics.median(vals)/ns.victim_count:10.4f}")
    return 0


def selector_source(gap: int, direction: str) -> str:
    lines = [
        "#fn hidxsel(out<8>) {",
        "    #pragma MAXREG_COUNT(80)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    UMOV UR4, 0x28;[7:7:{}:5:1]",
        "    MOV32I R16, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R17, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R18, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R19, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R20, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R21, 0x3f803f80;[7:7:{}:5:1]",
    ]
    for r, val in zip(range(40, 44), (10.0, 11.0, 12.0, 13.0)):
        bits = struct.unpack("<I", struct.pack("<f", val))[0]
        lines.append(f"    MOV32I R{r}, 0x{bits:08x};[7:7:{{}}:5:1]")
    for r, val in zip(range(44, 48), (20.0, 21.0, 22.0, 23.0)):
        bits = struct.unpack("<I", struct.pack("<f", val))[0]
        lines.append(f"    MOV32I R{r}, 0x{bits:08x};[7:7:{{}}:5:1]")
    op = ("    HMMA.16816.F32.BF16 R[UR4], {R16,R17,R18,R19}, "
          "{R20,R21}, R[UR4], UPT;[7:7:{}:1:0]")
    wr = "    UMOV UR4, 0x2c;[7:7:{}:1:1]"
    if direction == "producer":
        lines += [wr] + ["    NOP;[7:7:{}:1:1]" for _ in range(gap)] + [op]
    else:
        lines += [op] + ["    NOP;[7:7:{}:1:1]" for _ in range(gap)] + [wr]
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(20)]
    lines += [
        "    STG.E.128.STRONG.GPU [{R2,R3}], {R40,R41,R42,R43};[7:1:{1}:8:0]",
        "    STG.E.128.STRONG.GPU [{R2,R3}+16], {R44,R45,R46,R47};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def selector_main(ns: argparse.Namespace) -> int:
    print("direction gap selected old-group new-group")
    for direction in ("producer", "overwrite"):
        for gap in range(ns.max_gap + 1):
            reset_context()
            mod = CudaModule(assemble(selector_source(gap, direction),
                                      check_deps=False))
            out = mod.devmem_alloc(64)
            try:
                mod.device_write(out, bytes(64))
                mod.launch("hidxsel", grid=(1,), block=(32,), args=[out])
                mod.synchronize()
                vals = struct.unpack("<8f", mod.device_read(out, 32))
            finally:
                mod.devmem_free(out)
            old_changed = vals[:4] != (10.0, 11.0, 12.0, 13.0)
            new_changed = vals[4:] != (20.0, 21.0, 22.0, 23.0)
            selected = "old" if old_changed else "new" if new_changed else "none"
            print(f"{direction:9s} {gap:3d} {selected:8s} "
                  f"{tuple(vals[:4])!s:28s} {tuple(vals[4:])}")
    return 0


def war_source(gap: int, same: bool, blocks: int) -> str:
    target = 8 if same else 24
    lines = [
        "#fn hidxwar(out<8>) {",
        "    #pragma MAXREG_COUNT(160)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        *setup(),
        "    UMOV UR24, 0x40;[7:7:{}:5:1]",
        "    CS2R {R4,R5}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    for _ in range(blocks):
        lines.append("    " + hmma(True, 0))
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
        lines.append(f"    UMOV UR{target}, 0x40;[7:7:{{}}:1:1]")
    lines += [
        "    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:5:1]" for _ in range(20)],
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R4,R5};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R6,R7};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def war_main(ns: argparse.Namespace) -> int:
    print("gap same-min same-med other-min other-med delta/block")
    for gap in range(ns.max_gap + 1):
        same = run_clock_source(war_source(gap, True, ns.blocks),
                                "hidxwar", 32, ns.reps)
        other = run_clock_source(war_source(gap, False, ns.blocks),
                                 "hidxwar", 32, ns.reps)
        delta = statistics.median(same) - statistics.median(other)
        print(f"{gap:3d} {min(same):8d} {statistics.median(same):8.1f} "
              f"{min(other):9d} {statistics.median(other):9.1f} "
              f"{delta/ns.blocks:+11.4f}")
    return 0


def uniform_consumer_source(gap: int) -> str:
    lines = [
        "#fn hidxuc(out<8>) {",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    UMOV UR4, 0x28;[7:7:{}:5:1]",
        "    UMOV UR4, 0x2c;[7:7:{}:1:1]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(gap)],
        "    IADD3 R40, PT, PT, RZ, UR4, RZ;[7:7:{}:5:1]",
        "    STG.E.STRONG.GPU [{R2,R3}], R40;[7:1:{1}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def uniform_consumer_main(ns: argparse.Namespace) -> int:
    print("gap IADD3-read")
    for gap in range(ns.max_gap + 1):
        reset_context()
        mod = CudaModule(assemble(uniform_consumer_source(gap),
                                  check_deps=False))
        out = mod.devmem_alloc(16)
        try:
            mod.device_write(out, bytes(16))
            mod.launch("hidxuc", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            val, = struct.unpack("<I", mod.device_read(out, 4))
        finally:
            mod.devmem_free(out)
        print(f"{gap:3d} {val:10d}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    pr = sub.add_parser("rate")
    pr.add_argument("--counts", default="64,128,256,512")
    pr.add_argument("--reps", type=int, default=20)
    pi = sub.add_parser("interference")
    pi.add_argument("--victim", choices=("scalar", "uniform"), default="scalar")
    pi.add_argument("--victim-count", type=int, default=4096)
    pi.add_argument("--tensor-count", type=int, default=512)
    pi.add_argument("--reps", type=int, default=20)
    ps = sub.add_parser("selector")
    ps.add_argument("--max-gap", type=int, default=16)
    pw = sub.add_parser("war")
    pw.add_argument("--max-gap", type=int, default=8)
    pw.add_argument("--blocks", type=int, default=256)
    pw.add_argument("--reps", type=int, default=20)
    pu = sub.add_parser("uniform-consumer")
    pu.add_argument("--max-gap", type=int, default=8)
    ns = p.parse_args()
    if ns.mode == "rate":
        ns.counts = [int(x) for x in ns.counts.split(",")]
        return rate_main(ns)
    if ns.mode == "interference":
        return interference_main(ns)
    if ns.mode == "war":
        return war_main(ns)
    if ns.mode == "uniform-consumer":
        return uniform_consumer_main(ns)
    return selector_main(ns)


if __name__ == "__main__":
    raise SystemExit(main())
