#!/usr/bin/env python3
"""HGMMA-result visibility to fixed-pipe and MIO consumers (sm_90/H100).

This is deliberately an invalid/unsafe async-proxy RAW race.  An n64
overwrite HGMMA changes accumulator R54 from 4.0f to 16.0f without a DEPBAR;
after a swept stall-1 NOP gap, a consumer samples R54.  IADD3/FADD represent
the fixed INT/FMA collectors, while SHFL/MUFU represent MIO late collection.
The consumer result is stored only after its own scoreboard and the HGMMA gsb
have completed, so stale/fresh classifies the consumer's earlier source sample.

The separate latch mode issues SHFL/MUFU first and overwrites their source
after a swept delay.  It checks whether an apparent earlier MIO boundary can
instead be explained by a fixed issue-to-late-collection delay.  Each point
runs in a fresh context to avoid queue phase carry-over.  This probe is for
microarchitecture discrimination, not an example of legal application
scheduling.

The decisive pair mode issues SHFL then IADD3 (or MUFU then FADD) in the same
dynamic instruction stream.  Seeing fresh in the earlier MIO/XU consumer and
stale in the later fixed-pipe consumer is impossible for two ordinary reads
of a monotonically updated RF and therefore identifies pre-commit forwarding.
"""

from __future__ import annotations

import argparse
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


POISON = 0x40800000       # 4.0f
FRESH = 0x41800000        # BF16 dot(ones[16], ones[16]) = 16.0f
MUFU_POISON = 0x3E800000  # rcp(4.0f) = 0.25f
MUFU_FRESH = 0x3D800000   # rcp(16.0f) = 0.0625f

CONSUMERS = {
    "int": "IADD3 R60, R54, RZ, RZ",
    "fma": "FADD R60, R54, RZ",
    "shfl": "SHFL.IDX PT, R60, R54, RZ, 0x1f",
    "mufu": "MUFU.RCP R60, R54",
}


def parse_delays(text: str) -> list[int]:
    if ":" in text:
        a, b, c = (int(x) for x in text.split(":"))
        return list(range(a, b, c))
    return [int(x) for x in text.split(",") if x]


def visibility_source(consumer: str, delay: int, pair: int = 15) -> str:
    treg = 24 + 2 * pair
    if treg != 54:
        raise ValueError("current consumer templates target pair 15 / R54")
    acc = "{" + ",".join(f"R{r}" for r in range(24, 56)) + "}"
    lines = [
        "#fn hgfwd(out<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(16384)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x4, {R2,R3};[7:7:{0,1}:5:1]",
        "    SHF.L.U32 R12, R4, 0x4, RZ;[7:7:{1}:5:1]",
        "    MOV32I R8, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R9, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R10, 0x3f803f80;[7:7:{}:5:1]",
        "    MOV32I R11, 0x3f803f80;[7:7:{}:5:1]",
        "    STS.128 [R12], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x1000], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x2000], {R8,R9,R10,R11};[7:7:{}:5:1]",
        "    STS.128 [R12+0x3000], {R8,R9,R10,R11};[7:7:{}:5:1]",
    ]
    lines += [f"    MOV32I R{r}, 0x{POISON:08x};[7:7:{{}}:5:1]"
              for r in range(24, 56)]
    lines += [
        "    UMOV UR4, 0x400040;[7:7:{}:5:1]",
        "    UMOV UR5, 0x0;[7:7:{}:5:1]",
        "    UMOV UR6, 0x4000c0;[7:7:{}:5:1]",
        "    UMOV UR7, 0x0;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        # Only warpgroup 0 runs the HGMMA/consumer.  All 256 threads were
        # retained above so the complete descriptor-covered tiles are valid.
        "    SHR R13, R4, 0x5;[7:7:{1}:5:1]",
        "    ISETP.LT.U32.AND P0, PT, R13, 0x4, PT;[7:7:{}:13:1]",
        "    @!P0 BRA #label(exit);[7:7:{}:5:1]",
        "    WARPGROUP.ARRIVE;[7:7:{}:5:1]",
        f"    HGMMA.64x64x16.F32.BF16 {acc}, gdesc[UR4], RZ, "
        "!UPT, gsb0;[7:7:{}:4:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(delay)]
    lines += [
        # No gsb wait before this instruction: its source observation is the
        # condition under test.  SB1 tracks only the consumer result.
        f"    {CONSUMERS[consumer]};[1:7:{{}}:1:1]",
        "    WARPGROUP.DEPBAR.LE gsb0, 0x0;[7:7:{}:5:1]",
        "    STG.E.STRONG.GPU [{R6,R7}], R60;[7:2:{1}:8:0]",
        "#def_label(exit)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def latch_source(consumer: str, delay: int) -> str:
    if consumer not in ("shfl", "mufu"):
        raise ValueError("latch calibration applies only to SHFL/MUFU")
    lines = [
        "#fn hglatch(out<8>) {",
        "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
        f"    MOV32I R54, 0x{POISON:08x};[7:7:{{0,1}}:5:1]",
        "    NOP;[7:7:{}:8:1]",
        "    NOP;[7:7:{}:8:1]",
        # wr=SB1 tracks the result, rd=7 intentionally omits a source-release
        # claim so the younger MOV can race the late source sample.
        f"    {CONSUMERS[consumer]};[1:7:{{}}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(delay)]
    lines += [
        f"    MOV32I R54, 0x{FRESH:08x};[7:7:{{}}:5:1]",
        "    STG.E.STRONG.GPU [{R6,R7}], R60;[7:2:{1}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def pair_source(mio: str, delay: int) -> str:
    """Issue MIO first, then a fixed-pipe read of the same accumulator."""
    src = visibility_source(mio, delay)
    first = f"    {CONSUMERS[mio]};[1:7:{{}}:1:1]"
    second = ("    IADD3 R61, R54, RZ, RZ;[2:7:{}:1:1]"
              if mio == "shfl" else
              "    FADD R61, R54, RZ;[2:7:{}:1:1]")
    src = src.replace(first, first + "\n" + second)
    src = src.replace(
        "    STG.E.STRONG.GPU [{R6,R7}], R60;[7:2:{1}:8:0]",
        "    STG.E.STRONG.GPU [{R6,R7}], R60;[7:2:{1}:8:0]\n"
        "    STG.E.STRONG.GPU [{R6,R7}+0x400], R61;[7:3:{2}:8:0]")
    return src


def expected(consumer: str) -> tuple[int, int]:
    return ((MUFU_POISON, MUFU_FRESH) if consumer == "mufu"
            else (POISON, FRESH))


def run(source: str, kernel: str, threads: int, samples: int,
        reps: int) -> collections.Counter[int]:
    reset_context()
    mod = CudaModule(assemble(source, arch="sm90", check_deps=False))
    out = mod.devmem_alloc(max(4096, threads * 4))
    counts: collections.Counter[int] = collections.Counter()
    try:
        for rep in range(reps + 1):
            mod.device_write(out, bytes(max(4096, threads * 4)))
            mod.launch(kernel, grid=(1,), block=(threads,), args=[out])
            mod.synchronize()
            if rep:
                vals = struct.unpack(
                    f"<{samples}I", mod.device_read(out, samples * 4))
                counts.update(vals)
    finally:
        mod.devmem_free(out)
    return counts


def classify(counts: collections.Counter[int], consumer: str) -> str:
    stale, fresh = expected(consumer)
    labels = {
        stale: "S",
        fresh: "F",
        0: "Z",
    }
    return "/".join(
        f"{labels.get(value, f'?{value:08x}')}:{count}"
        for value, count in counts.most_common()
    )


def run_pair(mio: str, delay: int, reps: int) -> collections.Counter[tuple[int, int]]:
    reset_context()
    mod = CudaModule(assemble(pair_source(mio, delay), arch="sm90",
                              check_deps=False))
    out = mod.devmem_alloc(4096)
    counts: collections.Counter[tuple[int, int]] = collections.Counter()
    try:
        for rep in range(reps + 1):
            mod.device_write(out, bytes(4096))
            mod.launch("hgfwd", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            if rep:
                a = struct.unpack("<128I", mod.device_read(out, 512))
                b = struct.unpack("<128I", mod.device_read(out + 0x400, 512))
                counts.update(zip(a, b))
    finally:
        mod.devmem_free(out)
    return counts


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("visibility", "latch", "pair"),
                   default="visibility")
    p.add_argument("--consumers", default="int,fma,shfl,mufu")
    p.add_argument("--delays", default="0:81:1")
    p.add_argument("--reps", type=int, default=3)
    ns = p.parse_args()
    consumers = [x for x in ns.consumers.split(",") if x]
    delays = parse_delays(ns.delays)
    if ns.mode == "pair":
        consumers = [x for x in consumers if x in ("shfl", "mufu")]
    if ns.mode == "latch" and any(x not in ("shfl", "mufu")
                                  for x in consumers):
        consumers = [x for x in consumers if x in ("shfl", "mufu")]

    print(f"mode={ns.mode}; delay is number of stall-1 NOP slots")
    print("delay " + " ".join(f"{x:>18s}" for x in consumers))
    for delay in delays:
        cells = []
        for consumer in consumers:
            if ns.mode == "pair":
                counts = run_pair(consumer, delay, ns.reps)
                m_stale, m_fresh = expected(consumer)
                parts = []
                for (m, fixed), count in counts.most_common():
                    ml = "F" if m == m_fresh else "S" if m == m_stale else "?"
                    fl = "F" if fixed == FRESH else "S" if fixed == POISON else "?"
                    parts.append(f"{ml}{fl}:{count}")
                cells.append("/".join(parts))
                continue
            if ns.mode == "visibility":
                counts = run(visibility_source(consumer, delay), "hgfwd",
                             256, 128, ns.reps)
            else:
                counts = run(latch_source(consumer, delay), "hglatch",
                             32, 1, ns.reps)
            cells.append(classify(counts, consumer))
        print(f"{delay:5d} " + " ".join(f"{x:>18s}" for x in cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
