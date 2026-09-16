#!/usr/bin/env python3
"""Measure coupled scalar UDP arithmetic throughput on SM120.

All ordinary UR inputs live in UR8--UR11, one 128-bit URF row.  Destinations
live in UR40--UR71 and rotate independently, so the one-warp result measures
UDP admission/execution rather than cross-row collection or RAW latency.
Uniform-predicate-only operations use non-overlapping fixed input/output UPs.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OPS = {
    # Move/address/integer.
    "umov": "UMOV UR{d}, UR8",
    "uiabs": "UIABS UR{d}, UR8",
    "uiadd3": "UIADD3 UR{d}, UPT, UPT, UR8, UR9, UR10",
    "uiadd3_x": "UIADD3.X UR{d}, UP0, UP1, UR8, UR9, UR10, UP2, UP3",
    "uiadd3_64": ("UIADD3.64 {ud}, UPT, UPT, {{UR8,UR9}}, "
                   "{{UR8,UR9}}, {{UR8,UR9}}"),
    "uimad_lo": "UIMAD.LO UR{d}, UR8, UR9, UR10",
    "uimad_hi": "UIMAD.HI UR{d}, UR8, UR9, UR10",
    "uimad_wide": "UIMAD.WIDE {ud}, UR8, UR9, {{UR10,UR11}}",
    "ulea": "ULEA.HI UR{d}, UPT, UR8, UR9, UR10, 0x2",
    "uclea": "UCLEA {ud}, UPT, {{UR8,UR9}}, UR10, 0x5",
    "uimnmx": "UIMNMX UR{d}, UR8, UR9, UPT",
    "uviadd": "UVIADD.U8x4 UR{d}, UR8, UR9",
    "uvimnmx": "UVIMNMX.U8x4 UR{d}, UR8, UR9, UPT",
    # Logic/shift/permute.
    "ubmsk": "UBMSK UR{d}, UR8, UR9",
    "ubrev": "UBREV UR{d}, UR8",
    "uflo": "UFLO UR{d}, UPT, UR8",
    "upopc": "UPOPC UR{d}, UR8",
    "ulop3": "ULOP3.LUT UR{d}, UR8, UR9, UR10, 0x96",
    "ulop": "ULOP.XOR UR{d}, UR8, UR9",
    "ushf": "USHF.L.U32 UR{d}, UR8, UR9, UR10",
    "ushl": "USHL UR{d}, UR8, UR9",
    "ushr": "USHR.U32 UR{d}, UR8, UR9",
    "usgxt": "USGXT UR{d}, UR8, UR9",
    "uprmt": "UPRMT UR{d}, UR8, UR9, UR10",
    # Float and packed-half arithmetic.
    "ufadd": "UFADD UR{d}, UR8, UR9",
    "ufmul": "UFMUL UR{d}, UR8, UR9",
    "uffma": "UFFMA UR{d}, UR8, UR9, UR10",
    "ufhadd": "UFHADD.F16 UR{d}, UR8, UR9",
    "ufhfma": "UFHFMA.F16 UR{d}, UR8, UR9, UR10",
    "ufmnmx": "UFMNMX UR{d}, UR8, UR9, UPT",
    "ufsel": "UFSEL UR{d}, UR8, UR9, UPT",
    "ufset": "UFSET.EQ UR{d}, UR8, UR9",
    # Coupled format conversion.
    "ui2i": "UI2I.S16.S32 UR{d}, UR8",
    "ui2ip": "UI2IP.S8.S32 UR{d}, UR8, UR9, UR10",
    "ui2f": "UI2F.F32.S32 UR{d}, UR8",
    "ui2fp": "UI2FP.F32.S32 UR{d}, UR8",
    "uf2f": "UF2F.F16.F32 UR{d}, UR8",
    "uf2fp": "UF2FP.F16.F32.PACK_AB UR{d}, UR8, UR9",
    "uf2i": "UF2I.S32.F32.TRUNC UR{d}, UR8",
    "uf2ip": "UF2IP.S8.F32.TRUNC UR{d}, UR8, UR9, UR10",
    "ufrnd": "UFRND.F32.TRUNC UR{d}, UR8",
    # Uniform predicate data path.  Inputs UP2--UP4 never alias outputs.
    "uisetp": "UISETP.EQ UP0, UR8, UR9",
    "ufsetp": "UFSETP.EQ UP0, UR8, UR9",
    "uplop3": "UPLOP3.LUT UP0, UP1, UP2, UP3, UP4, 0x96, 0x69",
    "upsetp": "UPSETP.AND UP0, UP2, UP3",
    "up2ur": "UP2UR UR{d}, UPR",
}

GROUPS = {
    "integer": ("umov", "uiabs", "uiadd3", "uiadd3_x", "uiadd3_64",
                "uimad_lo", "uimad_hi", "uimad_wide", "ulea", "uclea",
                "uimnmx", "uviadd", "uvimnmx"),
    "logic": ("ubmsk", "ubrev", "uflo", "upopc", "ulop3", "ulop",
              "ushf", "ushl", "ushr", "usgxt", "uprmt"),
    "float": ("ufadd", "ufmul", "uffma", "ufhadd", "ufhfma", "ufmnmx",
              "ufsel", "ufset"),
    "convert": ("ui2i", "ui2ip", "ui2f", "ui2fp", "uf2f", "uf2fp",
                "uf2i", "uf2ip", "ufrnd"),
    "predicate": ("uisetp", "ufsetp", "uplop3", "upsetp", "up2ur"),
    "all": tuple(OPS),
}

MIXED = ("uiadd3", "uimad_hi", "ushf", "uffma", "ufhfma", "uf2ip",
         "uisetp", "uplop3")


def inst(op: str, i: int) -> str:
    pair = op in ("uiadd3_64", "uimad_wide", "uclea")
    d = 40 + ((2 * i) % 32 if pair else i % 32)
    return OPS[op].format(d=d, ud=f"{{UR{d},UR{d + 1}}}")


def source(op: str, count: int, yield_bit: int) -> str:
    seq = MIXED if op == "mixed" else (op,)
    body = [f"    {inst(seq[i % len(seq)], i)};[7:7:{{}}:1:{yield_bit}]"
            for i in range(count)]
    return "\n".join([
        "#fn udparith(out<8>) {",
        "    #pragma MAXREG_COUNT(32)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    UMOV UR8, 0x3f800000;[7:7:{}:5:1]",
        "    UMOV UR9, 0x3f000000;[7:7:{}:5:1]",
        "    UMOV UR10, 0x3e800000;[7:7:{}:5:1]",
        "    UMOV UR11, 0x0;[7:7:{}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *body,
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:0:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:0:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ])


def measure(op: str, count: int, reps: int, warmups: int,
            yield_bit: int) -> tuple[float, list[int]]:
    mod = CudaModule(assemble(source(op, count, yield_bit),
                              check_deps=True, strict_deps=True))
    out = mod.devmem_alloc(16)
    vals = []
    try:
        for rep in range(reps + warmups):
            mod.launch("udparith", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            if rep >= warmups:
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return statistics.median(vals) / count, vals


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    choices = tuple(OPS) + tuple(GROUPS)
    p.add_argument("target", nargs="?", choices=choices + ("mixed",),
                   default="all")
    p.add_argument("--count", type=int, default=256)
    p.add_argument("--reps", type=int, default=7)
    p.add_argument("--warmups", type=int, default=8,
                   help="launches discarded before timing samples")
    p.add_argument("--yield-bit", type=int, choices=(0, 1), default=0)
    ns = p.parse_args()
    if ns.count <= 0 or ns.count > 512 or ns.reps <= 0 or ns.warmups < 0:
        p.error("count must be 1..512, reps positive, and warmups nonnegative")
    selected = GROUPS.get(ns.target, (ns.target,))
    for op in selected:
        rate, vals = measure(op, ns.count, ns.reps, ns.warmups,
                             ns.yield_bit)
        print(f"{op:12} {rate:8.4f} cycles/op  "
              f"{1 / rate:8.4f} inst/clock  samples={vals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
