#!/usr/bin/env python3
"""Test whether INT/FP/MIO UR operands share the UDP uniform-RF read port.

Warp 0 times a ULOP3 stream using either one or three 128-bit URF rows.  A
longer warp stream on the same or a different subcore executes an otherwise
matched GPR-source, UR-source, or predicated-off UR-source instruction.  The
GPR form captures dispatcher/execution contention; UR-minus-GPR isolates
uniform-register collection demand.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


FAMILIES = ("int", "fp", "f2f", "f2i", "i2f", "lds", "ldg")
PLACEMENTS = {
    "solo": (7, "none"),
    "same_gpr": (4, "gpr"),
    "same_ur": (4, "ur"),
    "same_pred": (4, "pred"),
    "diff_gpr": (1, "gpr"),
    "diff_ur": (1, "ur"),
    "diff_pred": (1, "pred"),
}


def victim_body(n: int, rows: int) -> list[str]:
    srcs = (8, 9, 10) if rows == 1 else (8, 12, 16)
    return [
        f"    ULOP3.LUT UR{40 + i % 32}, UR{srcs[0]}, UR{srcs[1]}, "
        f"UR{srcs[2]}, 0x96;[7:7:{{}}:1:1]" for i in range(n)
    ]


def contender_body(family: str, kind: str, n: int) -> list[str]:
    guard = "@P6 " if kind == "pred" else ""
    use_ur = kind in ("ur", "pred")
    lines = []
    for i in range(n):
        rd = 40 + i % 32
        if family == "int":
            src = "UR20" if use_ur else "R25"
            inst = f"IADD3 R{rd}, PT, PT, R24, {src}, RZ"
        elif family == "fp":
            src = "UR20" if use_ur else "R25"
            inst = f"FFMA R{rd}, R24, {src}, R26"
        elif family == "f2f":
            src = "UR20" if use_ur else "R24"
            inst = f"F2F.F16.F32 R{rd}, {src}"
        elif family == "f2i":
            src = "UR20" if use_ur else "R24"
            inst = f"F2I.S32.F32.TRUNC R{rd}, {src}"
        elif family == "i2f":
            src = "UR20" if use_ur else "R24"
            inst = f"I2F.F32.S32 R{rd}, {src}"
        elif family == "lds":
            addr = "RZ+UR20" if use_ur else "R24"
            inst = f"LDS R{rd}, [{addr}]"
        elif family == "ldg":
            if use_ur:
                inst = f"LDG.E R{rd}, desc[{{UR20,UR21}}][{{R18,R19}}]"
            else:
                inst = f"LDG.E.STRONG.GPU R{rd}, [{{R18,R19}}]"
        else:
            raise ValueError(family)
        # R18/R19 come from the variable-latency parameter LDC.  Keep the
        # wait on every generated LDG: the dependency checker tracks the
        # producer claim syntactically (a prior consumer does not erase it),
        # while a wait on an already-released SB is free in hardware.
        req = "{1}" if family == "ldg" else "{}"
        lines.append(f"    {guard}{inst};[7:7:{req}:1:1]")
    return lines


def source(family: str, placement: str, n: int, factor: int,
           victim_rows: int) -> str:
    contender_warp, kind = PLACEMENTS[placement]
    lines = [
        "#fn urfcross(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(4096)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R18,R19}, #param(data);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    MOV32I R24, 0x0;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R26, 0x3f000000;[7:7:{}:5:1]",
        "    UMOV UR8, 0x108;[7:7:{}:5:1]",
        "    UMOV UR9, 0x109;[7:7:{}:5:1]",
        "    UMOV UR10, 0x10a;[7:7:{}:5:1]",
        "    UMOV UR12, 0x10c;[7:7:{}:5:1]",
        "    UMOV UR16, 0x110;[7:7:{}:5:1]",
    ]
    if family == "ldg":
        lines += [
            "    LDCU.64 {UR20,UR21}, #spec_const(SLOT_DEFAULT_CDESC);"
            "[3:7:{}:1:0]",
            "    UMOV UR30, UR20;[7:7:{3}:5:1]",
        ]
    else:
        lines.append("    UMOV UR20, 0x0;[7:7:{}:5:1]")
    lines += [
        "    NOP;[7:7:{}:8:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
    ]
    if kind != "none":
        lines += [
            f"    ISETP.EQ.AND P0, PT, R5, 0x{contender_warp:x}, PT;"
            "[7:7:{}:13:1]",
            "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        ]
    lines += [
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        *victim_body(n, victim_rows),
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{0}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
    ]
    if kind != "none":
        lines += ["#def_label(contender)"]
        lines += contender_body(family, kind, n * factor)
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", choices=FAMILIES, default="int")
    p.add_argument("--placement", choices=PLACEMENTS, default="same_ur")
    p.add_argument("--victim-rows", type=int, choices=(1, 3), default=3)
    p.add_argument("--count", type=int, default=128)
    p.add_argument("--factor", type=int, default=4)
    p.add_argument("--reps", type=int, default=11)
    ns = p.parse_args()
    if min(ns.count, ns.factor, ns.reps) <= 0:
        p.error("count, factor and reps must be positive")

    text = source(ns.family, ns.placement, ns.count, ns.factor,
                  ns.victim_rows)
    mod = CudaModule(assemble(text, check_deps=True))
    out = mod.devmem_alloc(16)
    data = mod.devmem_alloc(4096)
    mod.device_write(data, bytes(4096))
    vals = []
    try:
        for rep in range(ns.reps + 1):
            mod.launch("urfcross", grid=(1,), block=(256,), args=[out, data])
            mod.synchronize()
            if rep:
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    med = statistics.median(vals)
    print(f"family={ns.family} placement={ns.placement} "
          f"victim_rows={ns.victim_rows} cycles={vals} median/op="
          f"{med/ns.count:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
