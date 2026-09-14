#!/usr/bin/env python3
"""GB202 RF writeback-bank collision probe (sm_120).

The candidate collision is:

    issue t+0: HADD2 -> nominal fp16 writeback near t+5
    issue t+1: FFMA  -> nominal fmal writeback near t+5

Both are 32-bit destinations.  Their destination parities are swept through
EE/EO/OE/OO while all source registers and scheduling words remain unchanged.
If RF bank = register_number&1 and each bank has one write port, EE/OO create
an instantaneous same-bank collision while EO/OE do not.

Two experiments are complementary:

* throughput: a long alternating HADD2/FFMA stream detects completion
  backpressure.  Its average demand is only one write/cycle, so a buffered
  1W/bank design may legitimately show no sustained penalty.
* boundary: after one collision pair, sweep an FADD consumer across issue gaps
  G=2..8 and classify stale/fresh values for each producer.  A parity-dependent
  one-cycle boundary shift identifies collision arbitration even when a queue
  hides it from throughput.

This deliberately schedules consumers inside nominal RAW windows, so the
boundary kernels use check_deps=False.  They are hardware probes, not examples
of safe application scheduling.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402


PARITIES = ("EE", "EO", "OE", "OO")
GAPS = tuple(range(2, 9))
SCHED1 = "[7:7:{}:1:1]"

PHASE_OPS = {
    "iadd3": "IADD3 R{d}, R8, R11, R12",
    "ffma": "FFMA R{d}, R10, R11, R12",
    "hadd2": "HADD2 R{d}, R8, R9",
}

# Values are selected so FADD pass-through preserves the raw word.
A_POISON = 0x3A003A00       # packed half 0.5|0.5; also finite as FP32
A_FRESH = 0x3C003C00        # packed half 1.0|1.0
B_POISON = 0x3F800000       # FP32 1.0
B_FRESH = 0x40200000        # FP32 2.5 = 1*2+0.5
I_POISON = 0x3E800000
I_FRESH = 0x3F000000
OVERWRITE = 0x40C00000      # 6.0 = 2.0 * 3.0


def fadd_bits(a: int, b: int) -> int:
    af = struct.unpack("<f", struct.pack("<I", a))[0]
    bf = struct.unpack("<f", struct.pack("<I", b))[0]
    return struct.unpack("<I", struct.pack("<f", af + bf))[0]


AB_VALUES = {
    fadd_bits(A_POISON, B_POISON): "SS",
    fadd_bits(A_FRESH, B_POISON): "FS",
    fadd_bits(A_POISON, B_FRESH): "SF",
    fadd_bits(A_FRESH, B_FRESH): "FF",
}


def fit_slope(points: list[tuple[int, float]]) -> float:
    if len(points) == 1:
        return points[0][1] / points[0][0]
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    return (sum((x - xm) * (y - ym) for x, y in points)
            / sum((x - xm) ** 2 for x, _ in points))


def dest_sets(parity: str) -> tuple[list[int], list[int]]:
    pa = 0 if parity[0] == "E" else 1
    pb = 0 if parity[1] == "E" else 1
    # Disjoint sets with 20 destinations each.  Reuse distance is 40 issued
    # instructions, safely beyond both producer latencies.
    a = [40 + pa + 4 * i for i in range(20)]
    b = [42 + pb + 4 * i for i in range(20)]
    assert not set(a) & set(b)
    return a, b


def harness_head(name: str, thread_stride: int) -> list[str]:
    return [
        f"#fn {name}(out<8>) {{",
        "    #pragma MAXREG_COUNT(128)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        f"    IMAD.WIDE.U32 {{R6,R7}}, R4, 0x{thread_stride:x}, "
        "{R2,R3};[7:7:{1,2}:5:1]",
        # HADD2 reads one even and one odd source.  FFMA reads E/O/E: no
        # source layout has a known two-clock same-bank collection cost.
        f"    MOV32I R8, 0x{A_FRESH:08x};[7:7:{{}}:5:1]",
        "    MOV32I R9, 0x00000000;[7:7:{}:5:1]",
        "    MOV32I R10, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R11, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R12, 0x3f000000;[7:7:{}:5:1]",
    ]


def throughput_source(parity: str, pairs: int) -> str:
    ad, bd = dest_sets(parity)
    lines = harness_head("rfwb_thr", 16)
    for r in sorted(set(ad + bd)):
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:5:0]",
    ]
    for i in range(pairs):
        lines.append(f"    HADD2 R{ad[i % len(ad)]}, R8, R9;{SCHED1}")
        lines.append(f"    FFMA R{bd[i % len(bd)]}, R10, R11, R12;{SCHED1}")
    lines += [
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    # Every lane writes a private 16-byte record.  Only lane 0 is read.
    lines += [
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_throughput(lengths: list[int], reps: int) -> dict[str, float]:
    slopes = {}
    print("\n== sustained alternating HADD2/FFMA ==")
    for parity in PARITIES:
        points = []
        vals = []
        for n in lengths:
            mod = CudaModule(assemble(throughput_source(parity, n),
                                      check_deps=True))
            out = mod.devmem_alloc(4096)
            try:
                samples = []
                for _ in range(reps + 1):       # first launch is warm-up
                    mod.launch("rfwb_thr", grid=(1,), block=(32,), args=[out])
                    mod.synchronize()
                    t0 = struct.unpack("<Q", mod.device_read(out, 8))[0]
                    t1 = struct.unpack("<Q", mod.device_read(out + 0x8, 8))[0]
                    samples.append((t1 - t0) & ((1 << 64) - 1))
                best = float(min(samples[1:]))
                points.append((n, best))
                vals.append(f"N={n}:{best/(2*n):.4f}")
            finally:
                mod.devmem_free(out)
        # slope is cycles/pair; report cycles/issued producer instruction.
        slopes[parity] = fit_slope(points) / 2.0
        print(f"  {parity}: " + "  ".join(vals)
              + f"  fitted={slopes[parity]:.4f} cyc/inst")
    same = statistics.mean(slopes[p] for p in ("EE", "OO"))
    cross = statistics.mean(slopes[p] for p in ("EO", "OE"))
    print(f"  same-bank mean={same:.4f}; opposite-bank mean={cross:.4f}; "
          f"delta={same-cross:+.4f} cyc/inst")
    return slopes


def phase_source(a_name: str, b_name: str, parity: str,
                 gap: int, pairs: int) -> str:
    """Tight A/B stream with B issued exactly ``gap`` slots after A."""
    ad, bd = dest_sets(parity)
    lines = harness_head("rfwb_phase", 16)
    for r in sorted(set(ad + bd)):
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    lines += [
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    NOP;[7:7:{}:5:0]",
    ]
    for i in range(pairs):
        ai = PHASE_OPS[a_name].format(d=ad[i % len(ad)])
        bi = PHASE_OPS[b_name].format(d=bd[i % len(bd)])
        lines.append(f"    {ai};[7:7:{{}}:{gap}:1]")
        lines.append(f"    {bi};{SCHED1}")
    lines += ["    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]"]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_phase(a_name: str, b_name: str, gaps: list[int],
              lengths: list[int], reps: int) -> dict[int, dict[str, float]]:
    print(f"\n== destination-bank phase scan: {a_name} -> {b_name} ==")
    result = {}
    for gap in gaps:
        slopes = {}
        for parity in PARITIES:
            points = []
            for n in lengths:
                src = phase_source(a_name, b_name, parity, gap, n)
                mod = CudaModule(assemble(src, check_deps=True))
                out = mod.devmem_alloc(4096)
                try:
                    samples = []
                    for _ in range(reps + 1):
                        mod.launch("rfwb_phase", grid=(1,), block=(32,),
                                   args=[out])
                        mod.synchronize()
                        t0, t1 = struct.unpack(
                            "<QQ", mod.device_read(out, 16))
                        samples.append((t1 - t0) & ((1 << 64) - 1))
                    points.append((n, float(min(samples[1:]))))
                finally:
                    mod.devmem_free(out)
            slopes[parity] = fit_slope(points) / 2.0
        same = statistics.mean(slopes[p] for p in ("EE", "OO"))
        cross = statistics.mean(slopes[p] for p in ("EO", "OE"))
        result[gap] = slopes
        print(f"  gap={gap}: " + " ".join(
            f"{p}={slopes[p]:.4f}" for p in PARITIES)
            + f"  same-cross={same-cross:+.4f}")
    return result


def boundary_source(parity: str, producer_gap: int
                    ) -> tuple[str, list[tuple[str, int, int]]]:
    pa = 0 if parity[0] == "E" else 1
    pb = 0 if parity[1] == "E" else 1
    da, db = 40 + pa, 42 + pb
    lines = harness_head("rfwb_edge", 4)
    cases: list[tuple[str, int, int]] = []
    outreg = 80
    gaps = tuple(g for g in GAPS if g > producer_gap)
    for target, reg in (("A", da), ("B", db), ("AB", -1)):
        for gap in gaps:
            lines += [
                f"    MOV32I R{da}, 0x{A_POISON:08x};[7:7:{{}}:5:1]",
                f"    MOV32I R{db}, 0x{B_POISON:08x};[7:7:{{}}:5:1]",
            ]
            lines += ["    NOP;[7:7:{}:1:1]" for _ in range(8)]
            # HADD2 issues at t=0, FFMA at t=producer_gap, consumer at
            # t=gap.  Nominal writebacks coincide only at producer_gap=1.
            lines += [
                f"    HADD2 R{da}, R8, R9;"
                f"[7:7:{{}}:{producer_gap}:1]",
                f"    FFMA R{db}, R10, R11, R12;"
                f"[7:7:{{}}:{gap - producer_gap}:1]",
            ]
            if target == "AB":
                lines.append(
                    f"    FADD R{outreg}, R{da}, R{db};[7:7:{{}}:5:1]")
            else:
                lines.append(
                    f"    FADD R{outreg}, R{reg}, RZ;[7:7:{{}}:5:1]")
            cases.append((target, gap, outreg))
            outreg += 1
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(24)]
    for idx, (_, _, reg) in enumerate(cases):
        lines.append(
            f"    STG.E.STRONG.GPU [{{R6,R7}}+0x{idx * 0x80:x}], R{reg};"
            "[7:1:{}:8:0]")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines), cases


def classify(value: int, target: str) -> str:
    if target == "AB":
        return AB_VALUES.get(value, f"?{value:08x}")
    poison, fresh = ((A_POISON, A_FRESH) if target == "A"
                     else (B_POISON, B_FRESH))
    if value == poison:
        return "S"
    if value == fresh:
        return "F"
    return f"?{value:08x}"


def run_boundary(reps: int, producer_gaps: list[int]
                 ) -> dict[tuple[int, str, str], str]:
    patterns = {}
    print("\n== stale/fresh boundary after nominal writeback collision ==")
    for producer_gap in producer_gaps:
        gaps = tuple(g for g in GAPS if g > producer_gap)
        print(f"  producer_gap={producer_gap}; consumer gaps: "
              + " ".join(str(x) for x in gaps))
        for parity in PARITIES:
            source, cases = boundary_source(parity, producer_gap)
            mod = CudaModule(assemble(source, check_deps=False))
            out = mod.devmem_alloc(4096)
            try:
                runs = []
                for _ in range(reps):
                    mod.devmem_set(out, 0, 1024)
                    mod.launch("rfwb_edge", grid=(1,), block=(32,), args=[out])
                    mod.synchronize()
                    raw = mod.device_read(out, 4096)
                    runs.append([
                        struct.unpack_from("<I", raw, i * 0x80)[0]
                        for i in range(len(cases))
                    ])
            finally:
                mod.devmem_free(out)
            for target in ("A", "B", "AB"):
                chars = []
                for i, (t, _, _) in enumerate(cases):
                    if t != target:
                        continue
                    labels = [classify(r[i], target) for r in runs]
                    chars.append(labels[0]
                                 if all(x == labels[0] for x in labels)
                                 else "V")
                pattern = " ".join(chars)
                patterns[(producer_gap, parity, target)] = pattern
                print(f"    {parity} target={target}: {pattern}")
    print("  legend: S=stale, F=fresh, V=varies, ?xxxxxxxx=unexpected bits")
    return patterns


def triple_source(parity: str) -> tuple[str, list[tuple[str, int, int]]]:
    """IADD3/HADD2/FFMA at t=0/1/2, nominally all writing near t=6."""
    assert len(parity) == 3 and set(parity) <= {"E", "O"}
    regs = [40 + (parity[0] == "O"),
            42 + (parity[1] == "O"),
            44 + (parity[2] == "O")]
    lines = harness_head("rfwb_triple", 4)
    lines.append(f"    MOV32I R16, 0x{I_FRESH:08x};[7:7:{{}}:5:1]")
    cases = []
    outreg = 80
    gaps = tuple(range(3, 11))
    for target, reg in zip("IHF", regs):
        for gap in gaps:
            lines += [
                f"    MOV32I R{regs[0]}, 0x{I_POISON:08x};[7:7:{{}}:5:1]",
                f"    MOV32I R{regs[1]}, 0x{A_POISON:08x};[7:7:{{}}:5:1]",
                f"    MOV32I R{regs[2]}, 0x{B_POISON:08x};[7:7:{{}}:5:1]",
            ]
            lines += ["    NOP;[7:7:{}:1:1]" for _ in range(8)]
            lines += [
                f"    IADD3 R{regs[0]}, R16, RZ, RZ;[7:7:{{}}:1:1]",
                f"    HADD2 R{regs[1]}, R8, R9;[7:7:{{}}:1:1]",
                f"    FFMA R{regs[2]}, R10, R11, R12;"
                f"[7:7:{{}}:{gap - 2}:1]",
                f"    FADD R{outreg}, R{reg}, RZ;[7:7:{{}}:5:1]",
            ]
            cases.append((target, gap, outreg))
            outreg += 1
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(24)]
    for idx, (_, _, reg) in enumerate(cases):
        lines.append(
            f"    STG.E.STRONG.GPU [{{R6,R7}}+0x{idx * 0x80:x}], R{reg};"
            "[7:1:{}:8:0]")
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines), cases


def classify_triple(value: int, target: str) -> str:
    table = {
        "I": (I_POISON, I_FRESH),
        "H": (A_POISON, A_FRESH),
        "F": (B_POISON, B_FRESH),
    }
    poison, fresh = table[target]
    return "S" if value == poison else (
        "F" if value == fresh else f"?{value:08x}")


def run_triple(reps: int) -> dict[tuple[str, str], str]:
    print("\n== triple completion: IADD3(t0)+HADD2(t1)+FFMA(t2) ==")
    print("  nominal writeback alignment near t=6; consumer gaps 3..10")
    patterns = {}
    for parity in ("EEE", "EEO", "EOE", "EOO",
                   "OEE", "OEO", "OOE", "OOO"):
        source, cases = triple_source(parity)
        mod = CudaModule(assemble(source, check_deps=False))
        out = mod.devmem_alloc(4096)
        try:
            runs = []
            for _ in range(reps):
                mod.devmem_set(out, 0, 1024)
                mod.launch("rfwb_triple", grid=(1,), block=(32,), args=[out])
                mod.synchronize()
                raw = mod.device_read(out, 4096)
                runs.append([struct.unpack_from("<I", raw, i * 0x80)[0]
                             for i in range(len(cases))])
        finally:
            mod.devmem_free(out)
        fields = []
        for target in "IHF":
            chars = []
            for i, (t, _, _) in enumerate(cases):
                if t != target:
                    continue
                labels = [classify_triple(r[i], target) for r in runs]
                chars.append(labels[0]
                             if all(x == labels[0] for x in labels) else "V")
            pattern = "".join(chars)
            patterns[(parity, target)] = pattern
            fields.append(f"{target}:{pattern}")
        print(f"  {parity} " + "  ".join(fields))
    print("  legend: each string covers gaps 3..10; S=stale F=fresh V=variable")
    return patterns


def overwrite_source(parity: str) -> tuple[str, list[tuple[str, int]]]:
    """Unsafe WAW race: overwrite one triple-collision result with FFMA."""
    regs = [40 + (parity[0] == "O"),
            42 + (parity[1] == "O"),
            44 + (parity[2] == "O")]
    lines = harness_head("rfwb_waw", 4)
    lines += [
        f"    MOV32I R16, 0x{I_FRESH:08x};[7:7:{{}}:5:1]",
        "    MOV32I R18, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R19, 0x40400000;[7:7:{}:5:1]",
    ]
    cases = []
    idx = 0
    for target, reg in zip("IHF", regs):
        for gap in range(3, 8):
            lines += [
                f"    MOV32I R{regs[0]}, 0x{I_POISON:08x};[7:7:{{}}:5:1]",
                f"    MOV32I R{regs[1]}, 0x{A_POISON:08x};[7:7:{{}}:5:1]",
                f"    MOV32I R{regs[2]}, 0x{B_POISON:08x};[7:7:{{}}:5:1]",
            ]
            lines += ["    NOP;[7:7:{}:1:1]" for _ in range(8)]
            lines += [
                f"    IADD3 R{regs[0]}, R16, RZ, RZ;[7:7:{{}}:1:1]",
                f"    HADD2 R{regs[1]}, R8, R9;[7:7:{{}}:1:1]",
                f"    FFMA R{regs[2]}, R10, R11, R12;"
                f"[7:7:{{}}:{gap - 2}:1]",
                f"    FFMA R{reg}, R18, R19, RZ;[7:7:{{}}:5:1]",
            ]
            lines += ["    NOP;[7:7:{}:1:1]" for _ in range(24)]
            lines.append(
                f"    STG.E.STRONG.GPU [{{R6,R7}}+0x{idx * 0x80:x}], R{reg};"
                "[7:1:{}:8:0]")
            lines += ["    NOP;[7:7:{}:1:1]" for _ in range(8)]
            cases.append((target, gap))
            idx += 1
    lines += ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines), cases


def run_overwrite(reps: int) -> dict[tuple[str, str], str]:
    print("\n== unsafe WAW overwrite after triple completion ==")
    print("  FFMA overwrite issue gaps 3..7; O=overwrite wins")
    patterns = {}
    for parity in ("EEE", "EEO", "EOE", "EOO",
                   "OEE", "OEO", "OOE", "OOO"):
        source, cases = overwrite_source(parity)
        mod = CudaModule(assemble(source, check_deps=False))
        out = mod.devmem_alloc(4096)
        try:
            runs = []
            for _ in range(reps):
                mod.devmem_set(out, 0, 1024)
                mod.launch("rfwb_waw", grid=(1,), block=(32,), args=[out])
                mod.synchronize()
                raw = mod.device_read(out, 4096)
                runs.append([struct.unpack_from("<I", raw, i * 0x80)[0]
                             for i in range(len(cases))])
        finally:
            mod.devmem_free(out)
        fields = []
        originals = {"I": I_FRESH, "H": A_FRESH, "F": B_FRESH}
        for target in "IHF":
            chars = []
            for i, (t, _) in enumerate(cases):
                if t != target:
                    continue
                labels = []
                for run in runs:
                    v = run[i]
                    labels.append("O" if v == OVERWRITE else (
                        "P" if v == originals[target] else f"?{v:08x}"))
                chars.append(labels[0]
                             if all(x == labels[0] for x in labels) else "V")
            pattern = "".join(chars)
            patterns[(parity, target)] = pattern
            fields.append(f"{target}:{pattern}")
        print(f"  {parity} " + "  ".join(fields))
    print("  P=older producer wins (overtook WAW), V=variable")
    return patterns


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("both", "throughput", "boundary",
                                      "phase", "triple", "overwrite"),
                   default="both")
    p.add_argument("--lengths", default="128,256,512",
                   help="pair counts for throughput slope")
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--phase-pair", default="iadd3,ffma",
                   help="A,B for phase mode; choices: iadd3,ffma,hadd2")
    p.add_argument("--phase-gaps", default="1,2,3,4,5,6,7")
    p.add_argument("--producer-gaps", default="1",
                   help="HADD2->FFMA issue gaps for boundary mode")
    ns = p.parse_args()
    try:
        lengths = [int(x) for x in ns.lengths.split(",") if x.strip()]
    except ValueError as exc:
        p.error(str(exc))
    if not lengths or min(lengths) <= 0 or ns.reps <= 0:
        p.error("lengths and reps must be positive")
    try:
        a_name, b_name = (x.strip().lower()
                          for x in ns.phase_pair.split(",", 1))
        phase_gaps = [int(x) for x in ns.phase_gaps.split(",") if x.strip()]
        producer_gaps = [int(x) for x in ns.producer_gaps.split(",")
                         if x.strip()]
    except ValueError as exc:
        p.error(str(exc))
    if a_name not in PHASE_OPS or b_name not in PHASE_OPS:
        p.error("bad --phase-pair")
    if not phase_gaps or min(phase_gaps) < 1 or max(phase_gaps) > 7:
        p.error("--phase-gaps must be in 1..7")
    if (not producer_gaps or min(producer_gaps) < 1
            or max(producer_gaps) > 7):
        p.error("--producer-gaps must be in 1..7")

    print("GB202 RF writeback collision: HADD2(t+0,w~5) + FFMA(t+1,w~4)")
    print("destination parity is the only changed instruction operand")
    if ns.mode in ("both", "throughput"):
        run_throughput(lengths, ns.reps)
    if ns.mode in ("both", "boundary"):
        run_boundary(ns.reps, producer_gaps)
    if ns.mode == "phase":
        run_phase(a_name, b_name, phase_gaps, lengths, ns.reps)
    if ns.mode == "triple":
        run_triple(ns.reps)
    if ns.mode == "overwrite":
        run_overwrite(ns.reps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
