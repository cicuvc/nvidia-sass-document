#!/usr/bin/env python3
"""Poison/fresh boundaries from SHFL's MIO2RF return to MIO consumers."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


POISON = 0x40800000       # 4.0f
FRESH = 0x3F000000        # 0.5f, copied by SHFL
MUFU_STALE = 0x3E800000   # rcp(4.0)
MUFU_FRESH = 0x40000000   # rcp(0.5)
GAPS = [0] + list(range(1, 25)) + [32, 40]


def source(gap: int, consumer: str, producer: str) -> str:
    lines = [
        "#fn m2xfwd(out<8>) {",
        "    #pragma SHARED(128)",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[2:7:{}:1:0]",
        "    MOV32I R24, 0x3f000000;[7:7:{1,2}:5:1]",
    ]
    if producer == "lds":
        lines += [
            "    STS [RZ], R24;[7:7:{}:5:1]",
            "    NOP;[7:7:{}:8:1]",
            "    NOP;[7:7:{}:8:1]",
        ]
    elif producer != "shfl":
        raise ValueError(producer)
    lines += [
        f"    MOV32I R40, 0x{POISON:08x};[7:7:{{}}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
    ]
    if gap:
        # wr=7 intentionally omits the producer scoreboard claim.
        inst = ("SHFL.IDX PT, R40, R24, RZ, 0x1f"
                if producer == "shfl" else "LDS R40, [RZ]")
        lines.append(f"    {inst};[7:7:{{}}:1:1]")
        lines += ["    NOP;[7:7:{}:1:1]"] * (gap - 1)
    if consumer == "mufu":
        lines += [
            "    MUFU.RCP R20, R40;[3:7:{}:5:1]",
            "    IADD3 R21, R20, RZ, RZ;[7:7:{3}:5:1]",
            "    STG.E desc[{UR4,UR5}][{R6,R7}], R21;[0:7:{}:1:0]",
        ]
    elif consumer == "int":
        lines += [
            "    IADD3 R20, R40, RZ, RZ;[3:7:{}:5:1]",
            "    IADD3 R21, R20, RZ, RZ;[7:7:{3}:5:1]",
            "    STG.E desc[{UR4,UR5}][{R6,R7}], R21;[0:7:{}:1:0]",
        ]
    elif consumer == "lsu":
        lines.append("    STG.E desc[{UR4,UR5}][{R6,R7}], R40;[0:7:{}:1:0]")
    else:
        raise ValueError(consumer)
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run(gap: int, consumer: str, producer: str, reps: int = 3) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(source(gap, consumer, producer), check_deps=False))
    out = mod.devmem_alloc(4096)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.device_write(out, bytes(4096))
            mod.launch("m2xfwd", grid=(1,), block=(1,), args=[out])
            mod.synchronize()
            value, = struct.unpack("<I", mod.device_read(out, 4))
            if rep:
                vals.append(value)
    finally:
        mod.devmem_free(out)
    return vals


def expected(consumer: str) -> tuple[int, int]:
    return ((MUFU_STALE, MUFU_FRESH) if consumer == "mufu"
            else (POISON, FRESH))


def main() -> int:
    print("gap : " + " ".join(f"{x:2d}" for x in GAPS))
    ok = True
    for producer in ("shfl", "lds"):
        print(f"{producer.upper()}(MIO2RF)->consumer, no producer scoreboard")
        for consumer in ("mufu", "int", "lsu"):
            stale, fresh = expected(consumer)
            rows = [run(gap, consumer, producer) for gap in GAPS]
            states = []
            for vals in rows:
                chars = ["S" if x == stale else "F" if x == fresh else "?"
                         for x in vals]
                states.append(chars[0] if len(set(chars)) == 1 else "V")
            permanent = next((GAPS[i] for i in range(1, len(GAPS))
                              if all(x == "F" for x in states[i:])), None)
            print(f"{consumer:4}: " + "  ".join(states)
                  + f"  permanent={permanent}")
            ok &= (states[0] == "S" and states[-1] == "F"
                   and permanent is not None)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
