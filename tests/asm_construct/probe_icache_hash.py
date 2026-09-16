#!/usr/bin/env python3
"""Probe GB202 ICC set mapping with address-controlled heap-resident SASS.

Each hot cache line lives at

    aligned_base + i * stride_lines * 128

and contains an absolute JMP to the next line. The first line also maintains
the loop count and returns to the caller after the requested traversals.
Only the selected lines execute; the address gaps contain no assembled NOPs.
Sweeping stride and line count exposes equal-set strides and associativity.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402


LINE = 128
REGION_ALIGN = 2 << 20


def _words(source: str) -> bytes:
    encoded = assemble_flat(source)
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in encoded)


def launcher_source(iterations: int) -> str:
    return f"""#fn ichash(out<8>, code<8>) {{
    #pragma MAXREG_COUNT(32)
    LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
    LDC.64 {{R26,R27}}, #param(code);[2:7:{{}}:1:0]
    MOV32I R10, 0x{iterations:x};[7:7:{{}}:5:1]
    CS2R {{R20,R21}}, SR_CLOCKLO;[7:7:{{2}}:5:0]
    CALL.ABS.NOINC {{R26,R27}};[7:7:{{}}:8:1]
    CS2R {{R22,R23}}, SR_CLOCKLO;[7:7:{{}}:5:0]
""" + "    NOP;[7:7:{}:1:1]\n" * 16 + """    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]
    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]
    EXIT;[7:7:{}:5:0]
}"""


def install_offsets(mod: CudaModule, base: int,
                    offsets: list[int], body_nops: int = 0) -> list[int]:
    addrs = [base + offset * LINE for offset in offsets]
    count = len(addrs)
    first = _words(f"""    IADD3 R10, R10, -0x1, RZ;[7:7:{{}}:5:1]
    ISETP.NE.AND P0, PT, R10, RZ, PT;[7:7:{{}}:13:1]
    @P0 JMP 0x{addrs[1]:x};[7:7:{{}}:6:0]
    RPCMOV.32 R12, Rpc.LO;[0:7:{{}}:13:1]
    RPCMOV.32 R13, Rpc.HI;[0:7:{{}}:13:1]
    RET.ABS.NODEC {{R12,R13}}, 0x10;[7:7:{{}}:8:1]
""")
    assert len(first) <= LINE
    mod.device_write(addrs[0], first)
    for i in range(1, count):
        target = addrs[0] if i == count - 1 else addrs[i + 1]
        body = "NOP;[7:7:{}:1:1]\n" * body_nops
        body += f"JMP 0x{target:x};[7:7:{{}}:6:0]"
        encoded = _words(body)
        assert len(encoded) <= LINE
        mod.device_write(addrs[i], encoded)
    return addrs


def install_chain(mod: CudaModule, base: int, count: int,
                  stride_lines: int, body_nops: int = 0) -> list[int]:
    return install_offsets(mod, base,
                           [i * stride_lines for i in range(count)],
                           body_nops)


def parse_ints(raw: str, *, allow_zero: bool = False) -> list[int]:
    vals = [int(x, 0) for x in raw.split(",") if x.strip()]
    floor = 0 if allow_zero else 1
    if not vals or min(vals) < floor:
        kind = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"expected {kind} comma-separated integers")
    return vals


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & -alignment


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stride-lines",
                   default="1,2,4,8,16,32,64,128,256,512")
    p.add_argument("--counts", default="4,8,12,16,20")
    p.add_argument("--offset-lines",
                   help="one explicit comma-separated line-address set")
    p.add_argument("--iterations", type=int, default=1024)
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--body-nops", type=int, default=0,
                   help="executed NOPs before each non-control JMP (0..7)")
    ns = p.parse_args()
    try:
        strides = parse_ints(ns.stride_lines)
        counts = parse_ints(ns.counts)
        offsets = (parse_ints(ns.offset_lines, allow_zero=True)
                   if ns.offset_lines is not None else None)
    except ValueError as exc:
        p.error(str(exc))
    if (ns.iterations <= 1 or ns.reps <= 0 or min(counts) < 2
            or not 0 <= ns.body_nops <= 7):
        p.error("iterations must exceed one, reps positive, counts >= 2")

    if offsets is not None:
        if len(offsets) < 2 or len(set(offsets)) != len(offsets):
            p.error("offset-lines needs at least two distinct offsets")
        cases = [(0, len(offsets))]
        max_span = (max(offsets) + 1) * LINE
    else:
        cases = [(stride, count) for stride in strides for count in counts]
        max_span = max((count - 1) * stride * LINE + LINE
                       for stride, count in cases)
    slot = align_up(max_span, REGION_ALIGN)
    mod = CudaModule(assemble(launcher_source(ns.iterations),
                              check_deps=True))
    allocation = mod.devmem_alloc(slot * len(cases) + REGION_ALIGN)
    arena = align_up(allocation, REGION_ALIGN)
    out = mod.devmem_alloc(16)
    print("stride_lines stride_bytes count base_low21 cycles_per_visit")
    try:
        for case_index, (stride, count) in enumerate(cases):
            base = arena + case_index * slot
            if offsets is None:
                install_chain(mod, base, count, stride, ns.body_nops)
                entry = base
            else:
                entry = install_offsets(mod, base, offsets,
                                        ns.body_nops)[0]
            samples = []
            for rep in range(ns.reps + 1):
                mod.launch("ichash", grid=(1,), block=(32,),
                           args=[out, entry])
                mod.synchronize()
                if rep:
                    t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                    samples.append((t1 - t0) & ((1 << 64) - 1))
            # The first line executes iterations times; all others execute
            # iterations-1 times.
            visits = ns.iterations + (count - 1) * (ns.iterations - 1)
            dynamic = visits + (count - 1) * (ns.iterations - 1) * ns.body_nops
            print(f"{stride} {stride * LINE} {count} "
                  f"0x{base & (REGION_ALIGN - 1):x} "
                  f"{statistics.median(samples) / dynamic:.6f}")
    finally:
        mod.devmem_free(out)
        mod.devmem_free(allocation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
