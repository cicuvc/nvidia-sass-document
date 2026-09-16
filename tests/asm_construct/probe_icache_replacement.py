#!/usr/bin/env python3
"""Probe the GB202 16-way ICC replacement policy with a controlled trace.

Each epoch executes:

    A0..A15, touch, X, probe

where A0..A15 and X are 4 KiB apart and map to one ICC set. A small
heap-resident dispatcher in other sets makes repeated visits possible even
though each target line has only one fixed return edge.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402


def words(source: str) -> bytes:
    return b"".join(struct.pack("<QQ", lo, hi)
                    for lo, hi in assemble_flat(source))


def launcher(total_visits: int) -> str:
    return f"""#fn icrepl(out<8>, entry<8>) {{
    #pragma MAXREG_COUNT(32)
    LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
    LDC.64 {{R26,R27}}, #param(entry);[2:7:{{}}:1:0]
    MOV32I R10, 0x{total_visits:x};[7:7:{{}}:5:1]
    MOV32I R11, 0x0;[7:7:{{}}:5:1]
    LEPC {{R12,R13}}, #label(return);[7:7:{{}}:5:1]
    CS2R {{R20,R21}}, SR_CLOCKLO;[7:7:{{2}}:5:0]
    CALL.ABS.NOINC {{R26,R27}};[7:7:{{}}:8:1]
    #def_label(return)
    CS2R {{R22,R23}}, SR_CLOCKLO;[7:7:{{}}:5:0]
""" + "    NOP;[7:7:{}:1:1]\n" * 16 + """    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]
    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]
    EXIT;[7:7:{}:5:0]
}"""


def install(mod: CudaModule, base: int, sequence: list[int]) -> int:
    dispatcher = base + 0x80
    targets = [base + i * 0x1000 for i in range(17)]
    nseq = len(sequence)

    dispatch = [
        "IADD3 R10, R10, -0x1, RZ;[7:7:{}:5:1]",
        "ISETP.NE.AND P6, PT, R10, RZ, PT;[7:7:{}:13:1]",
        "@!P6 JMX {R12,R13}, 0x0;[7:7:{}:6:0]",
    ]
    for phase, target_index in enumerate(sequence):
        dispatch.append(
            f"ISETP.EQ.AND P0, PT, R11, 0x{phase:x}, PT;"
            "[7:7:{}:13:1]")
        dispatch.append(
            f"@P0 JMP 0x{targets[target_index]:x};[7:7:{{}}:6:0]")
    encoded = words("\n".join(dispatch))
    assert len(encoded) < 0x1000 - 0x80
    mod.device_write(dispatcher, encoded)

    target_body = f"""    IADD3 R11, R11, 0x1, RZ;[7:7:{{}}:5:1]
    ISETP.EQ.AND P0, PT, R11, 0x{nseq:x}, PT;[7:7:{{}}:13:1]
    @P0 MOV32I R11, 0x0;[7:7:{{}}:5:1]
    JMP 0x{dispatcher:x};[7:7:{{}}:6:0]
"""
    body = words(target_body)
    assert len(body) <= 128
    for target in targets:
        mod.device_write(target, body)
    return dispatcher


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--touch", type=int, default=0)
    p.add_argument("--insert", type=int, default=16,
                   help="inserted target (16 overflows; 0..15 is baseline)")
    p.add_argument("--probe", type=int, required=True)
    p.add_argument("--epochs", type=int, default=2048)
    p.add_argument("--reps", type=int, default=5)
    ns = p.parse_args()
    if (not 0 <= ns.touch < 16 or not 0 <= ns.probe < 16
            or not 0 <= ns.insert <= 16):
        p.error("touch/probe must be in 0..15 and insert in 0..16")
    if ns.epochs <= 0 or ns.reps <= 0:
        p.error("epochs and reps must be positive")

    sequence = [*range(16), ns.touch, ns.insert, ns.probe]
    total_visits = ns.epochs * len(sequence)
    mod = CudaModule(assemble(launcher(total_visits), check_deps=True))
    allocation = mod.devmem_alloc(2 << 20)
    base = (allocation + 0x1fffff) & -0x200000
    if base + 0x11000 > allocation + (2 << 20):
        mod.devmem_free(allocation)
        allocation = mod.devmem_alloc(4 << 20)
        base = (allocation + 0x1fffff) & -0x200000
    out = mod.devmem_alloc(16)
    try:
        entry = install(mod, base, sequence)
        samples = []
        for rep in range(ns.reps + 1):
            mod.launch("icrepl", grid=(1,), block=(32,),
                       args=[out, entry])
            mod.synchronize()
            if rep:
                t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                samples.append((t1 - t0) & ((1 << 64) - 1))
        cycles = statistics.median(samples)
        print(f"touch={ns.touch} insert={ns.insert} probe={ns.probe} "
              f"epochs={ns.epochs} "
              f"cycles/epoch={cycles / ns.epochs:.6f}")
    finally:
        mod.devmem_free(out)
        mod.devmem_free(allocation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
