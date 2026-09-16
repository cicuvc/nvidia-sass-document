#!/usr/bin/env python3
"""Locate GB202 tensor operand collection and completion relative to scalar RF.

``collect`` times a two-even-source FADD/RZ stream in warp 0 while warp 4
(same subcore) or warp 1 (different subcore) runs HMMA.  The HMMA body is
identical except that all ten input GPRs are replaced by RZ in the control.
Both versions execute and write four-register results, so their timing
difference isolates tensor GPR operand collection from tensor admission,
backend occupancy, and result traffic.

``commit`` issues one HMMA with a known four-register result, overlaps its
completion with an even-only or odd-only reuse-fed FFMA write stream, and
samples an even or odd HMMA result after a swept padding.  This is deliberately
an unsafe visibility probe: tensor results have no general scoreboard, so the
stale/fresh boundary rather than architectural correctness is the signal.

``retire`` is the architectural-write test: a warmed scoreboarded LDG is
followed by a phase-shifted HMMA whose destination is either four GPRs or RZ.
The sources and tensor execution are identical, so a GPR-minus-RZ increase in
the LDG scoreboard-release time isolates tensor result-retirement pressure.

``throughput`` fits the naked RZ-source tensor admission slope.  ``mixedwb``
alternates one tensor instruction with sixteen even-bank FADD writes and
compares tensor GPR versus RZ destinations under sustained commit pressure.
``ramix`` compares a fixed A or B operand against rotating addresses while
sweeping scalar RF pressure between successive HMMAs; for B it can also set
the explicit SM120 reuse bit.
"""

from __future__ import annotations

import argparse
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.runner import reset_context  # noqa: E402


def mma_stream(op: str, n: int, source_mode: str, reuse: int = 0) -> list[str]:
    wide = op in ("hmma", "qmma")
    a = (("{R16,R17,R18,R19}" if "a" in source_mode
          else "{RZ,RZ,RZ,RZ}") if wide else
         ("{R16,R17}.ROW" if "a" in source_mode else "{RZ,RZ}.ROW"))
    b = (("{R20,R21}" if "b" in source_mode else "{RZ,RZ}") if wide
         else ("R20.COL" if "b" in source_mode else "RZ.COL"))
    lines = []
    for i in range(n):
        if source_mode in ("amp_fixed", "amp_rotate", "bw_fixed", "bw_rotate"):
            if op != "hmma":
                raise ValueError("fixed tensor operand patterns are HMMA-only")
            # Ampere-style: hold A and rotate B.  Blackwell-style control:
            # rotate A and hold B, the only dense-SM120 reusable operand.
            ar = (16 if source_mode == "amp_fixed"
                  else 32 + 4 * (i % 16))
            br = (96 if source_mode == "bw_fixed"
                  else 96 + 2 * (i % 16))
            rd = 128 + 4 * (i % 16)
            a = f"{{R{ar},R{ar+1},R{ar+2},R{ar+3}}}"
            b = f"{{R{br},R{br+1}}}"
            c = f"{{R{rd},R{rd+1},R{rd+2},R{rd+3}}}"
        elif source_mode in ("c_sep", "c_rmw"):
            # Equal rotating address distributions and reuse distances.  Only
            # c_rmw aliases Rc to Rd; c_sep keeps the same C group at +96.
            rd = 32 + 4 * (i % 20)
            cr = rd if source_mode == "c_rmw" else rd + 96
            c = f"{{R{cr},R{cr+1},R{cr+2},R{cr+3}}}"
        else:
            rd = 32 + 4 * (i % 47)
            c = ("{R24,R25,R26,R27}" if "c" in source_mode
                 else "{RZ,RZ,RZ,RZ}")
        src = f"{a}, {b}, {c}"
        if op == "hmma":
            mnem = "HMMA.16816.F32.BF16"
            tail = ""
        elif op == "qmma":
            mnem = "QMMA.16832.F32.E4M3.E4M3"
            tail = ""
        elif op == "imma":
            mnem = "IMMA.16816.U8.U8"
            tail = ", !UPT"
        else:
            raise ValueError(op)
        lines.append(f"    {mnem} {{R{rd},R{rd+1},R{rd+2},R{rd+3}}}, "
                     f"{src}{tail};[7:7:{{}}:1:0:{reuse}]")
    return lines


def collect_source(op: str, victim_n: int, tensor_n: int, contender_warp: int,
                   source_mode: str, reuse: int) -> str:
    lines = [
        "#fn trfcollect(out<8>) {",
        "    #pragma MAXREG_COUNT(224)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[2:7:{}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{2}:5:1]",
        "    MOV32I R80, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R82, 0x40000000;[7:7:{}:5:1]",
    ]
    for r in list(range(16, 22)) + list(range(24, 28)):
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    if source_mode in ("amp_fixed", "amp_rotate", "bw_fixed", "bw_rotate"):
        # Keep arithmetic values and setup instruction counts equal.  These
        # writes precede the CTA barrier and timed region.
        for r in range(32, 192):
            lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    lines += [
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        f"    ISETP.EQ.AND P0, PT, R5, 0x{contender_warp:x}, PT;"
        "[7:7:{}:13:1]",
        "    @P0 BRA #label(contender);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
        "    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    FADD RZ, R80, R82;[7:7:{}:1:1]"
              for _ in range(victim_n)]
    lines += [
        "    CS2R {R8,R9}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R6,R7};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R8,R9};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender)",
    ]
    lines += mma_stream(op, tensor_n, source_mode, reuse)
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(16)]
    lines += ["#def_label(done)", "    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(lines)


def run_collect(op: str, victim_n: int, tensor_n: int, contender_warp: int,
                source_mode: str, reuse: int, reps: int) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(collect_source(
        op, victim_n, tensor_n, contender_warp, source_mode, reuse),
        check_deps=True))
    out = mod.devmem_alloc(32)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("trfcollect", grid=(1,), block=(256,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return vals


def collect_main(ns: argparse.Namespace) -> int:
    print(f"{ns.op.upper()} GPR collection vs scalar two-even-row FADD/RZ victim "
          f"(reuse={ns.reuse})")
    print("place source  min median  cycles/victim-inst")
    rows = {}
    for place, warp in (("same", 4), ("diff", 1)):
        for src in ns.sources:
            vals = run_collect(ns.op, ns.victim_count, ns.tensor_count, warp,
                               src, ns.reuse, ns.reps)
            rows[place, src] = statistics.median(vals)
            print(f"{place:5s} {src:6s} {min(vals):5d} "
                  f"{statistics.median(vals):6.1f} "
                  f"{statistics.median(vals)/ns.victim_count:9.4f}")
    if "abc" in ns.sources and "rz" in ns.sources:
        effect = ((rows["same", "abc"] - rows["same", "rz"])
                  - (rows["diff", "abc"] - rows["diff", "rz"]))
        print(f"ABC-vs-RZ difference-in-differences = {effect:+.1f} clocks "
              f"({effect/ns.tensor_count:+.3f} per {ns.op.upper()})")
    return 0


def commit_source(storm_n: int, storm_parity: str, sample_parity: str,
                  pad: int) -> str:
    sp = 0 if storm_parity == "E" else 1
    sample = 40 if sample_parity == "E" else 41
    dsts = [100 + sp + 2 * i for i in range(40)]
    lines = [
        "#fn trfcommit(out<8>) {",
        "    #pragma MAXREG_COUNT(224)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    MOV32I R16, 0;[7:7:{}:5:1]",
        "    MOV32I R17, 0;[7:7:{}:5:1]",
        "    MOV32I R18, 0;[7:7:{}:5:1]",
        "    MOV32I R19, 0;[7:7:{}:5:1]",
        "    MOV32I R20, 0;[7:7:{}:5:1]",
        "    MOV32I R21, 0;[7:7:{}:5:1]",
        "    MOV32I R24, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R25, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R26, 0x40400000;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40800000;[7:7:{}:5:1]",
        "    MOV32I R40, 0x7f000040;[7:7:{}:5:1]",
        "    MOV32I R41, 0x7f000041;[7:7:{}:5:1]",
        "    MOV32I R42, 0x7f000042;[7:7:{}:5:1]",
        "    MOV32I R43, 0x7f000043;[7:7:{}:5:1]",
        "    MOV32I R90, 0x3f800000;[7:7:{}:5:1]",
        "    MOV32I R93, 0x40000000;[7:7:{}:5:1]",
        "    MOV32I R94, 0x3f000000;[7:7:{}:5:1]",
    ]
    for r in dsts:
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    lines += ["    NOP;[7:7:{}:5:1]" for _ in range(4)]
    lines += [
        "    HMMA.16816.F32.BF16 {R40,R41,R42,R43}, "
        "{R16,R17,R18,R19}, {R20,R21}, {R24,R25,R26,R27};"
        "[7:7:{}:1:0]",
    ]
    for i in range(storm_n):
        lines.append(
            f"    FFMA R{dsts[i % len(dsts)]}, R90, R93, R94;"
            "[7:7:{}:1:0:7]")
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(pad)]
    lines += [
        f"    IADD3 R60, R{sample}, RZ, RZ;[7:7:{{}}:5:1]",
        "    NOP;[7:7:{}:5:1]",
        "    STG.E.STRONG.GPU [{R2,R3}], R60;[7:1:{1}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_commit(storm_n: int, sp: str, rp: str, pad: int, reps: int) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(
        commit_source(storm_n, sp, rp, pad), check_deps=False))
    out = mod.devmem_alloc(32)
    vals = []
    try:
        for _ in range(reps):
            mod.launch("trfcommit", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            vals.append(struct.unpack("<I", mod.device_read(out, 4))[0])
    finally:
        mod.devmem_free(out)
    return vals


def commit_main(ns: argparse.Namespace) -> int:
    print("HMMA completion visibility under parity-only FFMA writes")
    print("N pad  EE EO OE OO  (F=fresh, S=poison, ?=other/mixed)")
    fresh = {"E": 0x3f800000, "O": 0x40000000}
    poison = {"E": 0x7f000040, "O": 0x7f000041}
    for n in ns.storm_counts:
        for pad in ns.pads:
            chars = []
            for rp, sp in (("E", "E"), ("E", "O"),
                           ("O", "E"), ("O", "O")):
                vals = run_commit(n, sp, rp, pad, ns.reps)
                if all(v == fresh[rp] for v in vals):
                    ch = "F"
                elif all(v == poison[rp] for v in vals):
                    ch = "S"
                else:
                    ch = "?"
                chars.append(ch)
            print(f"{n:2d} {pad:3d}  " + "  ".join(chars))
    return 0


def retire_source(op: str, load_parity: str, phase: int,
                  write_gpr: bool) -> str:
    rd = 80 if load_parity == "E" else 81
    dst = "{R40,R41,R42,R43}" if write_gpr else "{RZ,RZ,RZ,RZ}"
    lines = [
        "#fn trfretire(out<8>, data<8>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC.64 {R6,R7}, #param(data);[2:7:{}:1:0]",
    ]
    for r in list(range(16, 22)) + list(range(24, 28)):
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    lines += [
        "    LDG.E R30, [{R6,R7}];[3:7:{2}:5:1]",
        "    IADD3 R31, R30, RZ, RZ;[7:7:{3}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        f"    LDG.E R{rd}, [{{R6,R7}}];[4:7:{{}}:1:1]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(phase)]
    if op == "hmma":
        tensor_inst = (f"HMMA.16816.F32.BF16 {dst}, "
                       "{R16,R17,R18,R19}, {R20,R21}, "
                       "{R24,R25,R26,R27}")
    elif op == "qmma":
        tensor_inst = (f"QMMA.16832.F32.E4M3.E4M3 {dst}, "
                       "{R16,R17,R18,R19}, {R20,R21}, "
                       "{R24,R25,R26,R27}")
    elif op == "imma":
        tensor_inst = (f"IMMA.16816.U8.U8 {dst}, {{R16,R17}}.ROW, "
                       "R20.COL, {R24,R25,R26,R27}, !UPT")
    else:
        raise ValueError(op)
    lines += [
        f"    {tensor_inst};[7:7:{{}}:1:0]",
        f"    IADD3 R32, R{rd}, RZ, RZ;[7:7:{{4}}:5:1]",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]",
        "    STG.E.STRONG.GPU [{R2,R3}+0x10], R32;[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_retire(op: str, parity: str, phase: int, write_gpr: bool,
               reps: int) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(
        retire_source(op, parity, phase, write_gpr), check_deps=True))
    out = mod.devmem_alloc(32)
    data = mod.devmem_alloc(128)
    mod.device_write(data, struct.pack("<32I", *([0x12345678] * 32)))
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("trfretire", grid=(1,), block=(32,), args=[out, data])
            mod.synchronize()
            t0, t1, got = struct.unpack("<QQI", mod.device_read(out, 20))
            if got != 0x12345678:
                raise RuntimeError(f"bad LDG result 0x{got:08x}")
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(data)
        mod.devmem_free(out)
    return vals


def retire_main(ns: argparse.Namespace) -> int:
    print(f"hot LDG completion under phase-shifted {ns.op.upper()} GPR/RZ result")
    print("phase  EG EZ dE  OG OZ dO | median deltas")
    for phase in ns.phases:
        rows = {(p, w): run_retire(ns.op, p, phase, w, ns.reps)
                for p in ("E", "O") for w in (True, False)}
        best = {k: min(v) for k, v in rows.items()}
        med = {k: statistics.median(v) for k, v in rows.items()}
        print(f"{phase:5d} {best['E',True]:3d} {best['E',False]:3d} "
              f"{best['E',True]-best['E',False]:+3d} "
              f"{best['O',True]:3d} {best['O',False]:3d} "
              f"{best['O',True]-best['O',False]:+3d} | "
              f"{med['E',True]-med['E',False]:+4.1f} "
              f"{med['O',True]-med['O',False]:+4.1f}")
    return 0


def throughput_source(op: str, n: int) -> str:
    lines = [
        "#fn trfthroughput(out<8>) {",
        "    #pragma MAXREG_COUNT(224)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += mma_stream(op, n, "rz")
    lines += [
        "    CS2R {R8,R9}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R6,R7};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R8,R9};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_throughput(op: str, n: int, reps: int) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(throughput_source(op, n), check_deps=True))
    out = mod.devmem_alloc(32)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("trfthroughput", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return vals


def throughput_main(ns: argparse.Namespace) -> int:
    points = []
    print(f"{ns.op.upper()} single-warp RZ-source throughput")
    print("N min median cycles/inst")
    for n in ns.counts:
        vals = run_throughput(ns.op, n, ns.reps)
        med = statistics.median(vals)
        points.append((n, med))
        print(f"{n:4d} {min(vals):5d} {med:7.1f} {med/n:9.4f}")
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    den = sum((x - xm) ** 2 for x, _ in points)
    slope = sum((x - xm) * (y - ym) for x, y in points) / den
    intercept = ym - slope * xm
    print(f"fit: cycles = {slope:.6f} * N + {intercept:.2f}")
    return 0


def mixedwb_source(op: str, blocks: int, write_gpr: bool) -> str:
    lines = [
        "#fn trfmixedwb(out<8>) {",
        "    #pragma MAXREG_COUNT(224)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    for i in range(blocks):
        rd = 32 + 4 * (i % 20)
        dst = (f"{{R{rd},R{rd+1},R{rd+2},R{rd+3}}}" if write_gpr
               else "{RZ,RZ,RZ,RZ}")
        if op == "hmma":
            inst = (f"HMMA.16816.F32.BF16 {dst}, "
                    "{RZ,RZ,RZ,RZ}, {RZ,RZ}, {RZ,RZ,RZ,RZ}")
        elif op == "qmma":
            inst = (f"QMMA.16832.F32.E4M3.E4M3 {dst}, "
                    "{RZ,RZ,RZ,RZ}, {RZ,RZ}, {RZ,RZ,RZ,RZ}")
        elif op == "imma":
            inst = (f"IMMA.16816.U8.U8 {dst}, {{RZ,RZ}}.ROW, RZ.COL, "
                    "{RZ,RZ,RZ,RZ}, !UPT")
        else:
            raise ValueError(op)
        lines.append(f"    {inst};[7:7:{{}}:1:0]")
        # Sixteen scalar results target only the even bank.  Sources are RZ,
        # so this is a writeback stream rather than an RF-read probe.
        for j in range(16):
            fd = 128 + 2 * ((16 * i + j) % 40)
            lines.append(f"    FADD R{fd}, RZ, RZ;[7:7:{{}}:1:0]")
    lines += [
        "    CS2R {R8,R9}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R6,R7};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R8,R9};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_mixedwb(op: str, blocks: int, write_gpr: bool,
                reps: int) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(
        mixedwb_source(op, blocks, write_gpr), check_deps=True))
    out = mod.devmem_alloc(32)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("trfmixedwb", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return vals


def mixedwb_main(ns: argparse.Namespace) -> int:
    print(f"{ns.op.upper()} result writes mixed with 16 even-bank FADD writes")
    print("blocks  GPR-min GPR-med  RZ-min RZ-med  delta/block")
    for n in ns.counts:
        g = run_mixedwb(ns.op, n, True, ns.reps)
        z = run_mixedwb(ns.op, n, False, ns.reps)
        delta = statistics.median(g) - statistics.median(z)
        print(f"{n:6d} {min(g):7d} {statistics.median(g):7.1f} "
              f"{min(z):7d} {statistics.median(z):6.1f} {delta/n:+11.4f}")
    return 0


def ramix_source(blocks: int, scalar_n: int, fixed: bool,
                 operand: str, reuse: int, only_operand: bool) -> str:
    lines = [
        "#fn trframix(out<8>) {",
        "    #pragma MAXREG_COUNT(224)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
    ]
    for r in range(16, 204):
        lines.append(f"    MOV32I R{r}, 0;[7:7:{{}}:5:1]")
    lines += ["    CS2R {R6,R7}, SR_CLOCKLO;[7:7:{}:5:0]"]
    for i in range(blocks):
        ar = (16 if fixed and operand == "a" else 32 + 4 * (i % 16))
        br = (96 if fixed and operand == "b" else 96 + 2 * (i % 16))
        rd = 128 + 4 * (i % 16)
        dst = ("{RZ,RZ,RZ,RZ}" if only_operand else
               f"{{R{rd},R{rd+1},R{rd+2},R{rd+3}}}")
        a = ("{RZ,RZ,RZ,RZ}" if only_operand and operand == "b" else
             f"{{R{ar},R{ar+1},R{ar+2},R{ar+3}}}")
        b = ("{RZ,RZ}" if only_operand and operand == "a" else
             f"{{R{br},R{br+1}}}")
        c = ("{RZ,RZ,RZ,RZ}" if only_operand else
             f"{{R{rd},R{rd+1},R{rd+2},R{rd+3}}}")
        lines.append(
            f"    HMMA.16816.F32.BF16 {dst}, {a}, {b}, {c};"
            f"[7:7:{{}}:1:0:{reuse}]")
        for _ in range(scalar_n):
            lines.append("    FADD RZ, R200, R202;[7:7:{}:1:1]")
    lines += ["    CS2R {R8,R9}, SR_CLOCKLO;[7:7:{}:5:0]"]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R2,R3}], {R6,R7};[7:1:{1}:8:0]",
        "    STG.E.64.STRONG.GPU [{R2,R3}+8], {R8,R9};[7:1:{}:8:0]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def run_ramix(blocks: int, scalar_n: int, fixed: bool, operand: str,
              reuse: int, only_operand: bool, reps: int) -> list[int]:
    reset_context()
    mod = CudaModule(assemble(
        ramix_source(blocks, scalar_n, fixed, operand, reuse, only_operand),
        check_deps=True))
    out = mod.devmem_alloc(32)
    vals = []
    try:
        for rep in range(reps + 1):
            mod.launch("trframix", grid=(1,), block=(32,), args=[out])
            mod.synchronize()
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            if rep:
                vals.append((t1 - t0) & ((1 << 64) - 1))
    finally:
        mod.devmem_free(out)
    return vals


def ramix_main(ns: argparse.Namespace) -> int:
    print(f"single-warp fixed/rotating R{ns.operand} around the HMMA/RF "
          f"threshold (reuse={ns.reuse}, only={ns.only_operand})")
    print("FADDs fixed-min fixed-med rotate-min rotate-med delta/block")
    for k in ns.scalar_counts:
        f = run_ramix(ns.blocks, k, True, ns.operand, ns.reuse,
                      ns.only_operand, ns.reps)
        r = run_ramix(ns.blocks, k, False, ns.operand, ns.reuse,
                      ns.only_operand, ns.reps)
        delta = statistics.median(f) - statistics.median(r)
        print(f"{k:5d} {min(f):9d} {statistics.median(f):9.1f} "
              f"{min(r):10d} {statistics.median(r):10.1f} "
              f"{delta/ns.blocks:+11.4f}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    pc = sub.add_parser("collect")
    pc.add_argument("--op", choices=("hmma", "qmma", "imma"),
                    default="hmma")
    pc.add_argument("--victim-count", type=int, default=4096)
    pc.add_argument("--tensor-count", type=int, default=512)
    pc.add_argument("--reps", type=int, default=20)
    pc.add_argument("--sources", default="rz,a,b,c,ab,abc",
                    help="comma-separated HMMA GPR source groups")
    pc.add_argument("--reuse", type=int, choices=range(8), default=0,
                    help="schedule reuse mask; dense SM120 MMA uses bit 1/Rb")
    pw = sub.add_parser("commit")
    pw.add_argument("--storm-counts", default="0,8,16,24,32,40,48")
    pw.add_argument("--pads", default="0,2,4,6,8,10,12,16")
    pw.add_argument("--reps", type=int, default=5)
    pr = sub.add_parser("retire")
    pr.add_argument("--op", choices=("hmma", "qmma", "imma"),
                    default="hmma")
    pr.add_argument("--phases", default="0,4,8,12,16,20,24,28,32,36,40")
    pr.add_argument("--reps", type=int, default=30)
    pt = sub.add_parser("throughput")
    pt.add_argument("--op", choices=("hmma", "qmma", "imma"),
                    default="hmma")
    pt.add_argument("--counts", default="64,128,256,512")
    pt.add_argument("--reps", type=int, default=20)
    pm = sub.add_parser("mixedwb")
    pm.add_argument("--op", choices=("hmma", "qmma", "imma"),
                    default="hmma")
    pm.add_argument("--counts", default="32,64,128,256")
    pm.add_argument("--reps", type=int, default=20)
    pa = sub.add_parser("ramix")
    pa.add_argument("--blocks", type=int, default=256)
    pa.add_argument("--scalar-counts", default="3,4,5,6,7,8")
    pa.add_argument("--operand", choices=("a", "b"), default="a")
    pa.add_argument("--reuse", type=int, choices=range(8), default=0,
                    help="schedule reuse mask; use 2 for dense-HMMA Rb")
    pa.add_argument("--only-operand", action="store_true",
                    help="replace all tensor RF operands except the selected one with RZ")
    pa.add_argument("--reps", type=int, default=20)
    ns = p.parse_args()
    if ns.mode == "commit":
        ns.storm_counts = [int(x) for x in ns.storm_counts.split(",")]
        ns.pads = [int(x) for x in ns.pads.split(",")]
        return commit_main(ns)
    if ns.mode == "retire":
        ns.phases = [int(x) for x in ns.phases.split(",")]
        return retire_main(ns)
    if ns.mode == "throughput":
        ns.counts = [int(x) for x in ns.counts.split(",")]
        return throughput_main(ns)
    if ns.mode == "mixedwb":
        ns.counts = [int(x) for x in ns.counts.split(",")]
        return mixedwb_main(ns)
    if ns.mode == "ramix":
        ns.scalar_counts = [int(x) for x in ns.scalar_counts.split(",")]
        return ramix_main(ns)
    ns.sources = [x.strip().lower() for x in ns.sources.split(",")]
    if any(x not in ("rz", "a", "b", "c", "ab", "ac", "bc", "abc",
                         "c_sep", "c_rmw", "amp_fixed", "amp_rotate",
                         "bw_fixed", "bw_rotate")
           for x in ns.sources):
        p.error("--sources entries must be a/b/c combinations, c_sep/c_rmw, or rz")
    return collect_main(ns)


if __name__ == "__main__":
    raise SystemExit(main())
