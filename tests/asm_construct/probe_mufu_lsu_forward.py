#!/usr/bin/env python3
"""Probe whether an MUFU result is visible early to the LSU late collector.

The producer deliberately claims no scoreboard.  R10 starts as 4.0f and
MUFU.RCP changes it to 0.5f.  A following STG uses R10 as store data, whose
GPR identity is retained in the LSU queue until late operand collection.
Each gap is run in an independent kernel/module to avoid XU/LSU queue phase
carry-over between adjacent cases.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


POISON = 0x40800000       # 4.0f
PRODUCER_IN = 0x40000000  # 2.0f
FRESH = 0x3F000000        # rcp(2.0f) = 0.5f
YOUNGER = 0x40400000      # 3.0f, written after STG in the latch control
GAPS = [0] + list(range(1, 17)) + [24, 32]


def source(gap: int, overwrite: bool = False) -> str:
    lines = [
        "#fn mufu_lsu(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[2:7:{}:1:0]",
        f"    MOV32I R1, 0x{PRODUCER_IN:08x};[7:7:{{1,2}}:5:1]",
        f"    MOV32I R10, 0x{POISON:08x};[7:7:{{}}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
    ]
    if gap:
        lines.append("    MUFU.RCP R10, R1;[7:7:{}:1:1]")
        lines += ["    NOP;[7:7:{}:1:1]"] * (gap - 1)
    # The output-address barrier was already consumed before the producer;
    # keep this instruction's req set empty so it cannot perturb the boundary.
    # In particular, there is no producer scoreboard to wait on.  STG's data
    # source is sampled by LSU's late GPR collector.
    # rd=7 deliberately omits a source-release barrier, matching the existing
    # STG late-latch probe.  This lets the post-STG MOV race the late sample.
    lines.append("    STG.E desc[{UR4,UR5}][{R6,R7}], R10;[7:7:{}:1:1]")
    if overwrite:
        lines.append(f"    MOV32I R10, 0x{YOUNGER:08x};[7:7:{{}}:5:1]")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run(gap: int, overwrite: bool = False, reps: int = 3) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(source(gap, overwrite), check_deps=False))
    out = mod.devmem_alloc(4096)
    values = []
    try:
        # Warm the module once, then take repeated samples.
        for _ in range(reps + 1):
            mod.device_write(out, struct.pack("<I", 0xDEADBEEF))
            mod.launch("mufu_lsu", grid=(1,), block=(1,), args=[out])
            mod.synchronize()
            values.append(struct.unpack("<I", mod.device_read(out, 4))[0])
    finally:
        mod.devmem_free(out)
    return values[1:]


def classify(value: int) -> str:
    if value == POISON:
        return "S"
    if value == FRESH:
        return "F"
    if value == YOUNGER:
        return "Y"
    return "?"


def main() -> int:
    rows_by_mode = {}
    try:
        for overwrite in (False, True):
            rows_by_mode[overwrite] = [run(gap, overwrite) for gap in GAPS]
    except RuntimeError as exc:
        print(f"skip GPU checks (no CUDA driver/GPU): {exc}")
        return 0

    print("MUFU.RCP -> STG data, no producer scoreboard wait")
    print("gap : " + " ".join(f"{x:2d}" for x in GAPS))
    ok = True
    for overwrite, rows in rows_by_mode.items():
        states = []
        deterministic = True
        for values in rows:
            cs = [classify(v) for v in values]
            deterministic &= len(set(values)) == 1
            states.append(cs[0] if len(set(cs)) == 1 else "V")
        permanent = next((GAPS[i] for i in range(1, len(GAPS))
                          if all(x == "F" for x in states[i:])), None)
        tag = "post-MOV" if overwrite else "plain"
        print(f"{tag:8}: " + "  ".join(states))
        print(f"  deterministic={deterministic}; permanently fresh={permanent}")
        unknown = [(gap, [hex(v) for v in vals])
                   for gap, vals, state in zip(GAPS, rows, states)
                   if state not in ("S", "F", "Y")]
        if unknown:
            print("  unknown/variable:", unknown)
        ok &= deterministic
        if not overwrite:
            ok &= states[0] == "S" and states[-1] == "F" and permanent is not None
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
