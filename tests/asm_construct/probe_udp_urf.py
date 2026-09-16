#!/usr/bin/env python3
"""Probe SM120 uniform-datapath throughput and uniform-RF conflicts.

The timed body uses independent, dead UR destinations and never waits for
their results.  ``umov_i`` has no UR source, ``umov_r`` has one, while
``ulop3``/``uiadd3``/``uimad``/``ushf`` expose three encoded UR sources.
Source-number and destination-parity sweeps separate UDP execution admission
from uniform-register collection and commit limits.  Actor sets compare two
warps on one subcore (0,4) with warps on distinct subcores (0,1,...).
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


ACTORS = {
    "one": (0,),
    "same2": (0, 4),
    "diff2": (0, 1),
    "diff4": (0, 1, 2, 3),
    "all8": tuple(range(8)),
}
OPS = ("umov_i", "umov_r", "umov64_i", "umov64_r", "ulop3",
       "uiadd3", "uimad", "uimad_wide", "ushf", "ufadd", "uffma",
       "ufmul", "uimnmx")
SRC_PATTERNS = ("fixed", "rotate_all", "rotate_even", "rotate_odd",
                "rotate_mod4")


def destinations(kind: str) -> tuple[int, ...]:
    if kind == "even":
        return tuple(range(40, 78, 2))
    if kind == "odd":
        return tuple(range(41, 78, 2))
    if kind == "alt":
        return tuple(range(40, 78))
    raise ValueError(kind)


def instruction(op: str, rd: int, srcs: tuple[int, int, int], i: int) -> str:
    a, b, c = srcs
    if op == "umov_i":
        return f"UMOV UR{rd}, 0x{0x12340000 + i:x}"
    if op == "umov_r":
        return f"UMOV UR{rd}, UR{a}"
    if op == "umov64_i":
        return (f"UMOV.64 {{UR{rd},UR{rd + 1}}}, "
                f"0x{0x1234000000000000 + i:x}")
    if op == "umov64_r":
        return f"UMOV.64 {{UR{rd},UR{rd + 1}}}, {{UR{a},UR{a + 1}}}"
    if op == "ulop3":
        return f"ULOP3.LUT UR{rd}, UR{a}, UR{b}, UR{c}, 0x96"
    if op == "uiadd3":
        return f"UIADD3 UR{rd}, UPT, UPT, UR{a}, UR{b}, UR{c}"
    if op == "uimad":
        return f"UIMAD.LO UR{rd}, UR{a}, UR{b}, UR{c}"
    if op == "uimad_wide":
        return (f"UIMAD.WIDE {{UR{rd},UR{rd + 1}}}, UR{a}, UR{b}, "
                f"{{UR{c},UR{c + 1}}}")
    if op == "ushf":
        return f"USHF.L.U32 UR{rd}, UR{a}, UR{b}, UR{c}"
    if op == "ufadd":
        return f"UFADD UR{rd}, UR{a}, UR{c}"
    if op == "uffma":
        return f"UFFMA UR{rd}, UR{a}, UR{b}, UR{c}"
    if op == "ufmul":
        return f"UFMUL UR{rd}, UR{a}, UR{b}"
    if op == "uimnmx":
        return f"UIMNMX UR{rd}, UR{a}, UR{b}, UPT"
    raise ValueError(op)


def source_sequence(base: tuple[int, int, int], pattern: str,
                    n: int) -> list[tuple[int, int, int]]:
    if pattern == "fixed":
        return [base] * n
    if pattern == "rotate_all":
        pool = tuple(range(8, 32))
    elif pattern == "rotate_even":
        pool = tuple(range(8, 32, 2))
    elif pattern == "rotate_odd":
        pool = tuple(range(9, 32, 2))
    else:
        pool = tuple(range(8, 32, 4))
    return [tuple(pool[(i + j) % len(pool)] for j in range(3))
            for i in range(n)]  # type: ignore[misc]


def source(op: str, n: int, actors: tuple[int, ...], srcs: tuple[int, int, int],
           src_pattern: str, dst_kind: str, yield_bit: int) -> str:
    dsts = destinations(dst_kind)
    src_seq = source_sequence(srcs, src_pattern, n)
    if op.startswith("umov64") or op == "uimad_wide":
        dsts = tuple(range(40, 78, 2))
        if op == "umov64_r" and any(a & 1 for a, _, _ in src_seq):
            raise ValueError("UMOV.64 register sources must start at an even UR")
    ops = [f"    {instruction(op, dsts[i % len(dsts)], src_seq[i], i)};"
           f"[7:7:{{}}:1:{yield_bit}]" for i in range(n)]
    lines = [
        "#fn udpprobe(out<8>) {",
        "    #pragma MAXREG_COUNT(64)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R5, 0x10, {R2,R3};[7:7:{0,1}:5:1]",
    ]
    # Seed every possible source register.  These writes are outside the
    # timed region and separated from it by BAR plus padding.
    used_srcs = {ur for triple in src_seq for ur in triple}
    if op == "umov64_r":
        used_srcs |= {a + 1 for a, _, _ in src_seq}
    if op == "uimad_wide":
        used_srcs |= {c + 1 for _, _, c in src_seq}
    for ur in sorted(used_srcs):
        lines.append(f"    UMOV UR{ur}, 0x{0x100 + ur:x};[7:7:{{}}:5:1]")
    lines += [
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if actors == tuple(range(max(actors) + 1)):
        lines.append("    BRA #label(work);[7:7:{}:5:1]")
    else:
        for warp in actors:
            lines += [
                f"    ISETP.EQ.AND P0, PT, R5, 0x{warp:x}, PT;"
                "[7:7:{}:13:1]",
                "    @P0 BRA #label(work);[7:7:{}:5:1]",
            ]
        lines.append("    BRA #label(done);[7:7:{}:5:1]")
    lines += [
        "#def_label(work)",
        "    NOP;[7:7:{}:8:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *ops,
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:0:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:0:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def parse_srcs(text: str) -> tuple[int, int, int]:
    vals = tuple(int(x, 0) for x in text.split(","))
    if len(vals) != 3 or any(x < 0 or x > 79 for x in vals):
        raise argparse.ArgumentTypeError("srcs must be three UR indices in 0..79")
    return vals  # type: ignore[return-value]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--op", choices=OPS, default="umov_i")
    p.add_argument("--actors", choices=ACTORS, default="one")
    p.add_argument("--srcs", type=parse_srcs, default=(8, 9, 10))
    p.add_argument("--src-pattern", choices=SRC_PATTERNS, default="fixed")
    p.add_argument("--dst", choices=("even", "odd", "alt"), default="alt")
    p.add_argument("--yield-bit", type=int, choices=(0, 1), default=1)
    p.add_argument("--count", type=int, default=128)
    p.add_argument("--reps", type=int, default=9)
    ns = p.parse_args()
    if ns.count <= 0 or ns.count > 512 or ns.reps <= 0:
        p.error("count must be 1..512 and reps must be positive")

    actors = ACTORS[ns.actors]
    try:
        text = source(ns.op, ns.count, actors, ns.srcs, ns.src_pattern,
                      ns.dst, ns.yield_bit)
    except ValueError as exc:
        p.error(str(exc))
    mod = CudaModule(assemble(text, check_deps=True))
    out_size = (max(actors) + 1) * 16
    out = mod.devmem_alloc(out_size)
    spans: list[list[int]] = [[] for _ in actors]
    try:
        for rep in range(ns.reps + 1):
            mod.launch("udpprobe", grid=(1,),
                       block=((max(actors) + 1) * 32,), args=[out])
            mod.synchronize()
            if rep:
                raw = mod.device_read(out, out_size)
                for j, warp in enumerate(actors):
                    t0, t1 = struct.unpack_from("<QQ", raw, warp * 16)
                    spans[j].append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    meds = [statistics.median(x) for x in spans]
    print(f"op={ns.op} actors={ns.actors} srcs={ns.srcs} "
          f"src_pattern={ns.src_pattern} dst={ns.dst} count={ns.count}")
    for warp, vals, med in zip(actors, spans, meds):
        print(f"warp {warp}: cycles={vals} median={med:g} "
              f"cycles/op={med / ns.count:.4f}")
    print(f"aggregate={len(actors) * ns.count / max(meds):.4f} inst/clock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
