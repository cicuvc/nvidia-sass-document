#!/usr/bin/env python3
"""Phase 5 random-operand fuzz: identical compute kernels on the GPU
(RTX 5090, sm_120) and in the semu interpreter, compared word-by-word over
random FP/int operand values.

Covers the core FP (FADD/FMUL/FFMA with all rounding/flush/SAT modifiers),
conversions (F2F/F2I/I2F), compares (FSETP), min/max (FMNMX), and integer
(IMAD/IADD3/LOP3/SHF) semantics with random bit patterns including
denormals, +/-0, subnormals, NaN and Inf.

Usage: python3 tools/fuzz_phase5.py [-n 200] [--seed 42] [--gpu]
  --gpu runs the GPU comparison; without it, semu results are checked
  against a host IEEE reference (fast, no CUDA needed).
"""

import json
import math
import os
import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import assemble, CudaModule

SEMU = os.environ.get("SEMU_BIN", str(Path(__file__).resolve().parents[1] /
                                       "semu" / "build" / "cli" / "semu"))

# ---------------------------------------------------------------------------
# Random operand generation
# ---------------------------------------------------------------------------

def rand_u32(rng):
    return rng.getrandbits(32)


def rand_f32_bits(rng):
    """Random float32 bits with emphasis on special/edge values."""
    r = rng.random()
    if r < 0.08:
        return rng.choice([0x00000000, 0x80000000,          # +/-0
                           0x7F800000, 0xFF800000,          # +/-inf
                           0x7FC00000, 0xFFC00000, 0x7FFFFFFF,  # NaN
                           0x00000001, 0x80000001,          # denormal
                           0x007FFFFF, 0x807FFFFF,          # max denormal
                           0x3F800000, 0xBF800000])         # +/-1
    if r < 0.25:
        # subnormal region
        return rng.getrandbits(23) | (rng.getrandbits(1) << 31)
    if r < 0.5:
        # exponent near boundaries
        exp = rng.choice([0x01, 0xFE, 0x7F, 0x80, 0x7E, 0x7D])
        return (exp << 23) | rng.getrandbits(23) | (rng.getrandbits(1) << 31)
    return rng.getrandbits(32)


def rand_f64_bits(rng):
    r = rng.random()
    if r < 0.1:
        return rng.choice([0, 0x8000000000000000,
                           0x7FF0000000000000, 0xFFF0000000000000,
                           0x7FF8000000000000,
                           0x3FF0000000000000, 0xBFF0000000000000,
                           0x0000000000000001, 0x000FFFFFFFFFFFFF])
    if r < 0.3:
        return rng.getrandbits(52) | (rng.getrandbits(1) << 63)
    return rng.getrandbits(64)


def bits_to_f32(b):
    return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]


def bits_to_f64(b):
    return struct.unpack("<d", struct.pack("<Q", b & 0xFFFFFFFFFFFFFFFF))[0]


def f32_to_bits(f):
    return struct.unpack("<I", struct.pack("<f", f))[0]


def f64_to_bits(f):
    return struct.unpack("<Q", struct.pack("<d", f))[0]


# ---------------------------------------------------------------------------
# Independent host reference (numpy float32 + fenv).
#
# Every FP32/FP64 result is computed with numpy float32/float64 arithmetic,
# which the host performs in the IEEE-754 correctly-rounded mode selected by
# fesetround(3).  This is a from-scratch Python oracle independent of the
# C++ interpreter's fp.cpp; it is used to validate the interpreter WITHOUT a
# GPU (never an automatic PASS) and to cross-check the GPU differential.
# ---------------------------------------------------------------------------

import ctypes as _ct
import numpy as _np

CANON_NAN32 = 0x7FFFFFFF
CANON_NAN64 = 0x7FFFFFFFFFFFFFFF

_FE_NEAREST, _FE_DOWN, _FE_UP, _FE_ZERO = 0, 0x400, 0x800, 0xC00
_LIBM = _ct.CDLL("libm.so.6")
_LIBM.fesetround.argtypes = [_ct.c_int]
_LIBM.fesetround.restype = _ct.c_int
_LIBM.fmaf.argtypes = [_ct.c_float, _ct.c_float, _ct.c_float]
_LIBM.fmaf.restype = _ct.c_float


def _set_round(rnd):
    """Apply a SASS rounding mode (0=RN,1=RM,2=RP,3=RZ) to the host fenv."""
    _LIBM.fesetround({0: _FE_NEAREST, 1: _FE_DOWN, 2: _FE_UP,
                      3: _FE_ZERO}[rnd])


def _f32v(b):
    return _np.float32(struct.unpack("<f", struct.pack("<I", int(b) & 0xFFFFFFFF))[0])


def _f32bits(v):
    return struct.unpack("<I", struct.pack("<f", float(v)))[0]


def _is_f32nan(b):
    e = (int(b) >> 23) & 0xFF
    return e == 0xFF and (int(b) & 0x7FFFFF) != 0


def sat_ref(bits):
    """FP32 SAT clamp reference (verified sm120): NaN -> +0, +inf -> 1.0,
    -inf/-1 -> +0, >1 -> 1.0, -0 -> +0, in-range unchanged."""
    if _is_f32nan(bits):
        return 0
    v = _f32v(bits)
    if v == 0.0:
        return 0
    v = _np.float32(min(max(float(v), 0.0), 1.0))
    return _f32bits(v)


def _is_f32den(b):
    return ((int(b) >> 23) & 0xFF) == 0 and (int(b) & 0x7FFFFF) != 0


def _flush_f32(b):
    return (int(b) & 0x80000000) if _is_f32den(b) else int(b)


# FP32 result NaN canonicalization (GPU sm120): every arithmetic NaN result
# is the positive quiet NaN 0x7fffffff.
def _canon(b):
    return CANON_NAN32 if _np.isnan(_f32v(b)) else b


def ref_ffma(a, b, c, rnd, mode):
    """FP32 fused multiply-add, sm120 flush semantics.

    `mode` is the SASS fmz field value: 0 = none, 1 = FMZ, 2 = FTZ.
    FTZ (2): flush all three denormal inputs sign-preserving, fused fma, a
    subnormal result flushes sign-preserving, exact +/-0 results keep the
    IEEE zero-sum sign.  FMZ (1): the denormal multiply inputs (a, b) flush
    to POSITIVE zero (multiply-path zero is sign-neutral on sm120), the
    denormal addend flushes sign-preserving, a subnormal product is kept in
    the fused sum, a subnormal result flushes sign-preserving, and an exact
    zero-product + zero-addend sum takes the addend's sign under RM else +0.
    Rule verified against a 288-combo modifier sweep and directed probes on
    sm120 (2026-08-17)."""
    if _is_f32nan(a) or _is_f32nan(b) or _is_f32nan(c):
        return CANON_NAN32
    if mode == 2:  # FTZ
        a, b, c = _flush_f32(a), _flush_f32(b), _flush_f32(c)
    elif mode == 1:  # FMZ
        a = 0 if _is_f32den(a) else a
        b = 0 if _is_f32den(b) else b
        c = _flush_f32(c)
    if mode == 1 and (int(a) & 0x7FFFFFFF) == 0 and \
            (int(b) & 0x7FFFFFFF) == 0 and (int(c) & 0x7FFFFFFF) == 0:
        # Exact zero-sum; multiply path sign-neutral under FMZ.
        return (0x80000000 if (rnd == 1 and (int(c) & 0x80000000)) else 0)
    _set_round(rnd)
    r = _LIBM.fmaf(_ct.c_float(float(_f32v(a))), _ct.c_float(float(_f32v(b))),
                   _ct.c_float(float(_f32v(c))))
    _LIBM.fesetround(_FE_NEAREST)
    out = _canon(_f32bits(r))
    if (out & 0x7F800000) == 0 and (out & 0x007FFFFF) != 0:
        # Subnormal result: flush sign-preserving (FTZ and FMZ).
        out = out & 0x80000000
    return out


def ref_fadd(a, b, rnd, flush):
    if _is_f32nan(a) or _is_f32nan(b):
        return CANON_NAN32
    if flush:
        a, b = _flush_f32(a), _flush_f32(b)
    _set_round(rnd)
    r = _np.float32(_f32v(a) + _f32v(b))
    _LIBM.fesetround(_FE_NEAREST)
    out = _canon(_f32bits(r))
    if flush and _is_f32den(out):
        # FADD/FMUL FTZ output flush is sign-preserving (sm120 verified).
        out = out & 0x80000000
    return out


def ref_fmul(a, b, rnd, flush):
    if _is_f32nan(a) or _is_f32nan(b):
        return CANON_NAN32
    if flush:
        a, b = _flush_f32(a), _flush_f32(b)
    _set_round(rnd)
    r = _np.float32(_f32v(a) * _f32v(b))
    _LIBM.fesetround(_FE_NEAREST)
    out = _canon(_f32bits(r))
    if flush and _is_f32den(out):
        # FADD/FMUL FTZ output flush is sign-preserving (sm120 verified).
        out = out & 0x80000000
    return out


def ref_f64(op, a, b, rnd):
    """DMUL/DADD on FP64 bit patterns; NaN preserved (sm120)."""
    af = struct.unpack("<d", struct.pack("<Q", a & 0xFFFFFFFFFFFFFFFF))[0]
    bf = struct.unpack("<d", struct.pack("<Q", b & 0xFFFFFFFFFFFFFFFF))[0]
    an = _np.isnan(af)
    bn = _np.isnan(bf)
    if an or bn:
        # NaN result: preserve the second NaN operand (sm120 verified).
        if bn:
            return b & 0xFFFFFFFFFFFFFFFF
        return a & 0xFFFFFFFFFFFFFFFF
    _set_round(rnd)
    r = (af * bf) if op == "DMUL" else (af + bf)
    _LIBM.fesetround(_FE_NEAREST)
    out = struct.unpack("<Q", struct.pack("<d", float(r)))[0]
    return out


def ref_f2f(src, fmt, rnd, ftz):
    """F2F conversion.  SASS mnemonic F2F.<dst>.<src>:
      F16.F32 = f32 -> f16 (down);  F32.F16 = f16 -> f32 (up);
      BF16.F32 = f32 -> bf16 (down, result in low 16);  F32.BF16 = bf16 -> f32 (up).
    The source width the generator loads may differ from the register the
    instruction reads; the reference follows the *instruction* semantics."""
    if fmt == "F16.F32":  # down: full f32 -> f16
        if _is_f32nan(src):
            return CANON_NAN32
        if ftz:
            src = _flush_f32(src)
        return _f32_to_f16_ref(src, rnd)
    if fmt == "BF16.F32":  # down: full f32 -> bf16 (low 16 bits)
        if _is_f32nan(src):
            return CANON_NAN32
        if ftz:
            src = _flush_f32(src)
        return _f32_to_bf16_ref(src, rnd)
    # Up: source is a 16-bit F16/BF16 in the low half.
    half = int(src) & 0xFFFF
    if fmt == "F32.BF16":
        s = (half >> 15) & 1
        e = (half >> 7) & 0xFF
        f = half & 0x7F
        if e == 0xFF:
            return CANON_NAN32 if f else (0x80000000 if s else 0x7F800000)
        if e == 0 and f == 0:
            return 0x80000000 if s else 0
        # bf16 -> f32: zero-extend (bf16 is the top 16 bits of f32).
        if e == 0:
            # subnormal bf16: value = f * 2^-133 (8-bit frac).  -> normal f32.
            return _f32bits(_np.float32((f if not s else -f) * 2.0 ** -133))
        return (0x80000000 if s else 0) | (e << 23) | (f << 16)
    # F32.F16 up: f16 -> f32.
    s = (half >> 15) & 1
    e = (half >> 10) & 0x1F
    f = half & 0x3FF
    if e == 0x1F:
        return CANON_NAN32 if f else (0x80000000 if s else 0x7F800000)
    if e == 0:
        if f == 0:
            return 0x80000000 if s else 0
        # subnormal half = f * 2^-24; upconvert exact to f32.
        return _f32bits(_np.float32((f if not s else -f) * 2.0 ** -24))
    return (0x80000000 if s else 0) | ((e - 15 + 127) << 23) | (f << 13)


def _f32_to_bf16_ref(src, rnd):
    """Exact f32 -> bf16 (result in the low 16 bits), directed rounding."""
    s = (src >> 31) & 1
    e = (src >> 23) & 0xFF
    f = src & 0x7FFFFF
    negative = bool(s)
    if e == 0xFF:
        return 0x7F80 if f else (0x8000 if s else 0x7F80)
    if e == 0 and f == 0:
        return 0x8000 if s else 0
    # bf16 = top 8 fraction bits of the f32 mantissa (8-bit frac, exp 8-bit).
    M = (1 << 23) | f if e else f
    E = int(e)
    if E == 0:
        # subnormal f32 -> subnormal/zero bf16.
        return _round_to_bf16_sub(f, rnd, negative)
    shift = 15  # drop 15 low mantissa bits to get 8-bit fraction
    m = M >> shift
    rem = M & ((1 << shift) - 1)
    if _decide(rem, 1 << (shift - 1), m & 1, rnd, negative):
        m += 1
        if m == 0x200:  # fraction overflow -> exponent bump
            if E + 1 >= 0xFF:
                to_inf = (rnd == 0) or (rnd == 2 and not negative) or (rnd == 1 and negative)
                return (0x8000 if s else 0) | (0x7F80 if to_inf else 0x7F7F)
            return (0x8000 if s else 0) | ((E + 1) << 7)
    return (0x8000 if s else 0) | (E << 7) | (m & 0x7F)


def _round_to_bf16_sub(f, rnd, negative):
    """Subnormal f32 -> bf16 subnormal/zero (bf16 subnormal unit = 2^-133)."""
    # f * 2^-149, in bf16 subnormal units (2^-133): shift = 149-133 = 16.
    q = 16
    m = f >> q
    rem = f & ((1 << q) - 1)
    if _decide(rem, 1 << (q - 1), m & 1, rnd, negative):
        m += 1
    if m >= (1 << 7):
        # rounds up to smallest normal bf16 (exp 1, frac 0).
        return (0x8000 if negative else 0) | (1 << 7)
    return (0x8000 if negative else 0) | (m & 0x7F)


def _f32_to_f16_ref(src, rnd):
    """Exact f32 -> f16 (full directed rounding, subnormal + ties)."""
    s = (src >> 31) & 1
    e = (src >> 23) & 0xFF
    f = src & 0x7FFFFF
    negative = bool(s)
    if e == 0xFF:
        return 0x7E00 if f else 0x7C00
    if e == 0 and f == 0:
        return 0x8000 if s else 0
    M = (1 << 23) | f if e else f
    E = int(e)
    ef = E - 112
    if ef >= 31:
        to_inf = (rnd == 0) or (rnd == 2 and not negative) or (rnd == 1 and negative)
        return (0x8000 if s else 0) | (0x7C00 if to_inf else 0x7BFF)
    if ef >= 1:
        shift = 13
        m = M >> shift
        rem = M & ((1 << shift) - 1)
        if _decide(rem, 1 << (shift - 1), m & 1, rnd, negative):
            m += 1
            if m == 0x800:
                if ef + 1 >= 31:
                    to_inf = (rnd == 0) or (rnd == 2 and not negative) or (rnd == 1 and negative)
                    return (0x8000 if s else 0) | (0x7C00 if to_inf else 0x7BFF)
                return (0x8000 if s else 0) | ((ef + 1) << 10)
        return (0x8000 if s else 0) | (ef << 10) | (m & 0x3FF)
    sh = 126 - E
    m = (M >> sh) if sh < 24 else 0
    rem = M if sh >= 24 else (M & ((1 << sh) - 1))
    carry = _decide(rem, 1 << (sh - 1), m & 1, rnd, negative) if (rnd == 0 and sh <= 25) \
        else (_decide(rem, 0, m & 1, rnd, negative) if rnd != 0 else False)
    if carry:
        m += 1
    if m == 1024:
        return (0x8000 if s else 0) | 0x400
    return (0x8000 if s else 0) | (m & 0x3FF)


def _decide(rem, half, odd, rnd, negative):
    if rnd == 1:
        return negative and rem != 0
    if rnd == 2:
        return (not negative) and rem != 0
    if rnd == 3:
        return False
    return rem > half or (rem == half and odd)


def ref_f2f64(pair, fmt, rnd, ftz):
    """Direct F64 -> F16/F32/BF16 rounding (no FP32 intermediate), matching
    the C++ f64_down_round.  fmt: 0=F16,1=F32,2=BF16."""
    sign = (pair >> 63) & 1
    exp = (pair >> 52) & 0x7FF
    frac = pair & 0xFFFFFFFFFFFFF
    negative = bool(sign)
    if fmt == 0:
        frac_bits, bias, exp_bits = 10, 15, 5
    elif fmt == 2:
        frac_bits, bias, exp_bits = 7, 127, 8
    else:
        frac_bits, bias, exp_bits = 23, 127, 8
    max_exp = (1 << exp_bits) - 1
    max_norm = max_exp - 1
    sub_unit = 1 - bias - frac_bits

    def sign_bit():
        return (0x80000000 if negative else 0) if fmt == 1 else \
               (0x8000 if negative else 0)

    def overflow():
        to_inf = (rnd == 0) or (rnd == 2 and not negative) or (rnd == 1 and negative)
        inf = sign_bit() | (max_exp << frac_bits)
        maxf = sign_bit() | (max_norm << frac_bits) | ((1 << frac_bits) - 1)
        return inf if to_inf else maxf

    if exp == 0x7FF:
        if frac:
            if fmt == 1:
                return sign_bit() | 0x7F800000 | ((frac >> 29) | 0x400000)
            return sign_bit() | (max_exp << frac_bits) | (1 << (frac_bits - 1))
        return sign_bit() | (max_exp << frac_bits)
    if exp == 0 and frac == 0:
        return sign_bit()

    M = (1 << 52) | frac if exp else frac
    E = exp if exp else 1
    ef = E - 1023 + bias

    def carry(rem, shift, m):
        if rnd == 0:
            if shift <= 0 or shift >= 64:
                return False
            half = 1 << (shift - 1)
            return rem > half or (rem == half and (m & 1))
        if rnd == 3:
            return False
        if rnd == 1:
            return negative and rem != 0
        return (not negative) and rem != 0

    if ef >= max_exp:
        return overflow()
    if ef >= 1:
        shift = 52 - frac_bits
        m = M >> shift
        rem = M & ((1 << shift) - 1)
        if carry(rem, shift, m):
            m += 1
            if m == (1 << (frac_bits + 1)):
                if ef + 1 >= max_exp:
                    return overflow()
                return sign_bit() | ((ef + 1) << frac_bits)
        out = sign_bit() | (ef << frac_bits) | (m & ((1 << frac_bits) - 1))
        if fmt == 1:
            # no sat in reference for fuzz (sat handled separately)
            pass
        return out
    # subnormal
    m_shift = 1075 + sub_unit - E
    if m_shift >= 53:
        m, rem = 0, M
    elif m_shift > 0:
        m, rem = M >> m_shift, M & ((1 << m_shift) - 1)
    else:
        m, rem = M << (-m_shift), 0
    if carry(rem, m_shift > 0 and m_shift or 0, m):
        m += 1
    if m >= (1 << frac_bits):
        return sign_bit() | (1 << frac_bits)
    out = sign_bit() | (m & ((1 << frac_bits) - 1))
    if ftz and (out & (max_exp << frac_bits)) == 0:
        out = (out & (0x80000000 if fmt == 1 else 0x8000)) if rnd == 1 else 0
    return out


def ref_f2i(src, dst, rnd):
    s, e, f, inf, nan, zero = _f32_parts(src)
    if nan:
        return 0x80000000
    v = _exact_f32(src)
    if v is None:
        # +/-inf saturates to the destination range (sm120 verified):
        # U32: +inf -> 0xFFFFFFFF, -inf -> 0; S32: +inf -> 0x7FFFFFFF,
        # -inf -> 0x80000000.
        if s:  # negative
            return 0 if dst == "U32" else 0x80000000
        return 0xFFFFFFFF if dst == "U32" else 0x7FFFFFFF
    m, iq, ie = v
    # value = +/- m / 2^iq * 2^ie.  Compute as a signed rational.
    if ie >= iq:
        q = m << (ie - iq)
        frac = 0
    else:
        sh = iq - ie
        q = m >> sh
        frac = m & ((1 << sh) - 1)
    # q is the magnitude of the truncated integer part.
    neg = bool(s)
    if rnd == "FLOOR":
        # floor(x): for negative x with fraction, one more negative.
        iv = -q if neg else q
        if neg and frac:
            iv -= 1
    elif rnd == "CEIL":
        iv = -q if neg else q
        if not neg and frac:
            iv += 1
    elif rnd == "TRUNC":
        iv = -q if neg else q
    else:  # ROUND ties-to-even on the signed value
        if frac:
            if neg:
                # round -q - frac/2^sh to nearest even
                sh = iq - ie if ie < iq else 0
                half = 1 << (sh - 1) if sh > 0 else 0
                if sh > 0:
                    if frac > half or (frac == half and (q & 1)):
                        iv = -(q + 1)
                    else:
                        iv = -q
                else:
                    iv = -q
            else:
                sh = iq - ie if ie < iq else 0
                half = 1 << (sh - 1) if sh > 0 else 0
                if sh > 0:
                    if frac > half or (frac == half and (q & 1)):
                        iv = q + 1
                    else:
                        iv = q
                else:
                    iv = q
        else:
            iv = -q if neg else q
    if dst == "U32":
        if iv < 0:
            return 0
        if iv > 0xFFFFFFFF:
            return 0xFFFFFFFF
        return iv
    else:
        if iv > 0x7FFFFFFF:
            return 0x7FFFFFFF
        if iv < -0x80000000:
            return 0x80000000
        return iv & 0xFFFFFFFF


def ref_i2f(src, fmt, rnd):
    if fmt == "S32":
        iv = src if src < 0x80000000 else src - 0x100000000
    else:
        iv = src
    _set_round(rnd)
    r = _np.float32(float(iv))
    _LIBM.fesetround(_FE_NEAREST)
    return _f32bits(r)


def ref_fsetp(a, b, op, bop, pp_val):
    sa, ea, fa, ai, an, az = _f32_parts(a)
    sb, eb, fb, bi, bn, bz = _f32_parts(b)
    af, bf = _f32v(a), _f32v(b)
    cmap = {"LT": (not an and not bn and af < bf),
            "EQ": (not an and not bn and af == bf),
            "LE": (not an and not bn and af <= bf),
            "GT": (not an and not bn and af > bf),
            "NE": (not an and not bn and af != bf),
            "GE": (not an and not bn and af >= bf),
            "NUM": (not an and not bn),
            "NAN": (an or bn),
            # U-variants are unordered-true: true on NaN (sm120 verified).
            "LTU": (an or bn) or af < bf, "EQU": (an or bn) or af == bf,
            "LEU": (an or bn) or af <= bf, "GTU": (an or bn) or af > bf,
            "NEU": (an or bn) or af != bf, "GEU": (an or bn) or af >= bf}
    r = cmap.get(op, False)
    pp = bool(pp_val)
    def bop_fn(x, y):
        return {"AND": x and y, "OR": x or y, "XOR": x != y}[bop]
    pu = bop_fn(r, pp)
    pv = bop_fn(not r, pp)
    return (1 if pu else 0) | (2 if pv else 0)


def ref_fmnmx(a, b, pp, mods):
    sa, ea, fa, ai, an, az = _f32_parts(a)
    sb, eb, fb, bi, bn, bz = _f32_parts(b)
    is_max = (pp == "!PT")
    nan = ".NAN" in mods
    xorsign = ".XORSIGN" in mods
    if nan and (an or bn):
        return CANON_NAN32
    if an or bn:
        return b if an else a
    af, bf = _f32v(a), _f32v(b)
    if is_max:
        # max: +0 beats -0 when equal in magnitude.
        if af > bf:
            out = a
        elif af < bf:
            out = b
        else:  # equal magnitude (incl +/-0)
            out = a if sa == 0 else b
    else:
        # min: -0 beats +0 when equal in magnitude.
        if af < bf:
            out = a
        elif af > bf:
            out = b
        else:
            out = b if sb == 1 else a
    if xorsign:
        ns = (sa ^ sb) & 1
        out = (out & 0x7FFFFFFF) | (ns << 31)
    return out


def ref_int(kind, a, b, c):
    if kind == "IADD3":
        return (a + b + c) & 0xFFFFFFFF
    if kind == "IMAD":
        return (a * b + c) & 0xFFFFFFFF
    if kind.startswith("SHF.L"):
        # LO.L: Ra << sh (no fill)
        return (a << (b & 0x1F)) & 0xFFFFFFFF
    if kind.startswith("SHF.R"):
        # LO.R funnel: (c << (32-sh)) | (a >> sh)
        sh = b & 0x1F
        if sh == 0:
            return a
        return ((c << (32 - sh)) | (a >> sh)) & 0xFFFFFFFF
    if kind == "POPC":
        return bin(a).count("1")
    if kind == "IABS":
        return (a if not (a & 0x80000000) else ((~a + 1) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return 0


def _f32_parts(b):
    sign = (int(b) >> 31) & 1
    exp = (int(b) >> 23) & 0xFF
    frac = int(b) & 0x7FFFFF
    if exp == 0xFF:
        return sign, exp, frac, not bool(frac), bool(frac), False
    if exp == 0:
        return sign, exp, frac, False, False, frac == 0
    return sign, exp, frac, False, False, False


def _exact_f32(b):
    sign, exp, frac, inf, nan, zero = _f32_parts(b)
    if inf or nan:
        return None
    if exp == 0:
        return (frac, 23, -126) if frac else (0, 0, 0)
    return ((1 << 23) | frac, 23, exp - 127)



# ---------------------------------------------------------------------------
# Build one random kernel per instruction family
# ---------------------------------------------------------------------------

def mov(reg, val):
    return f"    MOV32I {reg}, 0x{val & 0xFFFFFFFF:08X};[7:7:{{0}}:5:1]"


def build_gpu(src, name):
    return assemble(src, kernel_name=name, check_deps=False)


def build_semu(src, name):
    return assemble(src, kernel_name=name, check_deps=False)


def mangle(name):
    return f"_Z{len(name)}{name}"


# ---------------------------------------------------------------------------
# Case generators: each returns a (label, gpu_src, semu_src, nres, block)
# ---------------------------------------------------------------------------

def gen_ffma_cases(rng, n):
    cases = []
    for i in range(n):
        a = rand_f32_bits(rng)
        b = rand_f32_bits(rng)
        c = rand_f32_bits(rng)
        rnd = rng.choice(["", ".RM", ".RP", ".RZ"])
        flush = rng.choice(["", ".FMZ"])
        sat = rng.choice(["", ".SAT"])
        label = f"FFMA-{a:08X}-{b:08X}-{c:08X}{rnd}{flush}{sat}"
        rnd_idx = {"": 0, ".RM": 1, ".RP": 2, ".RZ": 3}[rnd]
        mode = 1 if flush else 0   # fmz field value (FMZ only in fuzz)
        body = [mov("R0", a), mov("R1", b), mov("R2", c),
                f"    FFMA{flush}{rnd}{sat} R3, R0, R1, R2;[1:7:{{0}}:8:1]"]
        ref = lambda a=a, b=b, c=c, ri=rnd_idx, md=mode, st=bool(sat): \
            [ref_ffma(a, b, c, ri, md) if not st
             else sat_ref(ref_ffma(a, b, c, ri, md))]
        cases.append((label, body, ["R3"], ref))
    return cases


def gen_fadd_fmul_cases(rng, n):
    cases = []
    for i in range(n):
        op = rng.choice(["FADD", "FMUL"])
        a = rand_f32_bits(rng)
        b = rand_f32_bits(rng)
        rnd = rng.choice(["", ".RM", ".RP", ".RZ"])
        flush = rng.choice(["", ".FTZ"])
        sat = rng.choice(["", ".SAT"])
        label = f"{op}-{a:08X}-{b:08X}{rnd}{flush}{sat}"
        rnd_idx = {"": 0, ".RM": 1, ".RP": 2, ".RZ": 3}[rnd]
        fl = bool(flush)
        body = [mov("R0", a), mov("R1", b),
                f"    {op}{flush}{rnd}{sat} R3, R0, R1;[1:7:{{0}}:8:1]"]
        if op == "FADD":
            ref = lambda a=a, b=b, ri=rnd_idx, f=fl, st=bool(sat): \
                [ref_fadd(a, b, ri, f) if not st else sat_ref(ref_fadd(a, b, ri, f))]
        else:
            ref = lambda a=a, b=b, ri=rnd_idx, f=fl, st=bool(sat): \
                [ref_fmul(a, b, ri, f) if not st else sat_ref(ref_fmul(a, b, ri, f))]
        cases.append((label, body, ["R3"], ref))
    return cases


def gen_f64_cases(rng, n):
    cases = []
    for i in range(n):
        op = rng.choice(["DMUL", "DADD"])
        a = rand_f64_bits(rng)
        b = rand_f64_bits(rng)
        rnd = rng.choice(["", ".RM", ".RP", ".RZ"])
        rnd_idx = {"": 0, ".RM": 1, ".RP": 2, ".RZ": 3}[rnd]
        label = f"{op}-{a:016X}-{b:016X}{rnd}"
        body = [f"    MOV R0, 0x{a & 0xFFFFFFFF:08X};[7:7:{{0}}:5:1]",
                f"    MOV R1, 0x{a >> 32:08X};[7:7:{{0}}:5:1]",
                f"    MOV R2, 0x{b & 0xFFFFFFFF:08X};[7:7:{{0}}:5:1]",
                f"    MOV R3, 0x{b >> 32:08X};[7:7:{{0}}:5:1]",
                f"    {op}{rnd} {{R4,R5}}, {{R0,R1}}, {{R2,R3}};[2:7:{{0}}:8:1]"]
        def ref(op=op, a=a, b=b, ri=rnd_idx):
            v = ref_f64(op, a, b, ri)
            return [v & 0xFFFFFFFF, v >> 32]
        cases.append((label, body, ["R4", "R5"], ref))
    return cases


def gen_f2f_cases(rng, n):
    cases = []
    for i in range(n):
        fmt = rng.choice(["F32.F16", "F16.F32", "F32.BF16", "BF16.F32"])
        if fmt in ("F32.F16", "F32.BF16"):
            # downconvert: source is a full f32
            src = rand_f32_bits(rng)
            label = f"F2F-{fmt}-{src:08X}"
            body = [mov("R0", src), f"    F2F.{fmt} R3, R0;[2:7:{{0}}:8:1]"]
        else:
            # upconvert: source is a 16-bit F16/BF16 in the low half
            src = rng.getrandbits(16)
            label = f"F2F-{fmt}-{src:04X}"
            body = [mov("R0", src), f"    F2F.{fmt} R3, R0;[2:7:{{0}}:8:1]"]
        rnd = 0  # RN default for F2F fuzz (conversions round per RN here)
        ref = lambda s=src, fm=fmt, ri=rnd: [ref_f2f(s, fm, ri, False)]
        cases.append((label, body, ["R3"], ref))
    return cases


def gen_f2f64_cases(rng, n):
    """F64 -> F16/F32/BF16 direct downconversion fuzz (double-rounding traps,
    NaN payloads, subnormals, overflow) across all directed rounding modes."""
    cases = []
    for i in range(n):
        pair = rand_f64_bits(rng)
        fmt = rng.choice(["F16.F64", "F32.F64", "BF16.F64"])
        rnd = rng.choice(["", ".RN", ".RM", ".RP", ".RZ"])
        rnd_idx = {"": 0, ".RN": 0, ".RM": 1, ".RP": 2, ".RZ": 3}[rnd]
        fmt_idx = {"F16.F64": 0, "F32.F64": 1, "BF16.F64": 2}[fmt]
        lo, hi = pair & 0xFFFFFFFF, pair >> 32
        label = f"F2F{fmt}{rnd}-{lo:08X}-{hi:08X}"
        body = [f"    MOV R0, 0x{lo:08X};[7:7:{{0}}:5:1]",
                f"    MOV R1, 0x{hi:08X};[7:7:{{0}}:5:1]",
                f"    F2F.{fmt}{rnd} R3, {{R0,R1}};[2:7:{{0}}:8:1]"]
        ref = lambda p=pair, fi=fmt_idx, ri=rnd_idx: \
            [ref_f2f64(p, fi, ri, False)]
        cases.append((label, body, ["R3"], ref))
    return cases


def gen_f2i_cases(rng, n):
    cases = []
    for i in range(n):
        src = rand_f32_bits(rng)
        dst = rng.choice(["S32", "U32"])
        rnd = rng.choice(["ROUND", "FLOOR", "CEIL", "TRUNC"])
        label = f"F2I-{dst}-{rnd}-{src:08X}"
        body = [mov("R0", src), f"    F2I.{dst}.F32.{rnd} R3, R0;[2:7:{{0}}:8:1]"]
        ref = lambda s=src, d=dst, r=rnd: [ref_f2i(s, d, r)]
        cases.append((label, body, ["R3"], ref))
    return cases


def gen_i2f_cases(rng, n):
    cases = []
    for i in range(n):
        src = rand_u32(rng)
        fmt = rng.choice(["U32", "S32"])
        label = f"I2F-{fmt}-{src:08X}"
        body = [mov("R0", src), f"    I2F.F32.{fmt} R3, R0;[2:7:{{0}}:8:1]"]
        ref = lambda s=src, fm=fmt: [ref_i2f(s, fm, 0)]
        cases.append((label, body, ["R3"], ref))
    return cases


def gen_fsetp_cases(rng, n):
    cases = []
    ops = ["LT", "EQ", "LE", "GT", "NE", "GE", "NUM", "NAN",
           "LTU", "EQU", "LEU", "GTU", "NEU", "GEU"]
    for i in range(n):
        a = rand_f32_bits(rng)
        b = rand_f32_bits(rng)
        op = rng.choice(ops)
        bop = rng.choice(["AND", "OR", "XOR"])
        label = f"FSETP-{op}-{bop}-{a:08X}-{b:08X}"
        body = [mov("R0", a), mov("R1", b),
                f"    FSETP.{op}.{bop} P0, P1, R0, R1, PT;[7:7:{{0}}:8:1]",
                "    P2R R3, PR, RZ, 0x1;[7:7:{0}:8:1]",
                "    P2R R4, PR, RZ, 0x2;[7:7:{0}:8:1]"]
        def ref(a=a, b=b, o=op, bo=bop):
            packed = ref_fsetp(a, b, o, bo, 1)  # Pp=PT -> 1
            # P2R register values: R3 = P0?1:0, R4 = P1?2:0.
            return [packed & 1, packed & 2]
        cases.append((label, body, ["R3", "R4"], ref))
    return cases


def gen_fmnmx_cases(rng, n):
    cases = []
    for i in range(n):
        a = rand_f32_bits(rng)
        b = rand_f32_bits(rng)
        pp = rng.choice(["PT", "!PT"])
        mod = rng.choice(["", ".NAN", ".XORSIGN"])
        label = f"FMNMX{mod}-{pp}-{a:08X}-{b:08X}"
        body = [mov("R0", a), mov("R1", b),
                f"    FMNMX{mod} R3, R0, R1, {pp};[7:7:{{0}}:8:1]"]
        ref = lambda a=a, b=b, p=pp, m=mod: [ref_fmnmx(a, b, p, m)]
        cases.append((label, body, ["R3"], ref))
    return cases


def gen_int_cases(rng, n):
    cases = []
    for i in range(n):
        a = rand_u32(rng)
        b = rand_u32(rng)
        c = rand_u32(rng)
        kind = rng.choice(["IADD3", "IMAD", "LOP3", "SHF", "SHF",
                           "POPC", "IABS"])
        d = rng.choice(["L", "R"])
        kind_shown = kind if kind != "SHF" else f"SHF.{d}"
        label = f"{kind_shown}-{a:08X}-{b:08X}-{c:08X}"
        if kind == "IADD3":
            body = [mov("R0", a), mov("R1", b), mov("R2", c),
                    "    IADD3 R3, R0, R1, R2;[7:7:{0}:8:1]"]
        elif kind == "IMAD":
            body = [mov("R0", a), mov("R1", b), mov("R2", c),
                    "    IMAD R3, R0, R1, R2;[7:7:{0}:8:1]"]
        elif kind == "LOP3":
            lut = rng.choice([0x80, 0xFE, 0x96, 0xE8, 0xC0, 0x78])
            body = [mov("R0", a), mov("R1", b), mov("R2", c),
                    f"    LOP3 R3, R0, R1, R2, 0x{lut:02X};[7:7:{{0}}:8:1]"]
        elif kind == "SHF":
            body = [mov("R0", a), mov("R1", b & 0x1F), mov("R2", c),
                    f"    SHF.{d}.U32 R3, R0, R1, R2;[2:7:{{0}}:8:1]"]
        elif kind == "POPC":
            body = [mov("R0", a), "    POPC R3, R0;[7:7:{0}:8:1]"]
        else:  # IABS
            body = [mov("R0", a), "    IABS R3, R0;[7:7:{0}:8:1]"]
        if kind == "LOP3":
            # LOP3 reference: truth-table with lut (a,b,c) index (a=MSB).
            def ref(a=a, b=b, c=c, lut=lut):
                out = 0
                for bit in range(32):
                    idx = (((a >> bit) & 1) << 2) | (((b >> bit) & 1) << 1) | ((c >> bit) & 1)
                    if (lut >> idx) & 1:
                        out |= (1 << bit)
                return [out]
        else:
            kind_ref = kind if kind != "SHF" else f"SHF.{d}"
            ref = lambda a=a, b=b, c=c, kr=kind_ref: [ref_int(kr, a, b, c)]
        cases.append((label, body, ["R3"], ref))
    return cases


# ---------------------------------------------------------------------------
# Mutation test: tamper one semu result word and confirm the gate fails.
# Guards against the harness silently passing when the interpreter is wrong.
# ---------------------------------------------------------------------------

def run_mutation(n=12, seed=7):
    """Run `n` fuzz cases with the first semu result word flipped (low bit).
    Every case must be flagged FAIL (semu no longer matches the reference).

    Returns (detected, total, errors):
      detected — tampered cases whose flipped result was flagged by the
                 reference gate.
      total    — cases actually verified (have a non-empty reference).
      errors   — cases where semu itself faulted/errored before the tamper
                 could be compared; these must NOT count as "detected" (a
                 harness/runtime failure must not mask a broken gate).
    The gate passes only when detected == total, total > 0, and errors == 0.
    """
    rng = random.Random(seed)
    gen = (gen_ffma_cases(rng, n) + gen_fadd_fmul_cases(rng, n) +
           gen_f64_cases(rng, n) + gen_f2f_cases(rng, n) +
           gen_f2i_cases(rng, n) + gen_i2f_cases(rng, n) +
           gen_fsetp_cases(rng, n) + gen_fmnmx_cases(rng, n) +
           gen_int_cases(rng, n))
    detected = 0
    total = 0
    errors = 0
    skipped = 0
    details = []
    for ci, (label, body, results, ref_fn) in enumerate(gen):
        if ref_fn is None:
            skipped += 1
            continue
        ref_words = ref_fn()
        if not ref_words:
            skipped += 1
            continue
        total += 1
        sname = f"mut_{ci:04d}_s"
        scubin = assemble(semu_kernel(sname, body),
                          kernel_name=sname, check_deps=False)
        # run_semu() reads /tmp/fz_semu.cubin — write there (not a side path)
        # so the interpreter actually runs THIS kernel.
        Path("/tmp/fz_semu.cubin").write_bytes(scubin)
        sres, serr = run_semu(scubin, mangle(sname), (1, 1, 1))
        if sres is None or "fault" in sres:
            # semu fault/error: the tampered value never ran, so this is a
            # harness/runtime failure, NOT a reference-detected mutation.
            errors += 1
            detail = "no result"
            if sres is not None and "fault" in sres:
                detail = str(sres["fault"])
            elif serr:
                detail = serr
            details.append(f"{label}: semu fault/error, mutation unverified "
                           f"({detail})")
            continue
        semu_words = []
        for i, reg in enumerate(results):
            semu_words.append(sres["ctas"][0]["warps"][0]["lanes"][0]["gpr"][int(reg[1:])])
        # Tamper the low bit of the first result word.
        semu_words[0] ^= 1
        if semu_words != ref_words:
            detected += 1
        else:
            details.append(f"{label}: tampered word NOT caught by reference")
    report = {"mutation": {"detected": detected, "total": total,
                           "errors": errors, "skipped": skipped},
              "seed": seed, "n": n}
    with open("/tmp/fuzz_phase5_mutation.json", "w") as f:
        json.dump(report, f, indent=1)
    print(f"=== mutation: {detected}/{total} tampered cases detected by the "
          f"reference gate, {errors} semu errors, {skipped} skipped "
          f"(expect {total}/{total}, 0 errors) ===")
    for d in details[:20]:
        print("  " + d)
    return detected, total, errors


def gpu_kernel(name, body, results):
    nlen = max(1, len(results) * 4)
    pro = [
        "#fn " + name + "(out<8>) {",
        "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
        "    LDC.64 {R22, R23}, #param(out);[0:7:{}:1:0]",
        "    S2R R30, SR_TID.X;[0:7:{0}:5:1]",
        f"    IMAD.WIDE {{R28,R29}}, R30, 0x{nlen:04X}, {{R22,R23}};[0:7:{{0}}:8:1]",
    ]
    nops = ["    NOP;[7:7:{}:1:1]"] * 48
    stgs = []
    for i, reg in enumerate(results):
        stgs.append(f"    STG.E desc[{{UR4,UR5}}][{{R28,R29}}+0x{i*4:X}], {reg};"
                    f"[0:1:{{0,2}}:1:0]")
    tail = ["    EXIT;[7:7:{}:5:0]", "}"]
    return "\n".join(pro + body + nops + stgs + tail)


def semu_kernel(name, body):
    return "#fn " + name + "(dummy<4>) {\n" + "\n".join(body) + \
           "\n    EXIT;[7:7:{}:5:0]\n}"


def run_semu(cubin_bytes, kernel, block):
    import json
    import subprocess
    p = subprocess.run(
        [SEMU, "run", "/tmp/fz_semu.cubin", kernel,
         "1", str(block[0]), "1", str(block[1]), "1", str(block[2])],
        capture_output=True, text=True)
    if p.returncode != 0:
        return None, p.stdout.strip()
    return json.loads(p.stdout), None


def main():
    import json
    import subprocess
    n = 100
    seed = 42
    do_gpu = "--gpu" in sys.argv
    argv = sys.argv[:]
    for i, a in enumerate(argv):
        if a == "-n" and i + 1 < len(argv):
            n = int(argv[i + 1])
        if a == "--seed" and i + 1 < len(argv):
            seed = int(argv[i + 1])
    rng = random.Random(seed)

    gen = (gen_ffma_cases(rng, n // 9) + gen_fadd_fmul_cases(rng, n // 9) +
           gen_f64_cases(rng, n // 9) + gen_f2f_cases(rng, n // 9) +
           gen_f2f64_cases(rng, n // 9) + gen_f2i_cases(rng, n // 9) +
           gen_i2f_cases(rng, n // 9) + gen_fsetp_cases(rng, n // 9) +
           gen_fmnmx_cases(rng, n // 9) + gen_int_cases(rng, n // 9))

    passed = failed = skipped = 0
    fail_detail = []
    report = {"seed": seed, "gpu": bool(do_gpu), "n": len(gen),
              "passed": 0, "failed": 0, "skipped": 0,
              "cases": []}
    for ci, case in enumerate(gen):
        label, body, results, ref_fn = case
        gname = f"fz_{ci:04d}_g"
        sname = f"fz_{ci:04d}_s"
        entry = {"label": label}
        try:
            gcubin = assemble(gpu_kernel(gname, body, results),
                              kernel_name=gname, check_deps=False)
            scubin = assemble(semu_kernel(sname, body),
                              kernel_name=sname, check_deps=False)
        except Exception as e:
            failed += 1
            entry["status"] = "FAIL"; entry["detail"] = f"assemble {e}"
            fail_detail.append(f"{label}: assemble {type(e).__name__}: {e}")
            report["cases"].append(entry)
            continue
        Path("/tmp/fz_gpu.cubin").write_bytes(gcubin)
        Path("/tmp/fz_semu.cubin").write_bytes(scubin)

        gpu_words = None
        if do_gpu:
            try:
                mod = CudaModule(gcubin)
                d = mod.devmem_alloc(len(results) * 4 + 64)
                mod.launch(mangle(gname), grid=(1,), block=(1,), args=[d])
                mod.synchronize()
                gpu_words = list(struct.unpack(f"<{len(results)}I",
                                               mod.device_read(d, len(results) * 4)))
                mod.devmem_free(d)
            except Exception as e:
                failed += 1
                entry["status"] = "FAIL"; entry["detail"] = f"GPU {e}"
                fail_detail.append(f"{label}: GPU {type(e).__name__}: {e}")
                report["cases"].append(entry)
                continue

        sres, serr = run_semu(scubin, mangle(sname), (1, 1, 1))
        if sres is None:
            failed += 1
            entry["status"] = "FAIL"; entry["detail"] = f"semu {serr}"
            fail_detail.append(f"{label}: semu {serr}")
            report["cases"].append(entry)
            continue
        if "fault" in sres:
            failed += 1
            entry["status"] = "FAIL"; entry["detail"] = f"semu fault {sres['fault']}"
            fail_detail.append(f"{label}: semu fault {sres['fault']}")
            report["cases"].append(entry)
            continue
        semu_words = []
        for i, reg in enumerate(results):
            semu_words.append(sres["ctas"][0]["warps"][0]["lanes"][0]["gpr"][int(reg[1:])])

        # 1) Host reference check (always; this is the non-GPU oracle).
        # 2) GPU check (when --gpu).  A case never auto-passes: it must agree
        #    with the reference, and with the GPU when present.  Cases with no
        #    reference and no GPU are marked SKIP, never PASS.
        ref_words = None
        if ref_fn is not None:
            try:
                ref_words = ref_fn()
            except Exception as e:
                ref_words = None
                entry.setdefault("warnings", []).append(f"ref error {e}")
        ok = True
        if ref_words is not None:
            if ref_words != semu_words:
                ok = False
                for i, reg in enumerate(results):
                    if ref_words[i] != semu_words[i]:
                        fail_detail.append(
                            f"{label}: {reg} ref=0x{ref_words[i]:08X} "
                            f"semu=0x{semu_words[i]:08X}")
        if do_gpu and gpu_words is not None:
            if gpu_words != semu_words:
                ok = False
                for i, reg in enumerate(results):
                    if gpu_words[i] != semu_words[i]:
                        fail_detail.append(
                            f"{label}: {reg} gpu=0x{gpu_words[i]:08X} "
                            f"semu=0x{semu_words[i]:08X}")

        if ok and (ref_words is not None or do_gpu):
            passed += 1
            entry["status"] = "PASS"
        elif ok:
            skipped += 1
            entry["status"] = "SKIP"
            entry["detail"] = "no reference and no GPU: unverified"
            fail_detail.append(
                f"{label}: SKIP (no reference oracle, no GPU) — not a pass")
        else:
            failed += 1
            entry["status"] = "FAIL"
        report["cases"].append(entry)

    report["passed"] = passed
    report["failed"] = failed
    report["skipped"] = skipped
    with open("/tmp/fuzz_phase5_report.json", "w") as f:
        json.dump(report, f, indent=1)
    print(f"\n=== fuzz: {passed} passed, {failed} failed, {skipped} skipped, "
          f"{len(gen)} cases (seed={seed}, gpu={do_gpu}) ===")
    for d in fail_detail[:40]:
        print("  " + d)
    return 0 if failed == 0 and skipped == 0 else 1


if __name__ == "__main__":
    if "--mutation" in sys.argv:
        # Gate passes only when EVERY verified tampered word is detected and
        # no semu error masked an unverified case.
        detected, total, errors = run_mutation()
        ok = total > 0 and detected == total and errors == 0
        sys.exit(0 if ok else 1)
    sys.exit(main())
