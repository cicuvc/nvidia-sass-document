#!/usr/bin/env python3
"""Phase 5 differential harness: same compute kernel on GPU (RTX 5090,
sm_120) and in the semu interpreter, compared word-by-word.

Strategy (the interpreter has no memory until Phase 6):
  * GPU side: kernel bakes inputs as MOV32I immediates, computes, and STG.E
    stores the result registers to global memory; the cubin runs on the GPU
    via CudaModule and the stored words are read back.
  * semu side: the identical compute instruction stream (STG/prologue lines
    stripped, same register allocation) runs in the interpreter via the
    `semu run` CLI, which dumps the final per-lane GPR state as JSON.
  * Comparison: for each stored result register and each lane, GPU STG value
    vs semu GPR value.  All must match bit-for-bit.

Usage: python3 tools/diff_phase5.py [--keep] [-j N]
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import assemble, CudaModule

SEMU = str(Path(__file__).resolve().parents[1] / "semu" / "build" / "cli" / "semu")

# ---------------------------------------------------------------------------
# Case library: each entry is a (label, body_lines) tuple.  `body_lines` is
# the compute-only SASS; the harness derives the GPU variant by prepending
# the STG prologue and appending one STG per listed result register.
# ---------------------------------------------------------------------------

# MOV32I convenience: value as hex, lane-invariant.
def mov(reg, val):
    return f"    MOV32I {reg}, 0x{val & 0xFFFFFFFF:08X};[7:7:{{0}}:5:1]"


def fpu32(label, body, results, block=(1, 1, 1), grid=(1, 1, 1)):
    return {"label": label, "body": body, "results": results,
            "block": block, "grid": grid}


def make_cases():
    cases = []

    # ---- FFMA / FADD / FMUL: rounding + FTZ/FMZ/SAT ----------------------
    ffma_cases = []
    for a, b, c in [(0x3F800000, 0x40000000, 0x3F000000),   # 1.0*2.0+0.5
                    (0x3F800000, 0x3F800000, 0x3F800000),   # 1.0*1.0+1.0
                    (0xBF800000, 0x3F800000, 0x3F800000),   # -1*1+1
                    (0x7F800000, 0x3F800000, 0x3F000000),   # inf*1+0.5
                    (0x7FC00000, 0x3F800000, 0x3F000000),   # nan*1+0.5
                    (0x3F800000, 0x7F800000, 0x3F000000),   # 1*inf+0.5
                    ]:
        for mod in ("", ".RM", ".RP", ".RZ"):
            lines = [mov("R0", a), mov("R1", b), mov("R2", c),
                     f"    FFMA{mod} R3, R0, R1, R2;[7:7:{{0}}:8:1]"]
            cases.append(fpu32(f"FFMA{mod}-{a:x}_{b:x}", lines, ["R3"]))
    for a, b in [(0x00000001, 0x3F800000),   # denormal + 1.0
                 (0x00000001, 0x80000001),   # denormal + -denormal
                 ]:
        for mod in ("", ".FTZ"):
            lines = [mov("R0", a), mov("R1", b),
                     f"    FADD{mod} R3, R0, R1;[7:7:{{0}}:8:1]"]
            cases.append(fpu32(f"FADD{mod}-{a:x}_{b:x}", lines, ["R3"]))

    # ---- .SAT special values (NaN/±inf/negative/>1/±0/0.5/1) -------------
    # Verified sm120: SAT clamps to [0,1]; NaN -> +0, +inf -> 1.0,
    # -inf/-1 -> +0, >1 -> 1.0, 0.5/1.0 pass through.
    for op in ("FADD", "FMUL", "FFMA"):
        sat_vals = [
            (0x7FC00000, 0x00000000), (0xFFC00000, 0x00000000),
            (0x7F800000, 0x00000000), (0xFF800000, 0x00000000),
            (0xBF800000, 0x00000000), (0x3F000000, 0x00000000),
            (0x3F800000, 0x00000000), (0x3F800001, 0x00000000),
            (0x40000000, 0x00000000), (0x80000000, 0x00000000),
        ]
        for a, b in sat_vals:
            if op == "FFMA":
                lines = [mov("R0", a), mov("R1", b), mov("R2", 0x00000000),
                         f"    FFMA.SAT R3, R0, R1, R2;[7:7:{{0}}:8:1]"]
            else:
                lines = [mov("R0", a), mov("R1", b),
                         f"    {op}.SAT R3, R0, R1;[7:7:{{0}}:8:1]"]
            cases.append(fpu32(f"{op}.SAT-{a:x}-{b:x}", lines, ["R3"]))
    # inf + -inf -> NaN under SAT (clamps to +0).
    for op in ("FADD", "FFMA"):
        if op == "FFMA":
            lines = [mov("R0", 0x7F800000), mov("R1", 0xFF800000),
                     mov("R2", 0x00000000),
                     f"    FFMA.SAT R3, R0, R1, R2;[7:7:{{0}}:8:1]"]
        else:
            lines = [mov("R0", 0x7F800000), mov("R1", 0xFF800000),
                     f"    FADD.SAT R3, R0, R1;[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"{op}.SAT-inf-ninf", lines, ["R3"]))

    # ---- FP64 add/mul/fma ------------------------------------------------
    for a, b, c in [(0x3FF0000000000000, 0x4000000000000000,
                     0x3FE0000000000000),  # 1.0*2.0+0.5
                    (0xBFF0000000000000, 0x3FF0000000000000,
                     0x3FF0000000000000),  # -1*1+1
                    (0x7FF0000000000000, 0x3FF0000000000000,
                     0x3FE0000000000000),  # inf*1+0.5
                    ]:
        lines = [f"    MOV R0, 0x{ (a & 0xFFFFFFFF):08X};[7:7:{{0}}:5:1]",
                 f"    MOV R1, 0x{(a >> 32):08X};[7:7:{{0}}:5:1]",
                 f"    MOV R2, 0x{ (b & 0xFFFFFFFF):08X};[7:7:{{0}}:5:1]",
                 f"    MOV R3, 0x{(b >> 32):08X};[7:7:{{0}}:5:1]",
                 f"    MOV R4, 0x{ (c & 0xFFFFFFFF):08X};[7:7:{{0}}:5:1]",
                 f"    MOV R5, 0x{(c >> 32):08X};[7:7:{{0}}:5:1]",
                 "    DMUL {R6,R7}, {R0,R1}, {R2,R3};[2:7:{0}:8:1]",
                 "    DADD {R8,R9}, {R6,R7}, {R4,R5};[2:7:{0,2}:8:1]"]
        cases.append(fpu32(f"DMUL-DADD-{a:x}", lines, ["R6", "R7", "R8", "R9"]))

    # ---- FP64 conversions + DFMA ------------------------------------------
    # I2F.F64.S32 / F2F.F64.F32 / F2F.F32.F64 and DFMA with a rounding-tie.
    f64conv = [
        (0x00000005, "I2F.F64.S32"),      # 5 -> 5.0
        (0x80000000, "I2F.F64.S32"),      # INT32_MIN
        (0x3F800000, "F2F.F64.F32"),      # 1.0
        (0x7F800000, "F2F.F64.F32"),      # inf
        (0x3DCCCCCD, "F2F.F64.F32"),      # 0.1
    ]
    for val, fmt in f64conv:
        lines = [mov("R0", val),
                 f"    {fmt} {{R6,R7}}, R0;[2:7:{{0}}:8:1]"]
        cases.append(fpu32(f"{fmt}-{val:x}", lines, ["R6", "R7"]))
    # F2F.F32.F64 downconvert (source is the 64-bit pair {R0,R1}).
    for lo, hi, tag in ((0x00000000, 0x3FF00000, "one"),      # 1.0
                        (0x00000000, 0x40080000, "three"),    # 3.0
                        (0x00000000, 0x7FF00000, "inf")):
        lines = [f"    MOV R0, 0x{lo:08X};[7:7:{{0}}:5:1]",
                 f"    MOV R1, 0x{hi:08X};[7:7:{{0}}:5:1]",
                 f"    F2F.F32.F64 R3, {{R0,R1}};[2:7:{{0}}:8:1]"]
        cases.append(fpu32(f"F2F.F32.F64-{tag}", lines, ["R3"]))

    # F64 -> F16/F32/BF16 DIRECT downconversion (no FP32 intermediate), across
    # double-rounding traps, directed rounding, NaN payloads, subnormals and
    # overflow.  Source is the 64-bit pair {R0,R1}; the F16/BF16 result is in
    # bits [15:0].
    f64_down = [
        # (lo, hi, tag) — double-rounding trap values where an FP32
        # intermediate would round differently than direct F64 rounding.
        (0x00080000, 0x3FF00200, "dr1"), (0x00040000, 0x3FF00200, "dr2"),
        (0x00001000, 0x3FF00200, "dr3"), (0x00008000, 0x3FE00200, "dr0.5"),
        (0x00000000, 0x3FF00000, "one"), (0x00000000, 0x40000000, "two"),
        (0x00000000, 0x3FE00000, "half"),
        (0x00000000, 0x7FF00000, "inf"), (0x00000000, 0xFFF00000, "ninf"),
        (0x00000000, 0x7FF80000, "nan"), (0x00000001, 0x7FF00000, "nan2"),
        (0x00000000, 0x00000000, "zero"), (0x00000000, 0x80000000, "nzero"),
        (0x00000000, 0x3F000000, "2^-8"), (0xFFFFFFFF, 0x3E7FFFFF, "b2^-7"),
        (0x00000000, 0x38000000, "2^-127"), (0x00000001, 0x38000000, "2^-127+"),
        (0x00000000, 0x43400000, "2^56"), (0x00000000, 0x47EFFFE0, "f32max"),
        (0x00000001, 0x47EFFFE0, "f32max+"), (0xFFFFFFFF, 0x7FEFFFFF, "f64max"),
    ]
    for lo, hi, tag in f64_down:
        for fmt, rnd in (("F16.F64", ""), ("F16.F64", ".RM"),
                         ("F16.F64", ".RP"), ("F16.F64", ".RZ"),
                         ("F32.F64", ""), ("F32.F64", ".RM"),
                         ("F32.F64", ".RP"), ("F32.F64", ".RZ"),
                         ("BF16.F64", ""), ("BF16.F64", ".RM"),
                         ("BF16.F64", ".RP"), ("BF16.F64", ".RZ")):
            lines = [f"    MOV R0, 0x{lo:08X};[7:7:{{0}}:5:1]",
                     f"    MOV R1, 0x{hi:08X};[7:7:{{0}}:5:1]",
                     f"    F2F.{fmt}{rnd} R3, {{R0,R1}};[2:7:{{0}}:8:1]"]
            cases.append(fpu32(f"F2F.{fmt}{rnd}-{tag}-{lo:x}-{hi:x}", lines,
                               ["R3"]))

    # DFMA: fused FP64 a*b+c with a rounding tie (1.0*1.0 + 2^-53).
    lines = [f"    MOV R0, 0x00000000;[7:7:{{0}}:5:1]",
             f"    MOV R1, 0x3FF00000;[7:7:{{0}}:5:1]",  # 1.0
             f"    MOV R2, 0x00000000;[7:7:{{0}}:5:1]",
             f"    MOV R3, 0x3FF00000;[7:7:{{0}}:5:1]",  # 1.0
             f"    MOV R4, 0x00000000;[7:7:{{0}}:5:1]",
             f"    MOV R5, 0x3CA00000;[7:7:{{0}}:5:1]",  # 2^-53
             "    DFMA {R6,R7}, {R0,R1}, {R2,R3}, {R4,R5};[2:7:{0}:8:1]"]
    cases.append(fpu32("DFMA-tie", lines, ["R6", "R7"]))
    # DFMA rounding boundary: (1+2^-52) * 1.0 + 2^-53, each mode.
    for mod, tag in (("", "RN"), (".RM", "RM"), (".RP", "RP"), (".RZ", "RZ")):
        lines = [f"    MOV R0, 0x00000000;[7:7:{{0}}:5:1]",
                 f"    MOV R1, 0x3FF00000;[7:7:{{0}}:5:1]",  # 1.0
                 f"    MOV R2, 0x00000001;[7:7:{{0}}:5:1]",
                 f"    MOV R3, 0x3FF00000;[7:7:{{0}}:5:1]",  # 1+2^-52
                 f"    MOV R4, 0x00000000;[7:7:{{0}}:5:1]",
                 f"    MOV R5, 0x3CA00000;[7:7:{{0}}:5:1]",  # 2^-53
                 f"    DFMA{mod} {{R6,R7}}, {{R0,R1}}, {{R2,R3}}, {{R4,R5}};[2:7:{{0}}:8:1]"]
        cases.append(fpu32(f"DFMA-{tag}", lines, ["R6", "R7"]))

    # ---- conversions ------------------------------------------------------
    # F2F.F32.F16 / F2F.F16.F32
    f2f_cases = [
        (0x3F800000, "F32.F16"),   # 1.0
        (0x40200000, "F32.F16"),   # 2.5
        (0x7F800000, "F32.F16"),   # inf
        (0x3DCCCCCD, "F32.F16"),   # 0.1
    ]
    for val, fmt in f2f_cases:
        lines = [mov("R0", val), f"    F2F.{fmt} R3, R0;[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"F2F-{fmt}-{val:x}", lines, ["R3"]))
    for half in (0x3C00, 0x4000, 0x0000, 0x7C00):   # 1.0, 2.0, 0, inf
        lines = [mov("R0", half), f"    F2F.F32.F16 R3, R0;[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"F2F-F32.F16-{half:x}", lines, ["R3"]))

    # I2F.F32.U32 / F2I (register-source forms; the 64-bit variants write a
    # register pair, so probe the 32-bit RRR forms).
    for val in (0, 1, 0x7FFFFFFF, 0xFFFFFFFF, 0x1000000):
        lines = [mov("R0", val),
                 f"    I2F.F32.U32 R3, R0;[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"I2F.U32-{val:x}", lines, ["R3"]))
    for val in (0x3F800000, 0x40000000, 0xBF800000, 0x7F800000, 0):
        lines = [mov("R0", val),
                 f"    F2I.S32.F32.TRUNC R3, R0;[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"F2I-{val:x}", lines, ["R3"]))

    # ---- compares / min-max / select -------------------------------------
    fsetp_ops = ["LT", "EQ", "LE", "GT", "NE", "GE", "NUM", "NAN"]
    for op in fsetp_ops:
        lines = [mov("R0", 0x3F800000), mov("R1", 0x3F800000),  # 1.0, 1.0
                 f"    FSETP.{op}.AND P0, P1, R0, R1, PT;[7:7:{{0}}:8:1]",
                 "    P2R R3, PR, RZ, 0x1;[7:7:{0}:8:1]"]
        cases.append(fpu32(f"FSETP.{op}", lines, ["R3"]))

    # FMNMX (min/max with NaN)
    for pp, label in [("PT", "MIN"), ("!PT", "MAX")]:
        lines = [mov("R0", 0x3F800000), mov("R1", 0x40000000),
                 f"    FMNMX R3, R0, R1, {pp};[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"FMNMX-{label}", lines, ["R3"]))
    lines = [mov("R0", 0x7FC00000), mov("R1", 0x3F800000),
             "    FMNMX.NAN R3, R0, R1, PT;[7:7:{0}:8:1]"]
    cases.append(fpu32("FMNMX.NAN", lines, ["R3"]))

    # FSEL
    lines = [mov("R0", 0x3F800000), mov("R1", 0x40000000),
             "    ISETP.GT.U32.AND P0, PT, R0, R1, PT;[7:7:{0}:8:1]",
             "    FSEL R3, R0, R1, P0;[7:7:{0}:8:1]"]
    cases.append(fpu32("FSEL", lines, ["R3"]))

    # ---- integer / bit ----------------------------------------------------
    int_cases = [
        ("IADD3", ["IADD3 R3, R0, R1, R2;[7:7:{0}:8:1]"],
         [0x00000001, 0x00000002, 0x00000003]),
        ("IADD3-neg", ["IADD3 R3, -R0, R1, R2;[7:7:{0}:8:1]"],
         [0x00000001, 0x00000002, 0x00000003]),
        ("LOP3.AND", ["LOP3 R3, R0, R1, R2, 0x80;[7:7:{0}:8:1]"],
         [0x0F0F0F0F, 0x00FF00FF, 0x00000000]),
        ("LOP3.XOR", ["LOP3 R3, R0, R1, R2, 0x96;[7:7:{0}:8:1]"],
         [0x0F0F0F0F, 0x00FF00FF, 0x00000000]),
        ("LOP3.LUT", ["LOP3 R3, R0, R1, RZ, 0xC0;[7:7:{0}:8:1]"],
         [0x0F0F0F0F, 0x00FF00FF, 0x00000000]),
        ("SHF.L", ["SHF.L.U32 R3, R0, R1, RZ;[7:7:{0}:8:1]"],
         [0x00000001, 0x00000004, 0x00000000]),
        ("SHF.R", ["SHF.R.U32 R3, R0, R1, RZ;[7:7:{0}:8:1]"],
         [0x80000000, 0x00000004, 0x00000000]),
        ("IABS", ["IABS R3, R0;[7:7:{0}:8:1]"], [0x80000001, 0, 0]),
        ("POPC", ["POPC R3, R0;[7:7:{0}:8:1]"], [0x0F0F0F0F, 0, 0]),
        ("PRMT", ["PRMT R3, R0, R1, R2;[7:7:{0}:8:1]"],
         [0x00010203, 0x00010203, 0x00000000]),
        ("IMNMX", ["IMNMX R3, R0, R1, PT;[7:7:{0}:8:1]"],
         [0x80000001, 0x00000002, 0x00000000]),
    ]
    for label, inst, vals in int_cases:
        lines = []
        for i, v in enumerate(vals):
            lines.append(mov(f"R{i}", v))
        lines += inst
        cases.append(fpu32(f"INT-{label}", lines, ["R3"]))

    # IMAD.WIDE / IMAD.HI (64-bit multiply-add, large products)
    # 0x12345678 * 0x9ABCDEF0 = 0x0B2A_..._;  a large 64-bit addend.
    imad_cases = [
        # (ra, rb, rc_lo, rc_hi, op)
        (0x00000001, 0x00000002, 0x00000005, 0x00000000, "IMAD.WIDE"),
        (0x12345678, 0x9ABCDEF0, 0x00000005, 0x00000000, "IMAD.WIDE"),
        (0xFFFFFFFF, 0xFFFFFFFF, 0x00000005, 0x00000000, "IMAD.WIDE"),
        (0x7FFFFFFF, 0x80000000, 0x11111111, 0x22222222, "IMAD.WIDE"),
        (0x12345678, 0x9ABCDEF0, 0x00000005, 0x00000000, "IMAD.HI"),
        (0xFFFFFFFF, 0xFFFFFFFF, 0x00000005, 0x00000000, "IMAD.HI"),
        (0x7FFFFFFF, 0x80000000, 0x00000000, 0x00000000, "IMAD.HI"),
        # High-1 regression vectors: a full 64-bit addend whose LOW half has
        # bit31 set must NOT re-sign-extend away the high half
        # (c = 0x00000000ffffffff must stay that, not become -1).
        (0x00000002, 0x00000003, 0xFFFFFFFF, 0x00000000, "IMAD.WIDE"),
        (0x00000002, 0x00000003, 0xFFFFFFFF, 0xFFFFFFFF, "IMAD.WIDE"),
        (0x00000002, 0x00000003, 0xFFFFFFFF, 0x00000000, "IMAD.HI"),
        # Large-addend wraparound: product + addend overflows 2^64 modularly.
        (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, "IMAD.WIDE"),
        (0xFFFFFFFF, 0xFFFFFFFF, 0x00000000, 0x80000000, "IMAD.HI"),
        # Signed product where low-half sign bit differs from the real sign.
        (0x80000000, 0x80000000, 0x00000000, 0x00000000, "IMAD.WIDE"),
        (0x80000000, 0x00000001, 0x00000000, 0x00000000, "IMAD.HI"),
    ]
    for a, b, clo, chi, op in imad_cases:
        lines = [mov("R0", a), mov("R2", b), mov("R4", clo), mov("R5", chi)]
        if op == "IMAD.WIDE":
            lines.append(
                f"    IMAD.WIDE {{R6,R7}}, R0, R2, {{R4,R5}};[1:7:{{0}}:8:1]")
            res = ["R6", "R7"]
        else:
            lines.append(
                f"    IMAD.HI R6, R0, R2, {{R4,R5}};[1:7:{{0}}:8:1]")
            res = ["R6"]
        cases.append(fpu32(f"{op}-{a:x}x{b:x}", lines, res))

    # BMSK / LEA / P2R / PRMT variants.
    bmsk_cases = [(0x00000000, 0x0000001F),   # mask [0,31]
                  (0xFFFFFFFF, 0x000003FF),   # mask [31,31]
                  (0x00000005, 0x00000008),   # mask [8,0]
                  (0x00000008, 0x00000000)]   # mask [0,8] inverted wrap
    for a, b in bmsk_cases:
        lines = [mov("R0", a), mov("R1", b),
                 "    BMSK R3, R0, R1;[7:7:{0}:8:1]"]
        cases.append(fpu32(f"BMSK-{a:x}-{b:x}", lines, ["R3"]))
    for a, b, sh in ((0x00000001, 0x00000002, 0x00000001),
                     (0x10000000, 0x00000004, 0x00000000)):
        lines = [mov("R0", a), mov("R1", b),
                 f"    LEA R3, PT, R0, R1, 0x{sh:x};[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"LEA-{a:x}-{b:x}-{sh:x}", lines, ["R3"]))
    # P2R byte-select variants: P0 set by ISETP; read P0 at byte 0/1/2/3.
    for bsel, tag in (("B0", "b0"), ("B1", "b1"), ("B2", "b2"), ("B3", "b3")):
        lines = [mov("R0", 0x00000005), mov("R1", 0x0000000A),
                 "    ISETP.LT.U32.AND P0, PT, R0, R1, PT;[7:7:{0}:13:1]",
                 f"    P2R.{bsel} R3, PR, RZ, 0x1;[7:7:{{0}}:8:1]"]
        cases.append(fpu32(f"P2R-{tag}", lines, ["R3"]))

    # ---- FP16 subnormal directed rounding --------------------------------
    # Boundaries around 2^-14 (smallest normal f16) and 2^-24 (subnormal
    # unit) across all four rounding modes and both signs.
    f16_edge = [0x33800000, 0x337FFFFF, 0x33800001, 0x39800000,
                0x39000000, 0x38FFFFFF, 0x387FFFFF, 0x38000001,
                0x33FF0000, 0x33FFFF00]
    for v in f16_edge:
        for s in (0, 0x80000000):
            for rnd in ("RN", "RM", "RP", "RZ"):
                lines = [mov("R0", v | s),
                         f"    F2F.F16.F32.{rnd} R3, R0;[2:7:{{0}}:8:1]"]
                cases.append(fpu32(f"F16SUB-{v|s:x}-{rnd}", lines, ["R3"]))

    # ---- MUFU / FCHK runtime faults ---------------------------------------
    # These are hardware-table instructions not modeled in Phase 5; the
    # interpreter must fault with UnsupportedInstruction at the right PC and
    # word.  (semu side checked separately; the GPU side is not run because
    # MUFU/FCHK DO execute on real silicon.)

    # ---- collectives ------------------------------------------------------
    # VOTE.ANY/ALL/EQ with lanes holding distinct values; result bitmask in
    # Rd, result predicate in Pu.  Read predicates back via P2R.  Use the
    # register-register ISETP pattern (test_vote.py) — reg-vs-immediate
    # ISETP.GT produced all-true on this GPU, so keep both operands regs.
    vote_body = [
        "    S2R R0, SR_TID.X;[0:7:{0}:5:1]",
        "    MOV32I R1, 0x10;[7:7:{0}:5:1]",
        "    ISETP.GT.U32.AND P0, PT, R0, R1, PT;[7:7:{0}:13:1]",  # lanes>16
        "    VOTE.ANY R2, P1, P0;[7:7:{0}:5:1]",
        "    VOTE.ALL R3, P2, P0;[7:7:{0}:5:1]",
        "    VOTE.EQ R4, P3, P0;[7:7:{0}:5:1]",
        "    P2R R5, PR, RZ, 0x1;[7:7:{0}:8:1]",   # read P0 (input mask)
    ]
    cases.append(fpu32("VOTE", vote_body, ["R2", "R3", "R4", "R5"],
                       block=(32, 1, 1)))

    # SHFL.IDX / UP / DOWN / BFLY with lanes carrying their TID.  Use a
    # register segment R4=0 (RZ as segment returns the lane's own value on
    # this GPU, which is a different op).
    # SHFL.IDX / UP / DOWN / BFLY.  IDX uses index=2 via register R4 and
    # bound R4 (matching test_shfl: source lane = bound for IDX); UP/DOWN/
    # BFLY use immediate delta=2 with bound 0x1f/0x0 (Rc register).
    shfl_cases = [
        ("IDX", ["    MOV32I R4, 0x2;[7:7:{0}:5:1]",
                 "    SHFL.IDX P0, R3, R0, R4, R4;[2:7:{0}:8:1]"]),
        ("UP", ["    SHFL.UP P0, R3, R0, 0x2, RZ;[2:7:{0}:8:1]"]),
        ("DOWN", ["    MOV32I R4, 0x1f;[7:7:{0}:5:1]",
                  "    SHFL.DOWN P0, R3, R0, 0x2, R4;[2:7:{0}:8:1]"]),
        ("BFLY", ["    MOV32I R4, 0x1f;[7:7:{0}:5:1]",
                  "    SHFL.BFLY P0, R3, R0, 0x2, R4;[2:7:{0}:8:1]"]),
    ]
    for mode, lines in shfl_cases:
        body = ["    S2R R0, SR_TID.X;[0:7:{0}:5:1]"] + lines
        cases.append(fpu32(f"SHFL.{mode}", body, ["R3"], block=(32, 1, 1)))

    # ELECT: leader lane.
    elect_body = [
        "    S2R R0, SR_TID.X;[7:7:{0}:5:1]",
        "    ISETP.LT.U32.AND P0, PT, R0, 0x8, PT;[7:7:{0}:8:1]",  # lanes<8
        "    ELECT P1, UR4, P0;[7:7:{0}:5:1]",
        "    MOV R5, UR4;[7:7:{0}:5:1]",
    ]
    cases.append(fpu32("ELECT", elect_body, ["R5"], block=(32, 1, 1)))

    # REDUX.ADD/OR
    redux_body = [
        "    S2R R0, SR_TID.X;[0:7:{0}:5:1]",
        "    REDUX.SUM.U32 UR4, R0;[2:7:{0}:8:1]",
        "    MOV R5, UR4;[7:7:{0,2}:5:1]",
    ]
    cases.append(fpu32("REDUX.ADD", redux_body, ["R5"], block=(32, 1, 1)))

    return cases


def build_gpu_kernel(case, name):
    """Build the GPU variant: prologue + body + one STG per result reg."""
    nlen = max(1, len(case["results"]) * 4)  # per-lane byte stride
    pro = [
        "#fn " + name + "(out<8>) {",
        "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R22, R23}, #param(out);[0:7:{}:1:0]",
        "    S2R R30, SR_TID.X;[0:7:{0}:5:1]",
        # Per-lane store base: R28:R29 = out + lane * nres * 4.  R30 is the
        # lane id; R28/R29 are the per-lane address (high regs avoid any
        # collision with the compute body's R0..R9 and result registers).
        f"    IMAD.WIDE {{R28,R29}}, R30, 0x{nlen:04X}, {{R22,R23}};[0:7:{{0}}:8:1]",
    ]
    body = case["body"]
    # After the compute body, pad with NOPs so high-latency pipes (FP64,
    # mio conversions, collectives) settle before the STG reads them.
    nops = ["    NOP;[7:7:{}:1:1]"] * 24
    stgs = []
    for i, reg in enumerate(case["results"]):
        # Read the result register directly (no intermediate MOV: reading
        # through MOV captures a stale value while the pipe is still in
        # flight); req {0} covers the base-address LDCU SB0 + LDC SB1.
        stgs.append(
            f"    STG.E desc[{{UR4,UR5}}][{{R28,R29}}+0x{i*4:X}], {reg};"
            f"[0:1:{{0,1,2}}:1:0]")
    tail = ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(pro + body + nops + stgs + tail)


def build_semu_kernel(case, name):
    """Build the semu variant: just the body (no prologue/STG)."""
    body = ["#fn " + name + "(dummy<4>) {"] + case["body"] + \
           ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(body)


def mangle(name):
    return f"_Z{len(name)}{name}"


def run_gpu(cubin_bytes, kernel, block, grid, nlanes, nres, mod=None):
    """Run a case on the GPU.  `mod` (optional) is a prebuilt CudaModule so
    all cases share one driver context (repeated fresh-process CUDA inits on
    this RTX 5090 driver intermittently fault with ILLEGAL_ADDRESS)."""
    if mod is None:
        mod = CudaModule(cubin_bytes)
    d = mod.devmem_alloc(nlanes * nres * 4 + 64)
    try:
        mod.launch(kernel, grid=tuple(grid), block=tuple(block), args=[d])
        mod.synchronize()
        return mod.device_read(d, nlanes * nres * 4)
    finally:
        mod.devmem_free(d)


def run_semu(cubin_bytes, kernel, block, grid):
    p = subprocess.run(
        [SEMU, "run", "/tmp/diff_semu.cubin", kernel,
         str(grid[0]), str(block[0]), str(grid[1]), str(block[1]),
         str(grid[2]), str(block[2])],
        capture_output=True, text=True)
    if p.returncode != 0:
        return None, p.stderr.strip()
    return json.loads(p.stdout), None


def run_semu_fault(body_lines, mnemonic):
    """Run a body that must fault at runtime (MUFU/FCHK).  Returns the fault
    JSON dict on success, or None on failure (wrong/no fault)."""
    sname = "fault_k"
    scubin = assemble(build_semu_kernel({"body": body_lines}, sname),
                      kernel_name=sname, check_deps=False)
    Path("/tmp/diff_semu.cubin").write_bytes(scubin)
    p = subprocess.run(
        [SEMU, "run", "/tmp/diff_semu.cubin", mangle(sname),
         "1", "1", "1", "1", "1", "1"],
        capture_output=True, text=True)
    if p.returncode != 0:
        try:
            return json.loads(p.stdout)
        except Exception:
            return None
    return None


def check_runtime_fault(fail_detail):
    """MUFU and FCHK must fault as kUnsupportedInstruction with the right
    PC/word/mnemonic.  Returns the number of passed checks."""
    checks = 0
    ok = True
    # MUFU.RCP R0, R0
    f = run_semu_fault(["    MUFU.RCP R0, R0;[7:7:{0}:8:1]"], "MUFU")
    if f is None or "fault" not in f:
        ok = False
        fail_detail.append("MUFU: expected a runtime fault, none reported")
    else:
        fl = f["fault"]
        checks += 1
        if fl.get("kind") != 1:
            ok = False
            fail_detail.append(f"MUFU: expected UnsupportedInstruction, got "
                               f"kind {fl.get('kind')}")
        if fl.get("pc") != 0:
            ok = False
            fail_detail.append(f"MUFU: expected pc 0, got {fl.get('pc')}")
        if "MUFU" not in fl.get("message", ""):
            ok = False
            fail_detail.append(f"MUFU: message missing mnemonic: "
                               f"{fl.get('message')}")
    # FCHK.DIVIDE P0, R0, R1
    f = run_semu_fault(["    FCHK.DIVIDE P0, R0, R1;[7:7:{0}:8:1]"], "FCHK")
    if f is None or "fault" not in f:
        ok = False
        fail_detail.append("FCHK: expected a runtime fault, none reported")
    else:
        fl = f["fault"]
        checks += 1
        if fl.get("kind") != 1:
            ok = False
            fail_detail.append(f"FCHK: expected UnsupportedInstruction, got "
                               f"kind {fl.get('kind')}")
        if fl.get("pc") != 0:
            ok = False
            fail_detail.append(f"FCHK: expected pc 0, got {fl.get('pc')}")
        if "FCHK" not in fl.get("message", ""):
            ok = False
            fail_detail.append(f"FCHK: message missing mnemonic: "
                               f"{fl.get('message')}")
    # IMAD.X / IMAD.WIDE.X / IMAD.HI.X: the carry-in/out forms are not
    # implemented; they must fault rather than silently drop the carry.
    for body, tag in ((["    IMAD.X R3, R0, R1, R2, P0;[7:7:{0}:8:1]"], "IMAD.X"),
                      (["    IMAD.WIDE.X {R4,R5}, PT, R0, R1, {R2,R3}, P0;[7:7:{0}:8:1]"],
                       "IMAD.WIDE.X")):
        f = run_semu_fault(body, tag)
        if f is None or "fault" not in f:
            ok = False
            fail_detail.append(f"{tag}: expected a runtime fault, none reported")
        else:
            fl = f["fault"]
            checks += 1
            if fl.get("kind") != 1:
                ok = False
                fail_detail.append(f"{tag}: expected UnsupportedInstruction, "
                                   f"got kind {fl.get('kind')}")
            if "IMAD" not in fl.get("message", ""):
                ok = False
                fail_detail.append(f"{tag}: message missing mnemonic: "
                                   f"{fl.get('message')}")
    if ok:
        print("PASS runtime-fault MUFU+FCHK+IMAD.X")
    return checks if ok else 0


def main():
    import struct
    keep = "--keep" in sys.argv
    cases = make_cases()
    passed = 0
    failed = 0
    fail_detail = []
    shared_gpu = None
    for ci, case in enumerate(cases):
        label = case["label"]
        gname = f"k_{ci:03d}_g"
        sname = f"k_{ci:03d}_s"
        try:
            gcubin = assemble(build_gpu_kernel(case, gname), kernel_name=gname,
                              check_deps=False)
            scubin = assemble(build_semu_kernel(case, sname), kernel_name=sname,
                              check_deps=False)
            gkern = mangle(gname)
            skern = mangle(sname)
        except Exception as e:
            failed += 1
            fail_detail.append(f"{label}: assemble error {type(e).__name__}: {e}")
            continue
        Path("/tmp/diff_gpu.cubin").write_bytes(gcubin)
        Path("/tmp/diff_semu.cubin").write_bytes(scubin)
        # GPU run (shared context across cases: reusing one process-global
        # CUDA context avoids the RTX 5090 driver's intermittent fault on
        # repeated fresh-process context teardown).
        nlanes = case["block"][0] * case["block"][1] * case["block"][2]
        nres = len(case["results"])
        try:
            if shared_gpu is None:
                shared_gpu = CudaModule(gcubin)
            else:
                shared_gpu = CudaModule(gcubin)  # reload per case; same ctx
            gpuvals = run_gpu(gcubin, gkern, case["block"], case["grid"],
                              nlanes, nres, shared_gpu)
        except Exception as e:
            failed += 1
            fail_detail.append(f"{label}: GPU error {type(e).__name__}: {e}")
            continue
        # semu run
        sres, serr = run_semu(scubin, skern, case["block"], case["grid"])
        if sres is None:
            failed += 1
            fail_detail.append(f"{label}: semu error {serr}")
            continue
        if "fault" in sres:
            failed += 1
            fail_detail.append(f"{label}: semu fault {sres['fault']}")
            continue
        # Compare per result register per lane: GPU stores lane L result i at
        # byte offset (L * nres + i) * 4.  semu dumps per-lane GPRs.
        ok = True
        for i, reg in enumerate(case["results"]):
            for lane in range(nlanes):
                gpu_word = struct.unpack_from("<I", gpuvals,
                                              (lane * nres + i) * 4)[0]
                cta = sres["ctas"][0]
                warp = cta["warps"][0]
                lane_idx = lane % 32
                semu_word = warp["lanes"][lane_idx]["gpr"][int(reg[1:])]
                if gpu_word != semu_word:
                    ok = False
                    fail_detail.append(
                        f"{label}: {reg}[lane{lane}] gpu=0x{gpu_word:08X} "
                        f"semu=0x{semu_word:08X}")
        if ok:
            passed += 1
            print(f"PASS {label}")
        else:
            failed += 1
            print(f"FAIL {label}")
    # Runtime-fault checks (MUFU/FCHK fault on the interpreter; they execute
    # on real silicon so there is no GPU comparison — the fault is the gate).
    passed += check_runtime_fault(fail_detail)
    print(f"\n=== {passed} passed, {failed} failed, "
          f"{len(cases)} differential + 2 fault checks ===")
    for d in fail_detail[:60]:
        print("  " + d)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
