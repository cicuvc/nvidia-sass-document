#!/usr/bin/env python3
"""Locate LDGSTS global-source and shared-destination operand sampling.

Older wide STGs create a local LSU backlog.  A target LDGSTS is then issued
without a read/source-release scoreboard, followed by an overwrite of either
its global address GPR pair or shared destination GPR.  Distinct source values
and shared slots reveal whether each operand was captured at instruction issue
or later when the queued request is dispatched/collected.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


OLD = 0x11223344
NEW = 0x55667788


def source(prefix: int, gap: int, kind: str, separation: int = 0,
           prefix_op: str = "stg") -> str:
    if kind not in ("gaddr", "saddr", "both", "both-rev"):
        raise ValueError(kind)
    lines = [
        "#fn ldgstslatch(out<8>, target<8>, flood<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(0x2000)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    LDC.64 {R14,R15}, #param(target);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(flood);[2:7:{}:1:0]",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[3:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R10,R11}, R4, 0x8, {R2,R3};[7:7:{0,4}:5:1]",
        "    IMAD.WIDE.U32 {R20,R21}, R4, 0x4, {R14,R15};[7:7:{1,4}:5:1]",
        "    IMAD.WIDE.U32 {R8,R9}, R4, 0x10, {R6,R7};[7:7:{2,4}:5:1]",
        "    SHF.L.U32 R30, R4, 0x2, RZ;[7:7:{4}:5:1]",
        "    IADD3 R30, R30, 0x1000, RZ;[7:7:{}:5:1]",
        "    SHF.L.U32 R36, R4, 0x2, RZ;[7:7:{4}:5:1]",
        # A 32-way bank-conflicted LDS address for a deliberately slow prefix.
        "    SHF.L.U32 R28, R4, 0x7, RZ;[7:7:{4}:5:1]",
        "    MOV32I R32, 0xaaaaaaaa;[7:7:{}:5:1]",
        "    MOV32I R33, 0xbbbbbbbb;[7:7:{}:5:1]",
        "    MOV32I R34, 0xcccccccc;[7:7:{}:5:1]",
        "    MOV32I R35, 0xdddddddd;[7:7:{}:5:1]",
        "    STS [R30], RZ;[7:7:{}:1:1]",
        "    STS [R30+0x400], RZ;[7:7:{}:1:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    for i in range(prefix):
        if prefix_op == "stg":
            op = (f"    STG.E.128.STRONG.GPU [{{R8,R9}}+0x{i * 4096:x}], "
                  "{R32,R33,R34,R35};[7:7:{}:1:1]")
        elif prefix_op == "stg32":
            op = (f"    STG.E.STRONG.GPU [{{R8,R9}}+0x{i * 4096:x}], "
                  "R32;[7:7:{}:1:1]")
        elif prefix_op == "ldg":
            op = (f"    LDG.E.STRONG.GPU R{40 + i}, "
                  f"[{{R8,R9}}+0x{i * 4096:x}];[7:7:{{}}:1:1]")
        elif prefix_op == "lds":
            op = f"    LDS R{40 + i}, [R28];[7:7:{{}}:1:1]"
        elif prefix_op == "shfl":
            op = (f"    SHFL.BFLY PT, R{40 + i}, RZ, 0x1, 0x1f;"
                  "[7:7:{}:1:1]")
        elif prefix_op == "ldgsts":
            op = (f"    LDGSTS.E.32 [R36+0x{0x400 + i * 0x80:x}], "
                  f"desc[{{UR4,UR5}}][{{R8,R9}}+0x{i * 4096:x}];"
                  "[7:7:{3}:1:1]")
        else:
            raise ValueError(prefix_op)
        lines.append(op)
    # Deliberately no rd scoreboard: this is the WAR being probed.
    lines.append(
        "    LDGSTS.E.32 [R30], desc[{UR4,UR5}][{R20,R21}];[7:7:{3}:1:1]"
    )
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(gap)]
    if kind == "both-rev":
        lines.append("    IADD3 R30, R30, 0x400, RZ;[7:7:{}:1:1]")
        lines += ["    NOP;[7:7:{}:1:1]" for _ in range(separation)]
        lines.append("    IADD3 R20, R20, 0x100, RZ;[7:7:{}:1:1]")
    elif kind in ("gaddr", "both"):
        lines.append("    IADD3 R20, R20, 0x100, RZ;[7:7:{}:1:1]")
        if kind == "both":
            lines += ["    NOP;[7:7:{}:1:1]" for _ in range(separation)]
    if kind in ("saddr", "both"):
        lines.append("    IADD3 R30, R30, 0x400, RZ;[7:7:{}:1:1]")
    lines += [
        "    LDGDEPBAR;[0:7:{}:1:0]",
        "    DEPBAR.LE SB0, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # R30 may now name the alternate slot, so reconstruct both addresses.
        "    SHF.L.U32 R31, R4, 0x2, RZ;[7:7:{}:5:1]",
        "    IADD3 R31, R31, 0x1000, RZ;[7:7:{}:5:1]",
        "    LDS R40, [R31];[1:7:{}:8:1]",
        "    LDS R41, [R31+0x400];[2:7:{}:8:1]",
        "    STG.E.64.STRONG.GPU [{R10,R11}], {R40,R41};[7:7:{1,2}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run(prefix: int, gap: int, kind: str, separation: int, prefix_op: str,
        reps: int) -> dict[tuple[int, int], int]:
    # Missing scoreboards are intentional: this is a WAR/queue timing probe.
    mod = CudaModule(assemble(source(prefix, gap, kind, separation, prefix_op),
                              arch="sm120", check_deps=False))
    out = mod.devmem_alloc(32 * 8)
    target = mod.devmem_alloc(0x200)
    flood = mod.devmem_alloc(max(0x1000, prefix * 4096 + 512))
    payload = bytearray(0x200)
    for lane in range(32):
        struct.pack_into("<I", payload, lane * 4, OLD)
        struct.pack_into("<I", payload, 0x100 + lane * 4, NEW)
    mod.device_write(target, bytes(payload))
    outcomes: dict[tuple[int, int], int] = {}
    try:
        # Drop first-launch clock/cache state, as in the other latch probes.
        mod.launch("ldgstslatch", grid=(1,), block=(32,),
                   args=[out, target, flood], shared_mem=0x2000)
        mod.synchronize()
        for _ in range(reps):
            mod.devmem_set(out, 0, 64)
            mod.launch("ldgstslatch", grid=(1,), block=(32,),
                       args=[out, target, flood], shared_mem=0x2000)
            mod.synchronize()
            raw = mod.device_read(out, 32 * 8)
            # All lanes should agree; retain any disagreement in the outcome.
            vals = [struct.unpack_from("<II", raw, 8 * lane)
                    for lane in range(32)]
            outcome = vals[0] if all(x == vals[0] for x in vals) else (-1, -1)
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
    finally:
        mod.devmem_free(flood)
        mod.devmem_free(target)
        mod.devmem_free(out)
    return outcomes


def fmt(outcomes: dict[tuple[int, int], int]) -> str:
    def word(x: int) -> str:
        return "DIFF" if x < 0 else f"{x:08x}"
    return " ".join(f"({word(a)},{word(b)})x{n}"
                    for (a, b), n in sorted(outcomes.items()))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind", choices=("gaddr", "saddr", "both", "both-rev"),
                   default="gaddr")
    p.add_argument("--prefixes", default="0,1,2,3,4,6,8,12,16,24,32")
    p.add_argument("--gaps", default="0,1,2,4,8,12,16,24,32")
    p.add_argument("--reps", type=int, default=9)
    p.add_argument("--separation", type=int, default=0,
                   help="NOPs inserted between the two overwrites")
    p.add_argument("--prefix-op",
                   choices=("stg", "stg32", "ldg", "lds", "shfl", "ldgsts"),
                   default="stg")
    ns = p.parse_args()
    prefixes = [int(x) for x in ns.prefixes.split(",") if x]
    gaps = [int(x) for x in ns.gaps.split(",") if x]
    print(f"kind={ns.kind} prefix_op={ns.prefix_op}; "
          "tuple=(old shared slot, alternate shared slot)")
    print("prefix gap outcomes")
    for prefix in prefixes:
        for gap in gaps:
            outcomes = run(prefix, gap, ns.kind, ns.separation,
                           ns.prefix_op, ns.reps)
            print(f"{prefix:6d} {gap:3d} {fmt(outcomes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
