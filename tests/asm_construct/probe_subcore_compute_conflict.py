#!/usr/bin/env python3
"""Pairwise subcore compute-pipe conflict probe for sm_90 and sm_120.

The timed victim is warp 0.  A runtime-selected contender is either warp 4
(same subcore) or warp 1 (different subcore); the established in-CTA mapping
is ``warp_id % 4``.  NOP contenders measure the common scheduler/issue cost.

For each (A, B), fit the victim cycles against the unrolled instruction count
for these placements:

    solo       warp 0=A, no contender
    same_nop   warp 0=A, warp 4=NOP (diagnostic only)
    same_ctrl  warp 0=A, warp 4=@P6 B, with P6 architecturally false
    same_ab    warp 0=A, warp 4=B
    diff_nop   warp 0=A, warp 1=NOP (diagnostic only)
    diff_ctrl  warp 0=A, warp 1=@P6 B
    diff_ab    warp 0=A, warp 1=B

Three difference-in-differences scores separate predicate-insensitive
dispatch pressure from predicate-sensitive execution pressure:

    E_dispatch = (same_ctrl - same_nop) - (diff_ctrl - diff_nop)
    E_execute  = (same_ab - same_ctrl) - (diff_ab - diff_ctrl)
    E_total    = (same_ab - same_nop) - (diff_ab - diff_nop)

A positive score is evidence of same-subcore structural sharing beyond the
corresponding control path.  Predicated-off instructions can still reserve a
dispatch queue/pipe, so E_dispatch is real information rather than overhead to
discard.  This first-stage probe measures sustained *issue/backpressure*
throughput, not dependent-chain latency or final-result visibility.

Examples:
    python3 tests/asm_construct/probe_subcore_compute_conflict.py --smoke
    python3 tests/asm_construct/probe_subcore_compute_conflict.py \
        --pair iadd3,ffma --lengths 128,256,512,1024 --reps 5 --csv /tmp/sc.csv
    python3 tests/asm_construct/probe_subcore_compute_conflict.py --all

For an ncu evidence pass, restrict it to one placement and length, e.g.:
    sudo /usr/local/cuda/bin/ncu --metrics \
      smsp__average_warp_latency_issue_stalled_math_pipe_throttle.pct,\
smsp__pipe_alu_cycles_active.avg.pct_of_peak_sustained_active,\
smsp__pipe_fma_cycles_active.avg.pct_of_peak_sustained_active \
      python3 tests/asm_construct/probe_subcore_compute_conflict.py \
      --pair iadd3,ffma --lengths 512 --reps 1 --placements same_ab
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble  # noqa: E402
from assembler.arch import current  # noqa: E402


PLACEMENTS = {
    "solo": (7, 0),       # warp 7 reaches dispatch but kind=0 -> EXIT
    "same_nop": (4, 1),   # warp 4 aliases warp 0's subcore
    "same_ctrl": (4, 3),
    "same_ab": (4, 2),
    "diff_nop": (1, 1),   # warp 1 is on another subcore
    "diff_ctrl": (1, 3),
    "diff_ab": (1, 2),
    # Extended placement sweep.  These aliases are intentionally not part of
    # DEFAULT_PLACEMENTS so ordinary runs retain the original compact matrix.
    "sc1_ctrl": (1, 3),
    "sc1_ab": (1, 2),
    "sc2_ctrl": (2, 3),
    "sc2_ab": (2, 2),
    "sc3_ctrl": (3, 3),
    "sc3_ab": (3, 2),
}

DEFAULT_PLACEMENTS = (
    "solo", "same_nop", "same_ctrl", "same_ab",
    "diff_nop", "diff_ctrl", "diff_ab",
)

# Keep sources parity-balanced and destinations away from harness registers.
# Forty independent destinations exceed the known fixed/MUFU latencies and
# suppress accidental RAW/WAW serialization.
DSTS = tuple(range(40, 80))
SCHED = "[7:7:{}:1:1]"


@dataclass(frozen=True)
class Op:
    name: str
    pipe: str
    fmt: str
    sched: str = SCHED

    def instruction(self, i: int) -> str:
        d = DSTS[i % len(DSTS)]
        de = 40 + 2 * (i % 20)
        return self.fmt.format(d=d, do=d ^ 1, de0=de, de1=de + 1)


OPS = {
    "nop": Op("nop", "fe", "NOP"),
    "iadd3": Op("iadd3", "int/alu", "IADD3 R{d}, R24, R27, R28"),
    "iadd3_o": Op("iadd3_o", "int/alu", "IADD3 R{do}, R24, R27, R28"),
    "iadd3_s": Op("iadd3_s", "int/alu", "IADD3 R{do}, R25, R26, R29"),
    "iadd3_e": Op("iadd3_e", "int/alu", "IADD3 R{d}, R24, R26, R28"),
    "iadd3_1r": Op("iadd3_1r", "int/alu", "IADD3 R{d}, R24, RZ, RZ"),
    "iadd3_y0": Op("iadd3_y0", "int/alu", "IADD3 R{d}, R24, R27, R28",
                     "[7:7:{}:1:0]"),
    "iadd3_ra": Op("iadd3_ra", "int/alu", "IADD3 R{d}, R24, R27, R28",
                     "[7:7:{}:1:0:1]"),
    "iadd3_rabc": Op(
        "iadd3_rabc", "int/alu-reuse",
        "IADD3 R{d}, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "iadd3_rz": Op(
        "iadd3_rz", "int/alu-reuse-no-wb",
        "IADD3 RZ, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "lop3": Op("lop3", "int/alu", "LOP3.LUT R{d}, R24, R27, R28, 0x96"),
    "shf": Op("shf", "int/alu", "SHF.R.U32.HI R{d}, R24, R27, R28"),
    "imad": Op("imad", "fmalighter/intmul", "IMAD R{d}, R24, R27, R28"),
    "imad_rabc": Op(
        "imad_rabc", "fmaheavy/intmul-reuse",
        "IMAD R{d}, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "imad_rz": Op(
        "imad_rz", "fmaheavy/intmul-reuse-no-wb",
        "IMAD RZ, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "imad_hi": Op(
        "imad_hi", "fmaheavy/intmul-high",
        "IMAD.HI R{d}, PT, R24, R27, {{R28,R29}}"),
    "imad_hi_rabc": Op(
        "imad_hi_rabc", "fmaheavy/intmul-high-reuse",
        "IMAD.HI R{d}, PT, R24, R27, {{R28,R29}}", "[7:7:{}:1:0:7]"),
    "imad_wide": Op(
        "imad_wide", "fmaheavy/intmul-wide",
        "IMAD.WIDE.U32 {{R{de0},R{de1}}}, PT, R24, R27, {{R28,R29}}"),
    "imad_wide_rabc": Op(
        "imad_wide_rabc", "fmaheavy/intmul-wide-reuse",
        "IMAD.WIDE.U32 {{R{de0},R{de1}}}, PT, R24, R27, {{R28,R29}}",
        "[7:7:{}:1:0:7]"),
    "idp4": Op(
        "idp4", "fmaheavy/int-dot",
        "IDP.4A.U8.U8 R{d}, R24, R27, R28"),
    "idp2": Op(
        "idp2", "fmaheavy/int-dot",
        "IDP.2A.LO.U16.U8 R{d}, R24, R27, R28"),
    "imad_o": Op("imad_o", "fmalighter/intmul", "IMAD R{do}, R24, R27, R28"),
    "imad_s": Op("imad_s", "fmalighter/intmul", "IMAD R{do}, R25, R26, R29"),
    "imad_y0": Op("imad_y0", "fmalighter/intmul", "IMAD R{d}, R24, R27, R28",
                    "[7:7:{}:1:0]"),
    "imad_ra": Op("imad_ra", "fmalighter/intmul", "IMAD R{d}, R24, R27, R28",
                    "[7:7:{}:1:0:1]"),
    "ffma": Op("ffma", "fmalighter", "FFMA R{d}, R24, R27, R28"),
    "ffma_o": Op("ffma_o", "fmalighter", "FFMA R{do}, R24, R27, R28"),
    "ffma_s": Op("ffma_s", "fmalighter", "FFMA R{do}, R25, R26, R29"),
    "ffma_e": Op("ffma_e", "fmalighter", "FFMA R{d}, R24, R26, R28"),
    "ffma_2r": Op("ffma_2r", "fmalighter", "FFMA R{d}, R24, R27, RZ"),
    "ffma_y0": Op("ffma_y0", "fmalighter", "FFMA R{d}, R24, R27, R28",
                    "[7:7:{}:1:0]"),
    # All-even fixed sources with controlled reuse masks.  A reuse bit on one
    # instruction supplies that operand slot to the next instruction.
    "ffma_e_y0": Op("ffma_e_y0", "fmalighter",
                       "FFMA R{d}, R24, R26, R28", "[7:7:{}:1:0]"),
    "ffma_e_ra": Op("ffma_e_ra", "fmalighter",
                      "FFMA R{d}, R24, R26, R28", "[7:7:{}:1:0:1]"),
    "ffma_e_rb": Op("ffma_e_rb", "fmalighter",
                      "FFMA R{d}, R24, R26, R28", "[7:7:{}:1:0:2]"),
    "ffma_e_rc": Op("ffma_e_rc", "fmalighter",
                      "FFMA R{d}, R24, R26, R28", "[7:7:{}:1:0:4]"),
    "ffma_e_rab": Op("ffma_e_rab", "fmalighter",
                       "FFMA R{d}, R24, R26, R28", "[7:7:{}:1:0:3]"),
    "ffma_e_rabc": Op("ffma_e_rabc", "fmalighter",
                        "FFMA R{d}, R24, R26, R28", "[7:7:{}:1:0:7]"),
    "ffma_rz": Op(
        "ffma_rz", "fmalighter/reuse-no-wb",
        "FFMA RZ, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "fadd": Op("fadd", "fmalighter", "FADD R{d}, R24, R27"),
    "fadd32i": Op(
        "fadd32i", "fmalighter", "FADD32I R{d}, R24, 0f3f800000"),
    "fadd_o": Op("fadd_o", "fmalighter", "FADD R{do}, R24, R27"),
    "fadd_s": Op("fadd_s", "fmalighter", "FADD R{do}, R25, R26"),
    "fadd_e": Op("fadd_e", "fmalighter", "FADD R{d}, R24, R26"),
    "fadd_1e": Op("fadd_1e", "fmalighter", "FADD RZ, R24, RZ"),
    "fadd_1o": Op("fadd_1o", "fmalighter", "FADD RZ, R25, RZ"),
    "fadd_2e_z": Op("fadd_2e_z", "fmalighter", "FADD RZ, R24, R26"),
    "fadd_2o_z": Op("fadd_2o_z", "fmalighter", "FADD RZ, R25, R27"),
    "fadd_y0": Op("fadd_y0", "fmalighter", "FADD R{d}, R24, R27",
                    "[7:7:{}:1:0]"),
    "fadd_rab": Op("fadd_rab", "fmalighter", "FADD R{d}, R24, R27",
                     "[7:7:{}:1:0:3]"),
    "ffma32i": Op(
        "ffma32i", "fmalighter",
        "FFMA32I R{d}, R24, 0f3f800000, R28"),
    "fhadd": Op("fhadd", "fmalighter", "FHADD.F16 R{d}, R24, R27"),
    "fhfma": Op(
        "fhfma", "fmalighter", "FHFMA.F16 R{d}, R24, R27, R28"),
    "fmul": Op("fmul", "fmalighter", "FMUL R{d}, R24, R27"),
    "fmul32i": Op(
        "fmul32i", "fmalighter", "FMUL32I R{d}, R24, 0f3f800000"),
    "fswzadd": Op(
        "fswzadd", "fmalighter",
        "FSWZADD.NDV R{d}, R24, R27, PPPPPPPP"),
    "imul": Op("imul", "fmalighter", "IMUL.U32 R{d}, R24, R27"),
    "imul32i": Op(
        "imul32i", "fmalighter", "IMUL32I.U32 R{d}, R24, 0x3"),
    "mov": Op("mov", "alu", "MOV R{d}, R24"),
    "mov_ra": Op(
        "mov_ra", "alulite/reuse", "MOV R{d}, R24", "[7:7:{}:1:0:1]"),
    "mov_rz": Op(
        "mov_rz", "alulite/reuse-no-wb", "MOV RZ, R24",
        "[7:7:{}:1:0:1]"),
    "mov_imad_pair": Op(
        "mov_imad_pair", "alulite+fmaheavy",
        "MOV R{d}, R24;[7:7:{{}}:1:0:1]\n"
        "    IMAD R{do}, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "ffma_imad_pair": Op(
        "ffma_imad_pair", "fmalite+fmaheavy",
        "FFMA R{d}, R24, R27, R28;[7:7:{{}}:1:0:7]\n"
        "    IMAD R{do}, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "mov32i": Op("mov32i", "alu", "MOV32I R{d}, 0x12345678"),
    "sel": Op("sel", "alu", "SEL R{d}, R24, R27, PT"),
    "lea": Op("lea", "alu", "LEA R{d}, R24, R27, 0x4"),
    "sgxt": Op("sgxt", "alu", "SGXT R{d}, R24, 0x5"),
    "imnmx": Op("imnmx", "alu", "IMNMX.U32 R{d}, R24, R27, PT"),
    "vimnmx": Op("vimnmx", "alu", "VIMNMX.U32 R{d}, R24, R27, PT"),
    "viadd": Op("viadd", "alu", "VIADD.U32 R{d}, R24, R27"),
    "fmnmx": Op("fmnmx", "alu", "FMNMX R{d}, R24, R27, PT"),
    "fsel": Op("fsel", "alu", "FSEL R{d}, R24, R27, PT"),
    "fset": Op(
        "fset", "alu", "FSET.BF.LT.AND R{d}, R24, R27, PT"),
    "fsetp": Op(
        "fsetp", "alu", "FSETP.LT.AND P0, P1, R24, R27, PT"),
    "plop3": Op(
        "plop3", "alu", "PLOP3.LUT P0, PT, PT, PT, PT, 0x96"),
    "isetp": Op(
        "isetp", "alu", "ISETP.NE.AND P0, PT, R24, R27, PT"),
    "bmsk": Op("bmsk", "alu", "BMSK R{d}, R24, R27"),
    "iabs": Op("iabs", "alu", "IABS R{d}, R24"),
    "f2fp": Op(
        "f2fp", "alu", "F2FP.F16.F32.PACK_AB R{d}, R24, R27"),
    "f2ip": Op(
        "f2ip", "alu", "F2IP.U8.F32 R{d}, RZ, R24, RZ"),
    "i2fp": Op("i2fp", "alu", "I2FP.F32.S32 R{d}, R24"),
    "i2i": Op("i2i", "alu", "I2I.SAT.U8 R{d}, R24"),
    "i2ip": Op(
        "i2ip", "alu", "I2IP.U8.S32 R{d}, RZ, R24, RZ"),
    "iadd": Op("iadd", "alu", "IADD R{d}, PT, R24, R27"),
    "iadd_rab": Op(
        "iadd_rab", "alulite/reuse", "IADD R{d}, PT, R24, R27",
        "[7:7:{}:1:0:3]"),
    "iadd_rz": Op(
        "iadd_rz", "alulite/reuse-no-wb", "IADD RZ, PT, R24, R27",
        "[7:7:{}:1:0:3]"),
    "iadd_imad_pair": Op(
        "iadd_imad_pair", "alulite-add+fmaheavy",
        "IADD R{d}, PT, R24, R27;[7:7:{{}}:1:0:3]\n"
        "    IMAD R{do}, R24, R27, R28", "[7:7:{}:1:0:7]"),
    "iadd32i": Op("iadd32i", "alu", "IADD32I R{d}, PT, R24, 0x1"),
    "iscadd": Op(
        "iscadd", "alu", "ISCADD R{d}, PT, R24, R27, 0x2"),
    "iscadd32i": Op(
        "iscadd32i", "alu", "ISCADD32I R{d}, PT, R24, 0x1, 0x2"),
    "lop": Op("lop", "alu", "LOP.XOR PT, R{d}, R24, R27"),
    "lop32i": Op(
        "lop32i", "alu", "LOP32I.XOR PT, R{d}, R24, 0x12345678"),
    "mov64iur": Op(
        "mov64iur", "alu", "MOV64IUR {{R{de0},R{de1}}}, 0x12345678"),
    "p2r": Op("p2r", "alu", "P2R R{d}, PR, RZ, 0x7f"),
    "psetp": Op("psetp", "alu", "PSETP.AND P0, PT, PT"),
    "r2p": Op("r2p", "alu", "R2P PR, R24, 0x7f"),
    "shl": Op("shl", "alu", "SHL R{d}, R24, R27"),
    "shr": Op("shr", "alu", "SHR.U32 R{d}, R24, R27"),
    "prmt": Op("prmt", "alu", "PRMT R{d}, R24, R27, R28"),
    "hfma2": Op("hfma2", "fp16", "HFMA2 R{d}, R24, R27, R28"),
    "hfma2_o": Op("hfma2_o", "fp16", "HFMA2 R{do}, R24, R27, R28"),
    "hfma2_s": Op("hfma2_s", "fp16", "HFMA2 R{do}, R25, R26, R29"),
    "hfma2_e": Op("hfma2_e", "fp16", "HFMA2 R{d}, R24, R26, R28"),
    "hfma2_y0": Op("hfma2_y0", "fp16", "HFMA2 R{d}, R24, R27, R28",
                     "[7:7:{}:1:0]"),
    "hfma2_ra": Op("hfma2_ra", "fp16", "HFMA2 R{d}, R24, R27, R28",
                     "[7:7:{}:1:0:1]"),
    "hadd2": Op("hadd2", "fp16", "HADD2 R{d}, R24, R27"),
    "hadd2_32i": Op(
        "hadd2_32i", "fp16",
        "HADD2_32I R{d}, R24, 0f3f800000, 0f3f800000"),
    "hadd2_y0": Op("hadd2_y0", "fp16", "HADD2 R{d}, R24, R27",
                     "[7:7:{}:1:0]"),
    "hfma2_32i": Op(
        "hfma2_32i", "fp16",
        "HFMA2_32I R{d}, R24, 0f3f800000, 0f3f800000, R28"),
    "hfma2_mma": Op(
        "hfma2_mma", "fma64lite/hfma2mma",
        "HFMA2.MMA R{d}, R24, R27, R28"),
    "hadd2_f32": Op(
        "hadd2_f32", "fp16/widen", "HADD2.F32 R{d}, -RZ, R24.H0_H0"),
    "hmnmx2": Op(
        "hmnmx2", "fp16", "HMNMX2 R{d}, R24, R27, PT"),
    "hmul2": Op("hmul2", "fp16", "HMUL2 R{d}, R24, R27"),
    "hmul2_32i": Op(
        "hmul2_32i", "fp16",
        "HMUL2_32I R{d}, R24, 0f3f800000, 0f3f800000"),
    "hset2": Op(
        "hset2", "fp16", "HSET2.BF.LT.AND R{d}, R24, R27, PT"),
    "hsetp2": Op(
        "hsetp2", "fp16", "HSETP2.LT.AND P0, P1, R24, R27, PT"),
    "dfma": Op(
        "dfma", "fma64lite",
        "DFMA {{R{de0},R{de1}}}, {{R24,R25}}, {{R26,R27}}, {{R28,R29}}"),
    "dadd": Op(
        "dadd", "fma64lite",
        "DADD {{R{de0},R{de1}}}, {{R24,R25}}, {{R26,R27}}"),
    "dmul": Op(
        "dmul", "fma64lite",
        "DMUL {{R{de0},R{de1}}}, {{R24,R25}}, {{R26,R27}}"),
    "dsetp": Op(
        "dsetp", "fma64lite",
        "DSETP.LT.AND P0, P1, {{R24,R25}}, {{R26,R27}}, PT"),
    "clmad": Op(
        "clmad", "fma64lite/clmad",
        "CLMAD.LO {{R{de0},R{de1}}}, {{R24,R25}}, {{R26,R27}}, {{R28,R29}}",
        "[7:7:{}:8:1]"),
    "mufu": Op("mufu", "mio/mufu", "MUFU.RCP R{d}, R24"),
    "shfl": Op("shfl", "mio/shfl", "SHFL.BFLY PT, R{d}, R24, 0x1, 0x1f"),
    # All lanes read the same shared word, which is a broadcast rather than a
    # bank conflict.  Results are deliberately dead, as for the MUFU stream.
    "lds": Op("lds", "mio/lsu/shared", "LDS R{d}, [RZ]"),
}

DEFAULT_PAIRS = (
    ("iadd3", "iadd3"),
    ("ffma", "ffma"),
    ("hfma2", "hfma2"),
    ("mufu", "mufu"),
    ("iadd3", "ffma"),
    ("iadd3", "hfma2"),
    ("ffma", "hfma2"),
    ("ffma", "mufu"),
)


def body(op: Op, count: int, guard: str = "") -> list[str]:
    prefix = f"{guard} " if guard else ""
    return [f"    {prefix}{op.instruction(i)};{op.sched}" for i in range(count)]


def build_source(a: Op, b: Op, n: int, contender_factor: int) -> str:
    """Build one cubin whose runtime params select every placement."""
    lines = [
        "#fn scconf(out<8>, contender_warp<4>, contender_kind<4>) {",
        "    #pragma MAXREG_COUNT(96)",
        "    #pragma SHARED(1024)",
        "    LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]",
        "    LDC R12, #param(contender_warp);[2:7:{}:1:0]",
        "    LDC R13, #param(contender_kind);[3:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[4:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R6,R7}, R4, 0x10, {R2,R3};[7:7:{1,4}:5:1]",
        "    SHR R5, R4, 0x5;[7:7:{4}:5:1]",
        # Stable finite inputs for integer, FP32, packed FP16 and MUFU ops.
        "    MOV32I R24, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R25, 0x3f803c00;[7:7:{}:5:1]",
        "    MOV32I R26, 0x40003c00;[7:7:{}:5:1]",
        "    MOV32I R27, 0x40003c00;[7:7:{}:5:1]",
        "    MOV32I R28, 0x3f003c00;[7:7:{}:5:1]",
        "    MOV32I R29, 0x3f003c00;[7:7:{}:5:1]",
    ]
    for d in DSTS:
        lines.append(f"    MOV32I R{d}, 0;[7:7:{{}}:5:1]")
    lines += [
        # All eight warps participate before non-actors exit.
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:0]",
        "    ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(victim);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R5, R12, PT;[7:7:{2}:13:1]",
        "    @!P0 BRA #label(done);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R13, 0x1, PT;[7:7:{3}:13:1]",
        "    @P0 BRA #label(contender_nop);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R13, 0x2, PT;[7:7:{3}:13:1]",
        "    @P0 BRA #label(contender_b);[7:7:{}:5:1]",
        "    ISETP.EQ.AND P0, PT, R13, 0x3, PT;[7:7:{3}:13:1]",
        "    @P0 BRA #label(contender_ctrl);[7:7:{}:5:1]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(victim)",
    ]
    lines += body(a, n)
    lines += [
        "    CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    # Give the coupled clock read ample time to write back without introducing
    # a dependency on the tested destination registers.
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R30,R31};[7:1:{}:8:0]",
        "    BRA #label(done);[7:7:{}:5:1]",
        "#def_label(contender_nop)",
    ]
    lines += body(OPS["nop"], n * contender_factor)
    lines += ["    BRA #label(contender_done);[7:7:{}:5:1]",
              "#def_label(contender_b)"]
    lines += body(b, n * contender_factor)
    lines += [
        "    BRA #label(contender_done);[7:7:{}:5:1]",
        "#def_label(contender_ctrl)",
    ]
    # P6 is never written by the harness and is false at kernel entry.  The
    # exact B encoding/schedule still traverses fetch/issue/dispatch, while
    # its architectural operand read, execution and writeback are disabled.
    lines += body(b, n * contender_factor, "@P6")
    lines += [
        "#def_label(contender_done)",
        "    CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:0]",
    ]
    lines += ["    NOP;[7:7:{}:1:1]" for _ in range(16)]
    lines += [
        "    STG.E.64.STRONG.GPU [{R6,R7}], {R20,R21};[7:1:{}:8:0]",
        "    STG.E.64.STRONG.GPU [{R6,R7}+0x8], {R22,R23};[7:1:{}:8:0]",
        "#def_label(done)",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def fit_slope(points: list[tuple[int, float]]) -> tuple[float, float]:
    """Return least-squares slope and intercept for cycles = m*N + c."""
    if len(points) == 1:
        n, cycles = points[0]
        return cycles / n, 0.0
    xm = statistics.mean(x for x, _ in points)
    ym = statistics.mean(y for _, y in points)
    den = sum((x - xm) ** 2 for x, _ in points)
    slope = sum((x - xm) * (y - ym) for x, y in points) / den
    return slope, ym - slope * xm


def parse_pair(text: str) -> tuple[str, str]:
    try:
        a, b = (x.strip().lower() for x in text.split(",", 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pair must be A,B") from exc
    if a not in OPS or b not in OPS:
        raise argparse.ArgumentTypeError(
            f"unknown op in {text!r}; choices: {', '.join(OPS)}")
    return a, b


def parse_csv_list(text: str, valid: set[str]) -> list[str]:
    vals = [x.strip() for x in text.split(",") if x.strip()]
    bad = [x for x in vals if x not in valid]
    if bad:
        raise argparse.ArgumentTypeError(
            f"unknown value(s) {bad}; choices: {', '.join(sorted(valid))}")
    return vals


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pair", action="append", type=parse_pair,
                   help="A,B pair; repeatable (default: representative matrix)")
    p.add_argument("--all", action="store_true",
                   help="run the full ordered cross-product of available non-NOP ops")
    p.add_argument("--smoke", action="store_true",
                   help="quick iadd3/ffma self and cross checks")
    p.add_argument("--lengths", default="128,256,512",
                   help="comma-separated victim instruction counts")
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--contender-factor", type=int, default=4,
                   help="contender length divided by victim length")
    p.add_argument("--placements", default=",".join(DEFAULT_PLACEMENTS),
                   help="comma-separated placement subset")
    p.add_argument("--csv", type=Path, help="write every raw timing sample")
    p.add_argument("--emit-dir", type=Path,
                   help="assemble cubins into this directory and exit (for GPU hosts without Python)")
    p.add_argument("--seed", type=int, default=120)
    ns = p.parse_args()
    try:
        ns.lengths = [int(x) for x in ns.lengths.split(",") if x.strip()]
    except ValueError as exc:
        p.error(f"bad --lengths: {exc}")
    if not ns.lengths or min(ns.lengths) <= 0:
        p.error("--lengths must contain positive integers")
    if ns.reps <= 0 or ns.contender_factor <= 0:
        p.error("--reps and --contender-factor must be positive")
    try:
        ns.placements = parse_csv_list(ns.placements, set(PLACEMENTS))
    except argparse.ArgumentTypeError as exc:
        p.error(str(exc))
    if not ns.placements:
        p.error("--placements must not be empty")
    return ns


def chosen_pairs(ns: argparse.Namespace) -> list[tuple[str, str]]:
    if ns.pair:
        return ns.pair
    if ns.all:
        names = [x for x in OPS if x != "nop"]
        return [(a, b) for a in names for b in names]
    if ns.smoke:
        return [("iadd3", "iadd3"), ("ffma", "ffma"),
                ("iadd3", "ffma")]
    return list(DEFAULT_PAIRS)


def main() -> int:
    ns = arguments()
    pairs = chosen_pairs(ns)
    if ns.emit_dir:
        ns.emit_dir.mkdir(parents=True, exist_ok=True)
        for a_name, b_name in pairs:
            for n in ns.lengths:
                src = build_source(OPS[a_name], OPS[b_name], n,
                                   ns.contender_factor)
                cubin = assemble(src, check_deps=True)
                path = ns.emit_dir / f"{a_name}__{b_name}__n{n}.cubin"
                path.write_bytes(cubin)
                print(path)
        return 0
    raw_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    # (a,b,placement) -> [(N, best cycles)]
    best_points: dict[tuple[str, str, str], list[tuple[int, float]]] = {}
    rng = random.Random(ns.seed)

    print(f"subcore compute structural-conflict probe ({current().name})")
    print(f"pairs={len(pairs)} lengths={ns.lengths} reps={ns.reps} "
          f"placements={','.join(ns.placements)}")
    print("victim=warp0; same=warp4; different=warp1; body=stall1/yield1")

    for a_name, b_name in pairs:
        a, b = OPS[a_name], OPS[b_name]
        print(f"\n[{a_name}({a.pipe}) <- {b_name}({b.pipe})]", flush=True)
        for n in ns.lengths:
            src = build_source(a, b, n, ns.contender_factor)
            cubin = assemble(src, check_deps=True)
            mod = CudaModule(cubin)
            out = mod.devmem_alloc(256 * 16)
            try:
                # Warm every selected runtime path before measuring it.
                for placement in ns.placements:
                    cw, kind = PLACEMENTS[placement]
                    mod.launch("scconf", grid=(1,), block=(256,),
                               args=[out, cw, kind])
                    mod.synchronize()

                samples = {p: [] for p in ns.placements}
                order = ns.placements * ns.reps
                rng.shuffle(order)
                for placement in order:
                    cw, kind = PLACEMENTS[placement]
                    mod.launch("scconf", grid=(1,), block=(256,),
                               args=[out, cw, kind])
                    mod.synchronize()
                    t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
                    cycles = float((t1 - t0) & ((1 << 64) - 1))
                    contender_cycles = None
                    if kind:
                        off = cw * 32 * 16
                        c0, c1 = struct.unpack(
                            "<QQ", mod.device_read(out + off, 16))
                        contender_cycles = int(
                            (c1 - c0) & ((1 << 64) - 1))
                    samples[placement].append(cycles)
                    raw_rows.append({
                        "victim": a_name, "contender": b_name,
                        "victim_pipe": a.pipe, "contender_pipe": b.pipe,
                        "placement": placement, "n": n,
                        "cycles": int(cycles), "cycles_per_inst": cycles / n,
                        "contender_cycles": contender_cycles,
                        "overlap_ok": (contender_cycles is None or
                                       contender_cycles >= cycles),
                    })
                vals = []
                for placement in ns.placements:
                    # best-of suppresses host/display/preemption outliers; the
                    # randomized order prevents a placement-correlated drift.
                    best = min(samples[placement])
                    best_points.setdefault((a_name, b_name, placement), []).append(
                        (n, best))
                    rows = [r for r in raw_rows
                            if r["victim"] == a_name
                            and r["contender"] == b_name
                            and r["placement"] == placement and r["n"] == n]
                    overlap = all(bool(r["overlap_ok"]) for r in rows)
                    vals.append(f"{placement}={best/n:.3f}"
                                + ("" if overlap else "(!short)"))
                print(f"  N={n:<4d} " + "  ".join(vals), flush=True)
            finally:
                mod.devmem_free(out)

        slopes = {}
        for placement in ns.placements:
            slopes[placement] = fit_slope(
                best_points[(a_name, b_name, placement)])[0]
        print("  fitted cyc/inst: " + "  ".join(
            f"{p}={slopes[p]:.4f}" for p in ns.placements))
        row: dict[str, object] = {
            "victim": a_name, "contender": b_name,
            **{f"slope_{p}": slopes.get(p, "") for p in PLACEMENTS},
            "e_dispatch": "", "e_execute": "", "e_total": "",
        }
        need = {"same_nop", "same_ctrl", "same_ab",
                "diff_nop", "diff_ctrl", "diff_ab"}
        if need.issubset(slopes):
            e_dispatch = ((slopes["same_ctrl"] - slopes["same_nop"])
                          - (slopes["diff_ctrl"] - slopes["diff_nop"]))
            e_execute = ((slopes["same_ab"] - slopes["same_ctrl"])
                         - (slopes["diff_ab"] - slopes["diff_ctrl"]))
            e_total = ((slopes["same_ab"] - slopes["same_nop"])
                       - (slopes["diff_ab"] - slopes["diff_nop"]))
            print(f"  E_dispatch={e_dispatch:+.4f}  "
                  f"E_execute={e_execute:+.4f}  "
                  f"E_total={e_total:+.4f} cyc/inst")
            row.update(e_dispatch=e_dispatch, e_execute=e_execute,
                       e_total=e_total)
        summary_rows.append(row)

    if ns.csv:
        ns.csv.parent.mkdir(parents=True, exist_ok=True)
        with ns.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(raw_rows[0]))
            w.writeheader()
            w.writerows(raw_rows)
        summary_path = ns.csv.with_name(
            ns.csv.stem + "_summary" + ns.csv.suffix)
        with summary_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary_rows[0]))
            w.writeheader()
            w.writerows(summary_rows)
        print(f"\nraw samples: {ns.csv}\nsummary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
