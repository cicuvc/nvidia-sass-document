#!/usr/bin/env python3
"""Probe GB202 ICC bank/port mapping with four independent subcore streams."""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from tests.asm_construct.probe_icache_hash import install_chain  # noqa: E402


def launcher(iterations: int, actors: int) -> str:
    lines = [
        "#fn icbanks(out<8>, c0<8>, c1<8>, c2<8>, c3<8>) {",
        "    #pragma MAXREG_COUNT(32)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R12,R13}, #param(c0);[1:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(c1);[2:7:{}:1:0]",
        "    LDC.64 {R16,R17}, #param(c2);[3:7:{}:1:0]",
        "    LDC.64 {R18,R19}, #param(c3);[4:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[5:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{5}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};"
        "[7:7:{0,5}:5:1]",
        f"    MOV32I R10, 0x{iterations:x};[7:7:{{}}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    for warp, reg in enumerate((12, 14, 16, 18)[:actors]):
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
            "[7:7:{}:13:1]",
            f"    @P0 CALL.ABS.NOINC {{R{reg},R{reg + 1}}};"
            f"[7:7:{{{warp + 1}}}:8:1]",
        ]
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        *["    NOP;[7:7:{}:1:1]" for _ in range(16)],
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};"
        "[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+8], {R22,R23};"
        "[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def parse_sets(raw: str) -> list[int]:
    vals = [int(x, 0) for x in raw.split(",") if x.strip()]
    if not 1 <= len(vals) <= 4 or min(vals) < 0 or max(vals) >= 32:
        raise ValueError("sets must contain one to four indices in 0..31")
    if len(set(vals)) != len(vals):
        raise ValueError("sets must be distinct to avoid capacity overflow")
    return vals


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sets", required=True)
    p.add_argument("--lines", type=int, default=13)
    p.add_argument("--iterations", type=int, default=2048)
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--body-nops", type=int, default=0,
                   help="executed NOPs before each non-control JMP (0..7)")
    p.add_argument("--region-stride-kib", type=int, default=2048,
                   help="virtual-address spacing between actor rings")
    ns = p.parse_args()
    try:
        sets = parse_sets(ns.sets)
    except ValueError as exc:
        p.error(str(exc))
    region_stride = ns.region_stride_kib << 10
    if (not 13 <= ns.lines <= 16 or ns.iterations <= 1 or ns.reps <= 0
            or not 0 <= ns.body_nops <= 7
            or region_stride < 52 << 10 or region_stride & 127):
        p.error("lines must be 13..16, iterations > 1, reps positive; "
                "region stride must be >=52 KiB and 128-byte aligned")

    actors = len(sets)
    mod = CudaModule(assemble(launcher(ns.iterations, actors),
                              check_deps=True))
    allocation = mod.devmem_alloc(region_stride * actors + (2 << 20))
    arena = (allocation + 0x1fffff) & -0x200000
    out = mod.devmem_alloc(128 * 16)
    code = []
    try:
        for warp, set_index in enumerate(sets):
            base = arena + warp * region_stride + set_index * 128
            install_chain(mod, base, ns.lines, 32, ns.body_nops)
            code.append(base)
        per_warp = [[] for _ in range(actors)]
        spans = []
        for rep in range(ns.reps + 1):
            mod.launch("icbanks", grid=(1,), block=(actors * 32,),
                       args=[out, *(code + [code[0]] * (4 - actors))])
            mod.synchronize()
            if rep:
                raw = mod.device_read(out, 128 * 16)
                starts, ends = [], []
                for warp in range(actors):
                    t0, t1 = struct.unpack_from("<QQ", raw, warp * 32 * 16)
                    per_warp[warp].append((t1 - t0) & ((1 << 64) - 1))
                    starts.append(t0)
                    ends.append(t1)
                spans.append(max(ends) - min(starts))
        visits = ns.iterations + (ns.lines - 1) * (ns.iterations - 1)
        med = [statistics.median(x) / visits for x in per_warp]
        aggregate = actors * visits / statistics.median(spans)
        print(f"sets={','.join(map(str, sets))} lines={ns.lines} "
              f"cycles/visit={[round(x, 6) for x in med]} "
              f"aggregate_visits/cycle={aggregate:.6f}")
    finally:
        mod.devmem_free(out)
        mod.devmem_free(allocation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
