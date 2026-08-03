#!/usr/bin/env python3
"""Bit-accurate FDA (Fused-Dot-Add) reference model of the NVIDIA Tensor Core
fp16/bf16 HMMA path (Hopper sm_90).

Implements the FDA algorithm of arXiv:2511.10909 ("MMA-Sim: Bit-Accurate
Reference Model of Tensor Cores and Matrix Cores"), Hopper column of the
HMMA.16816.F32 / .BF16 row:

  * F = 25 fractional bits in the align step (Step 3)
  * exact fixed-point sum (Step 4) -- order-independent
  * round-to-zero (RZ) at the FP32 23rd fractional bit on output (Step 5)
  * |result| >= 2^128 -> infinity
  * specials: any NaN -> canonical 0x7FFFFFFF; 0*inf -> NaN; only one inf
    kind -> that inf; both +inf and -inf present -> NaN
  * subnormal inputs (bf16/f16) and C are honored (full FP32 dynamic range)

The model computes d = f(c, a_0..a_{K-1}, b_0..b_{K-1}) for ONE output element
(given its K product pairs).  Fragment layout mapping (which a/b slots feed
which D element) lives in the caller / probe tooling.

Usage: python3 hmma_model.py          (self-test against verified vectors)
"""
import struct

F = 25                     # Hopper HMMA fractional bits (align step)
NAN_OUT = 0x7FFFFFFF       # canonical FP32 NaN (NVIDIA)


def _ebits(mant):
    return 8 if mant == 7 else (5 if mant == 10 else 8)   # bf16/f16/fp32


def _special(v, mant):
    """Classify a half/FP32 value as 'nan'|'+inf'|'-inf'|'num'."""
    ebits = _ebits(mant)
    e = (v >> mant) & ((1 << ebits) - 1)
    emax = (1 << ebits) - 1
    if e == emax:
        if v & ((1 << mant) - 1):
            return "nan"
        return "+inf" if not (v >> (mant + ebits)) else "-inf"
    return "num"


def _sm(v, mant, bias):
    """Decompose a bf16/f16 into (sign, num, den_log2, exp) where
    value = sign * num * 2**(exp - den_log2)."""
    ebits = _ebits(mant)
    sign = -1 if (v >> (mant + ebits)) else 1
    e = (v >> mant) & ((1 << ebits) - 1)
    m = v & ((1 << mant) - 1)
    if e == 0:                          # subnormal: m/2^mant * 2^(1-bias)
        return sign, m, mant, 1 - bias
    return sign, (1 << mant) + m, mant, e - bias


def _fp32_sm(x):
    """Decompose FP32 bits into (sign, num, den_log2, exp)."""
    sign = -1 if (x >> 31) else 1
    e = (x >> 23) & 0xFF
    m = x & 0x7FFFFF
    if e == 0:
        return sign, m, 23, 1 - 127
    return sign, (1 << 23) + m, 23, e - 127


def _is_zero_half(v, mant):
    return (v & ((1 << (mant + 1)) - 1)) == 0


def _sign_pos(v, mant):
    return not (v >> (mant + _ebits(mant)))


def _sm_fp8(v, mant=3, bias=7, ebits=4):
    """Decompose an fp8 (e4m3/e5m2-style) value.  NVIDIA QMMA treats the
    all-ones exponent as an ordinary value (exp 15 -> 2^8 for e4m3): there are
    NO NaN/inf special values in fp8 inputs -- verified on SM120."""
    sign = -1 if (v >> (mant + ebits)) else 1
    e = (v >> mant) & ((1 << ebits) - 1)
    m = v & ((1 << mant) - 1)
    if e == 0:
        return sign, m, mant, 1 - bias
    return sign, (1 << mant) + m, mant, e - bias


def _tz_div(num, den):
    """num//den truncated toward zero (RZ), not floor."""
    q, r = divmod(num, den)
    return q + (1 if r and num < 0 else 0)


def _to_fixed(num, den_log2, shift):
    """num / 2**den_log2 * 2**shift = num * 2**(shift - den_log2), RZ-truncated."""
    k = shift - den_log2
    if k >= 0:
        return num << k
    return _tz_div(num, 1 << (-k))


def fda(c_bits, a_vals, b_vals, fmt="bf16"):
    """One output element: d = f(c, a_0..K-1, b_0..K-1).

    c_bits: FP32 bits of the accumulator.  a_vals/b_vals: half-precision bit
    values (bf16, f16, or fp8 e4m3).  Returns the FP32 output bits.
    """
    if fmt == "e4m3":
        mant, bias = 3, 7
        is_fp8 = True
    else:
        mant = 7 if fmt == "bf16" else 10
        bias = 127 if fmt == "bf16" else 15
        is_fp8 = False

    # ---- Step 1: special values -----------------------------------------
    # fp8 inputs carry NO special values (exp-15 is an ordinary exponent);
    # only the FP32 accumulator C can be NaN/inf.  For bf16/f16 the full FDA
    # special-value logic applies (any NaN -> canonical, 0*inf -> NaN, only one
    # inf kind -> that inf, both kinds -> NaN).
    if _special(c_bits, 23) == "nan":
        return NAN_OUT
    if is_fp8:
        # fp8 e4m3: only the all-ones pattern 0x7F/0xFF is NaN; every other
        # bit pattern (incl. exp-15) is an ordinary value.  No fp8 infinity.
        # NaN wins over c's inf, so check fp8 NaN before propagating c.
        for a, b in zip(a_vals, b_vals):
            if a in (0x7F, 0xFF) or b in (0x7F, 0xFF):
                return NAN_OUT
        c_sp = _special(c_bits, 23)
        if c_sp in ("+inf", "-inf"):
            return 0x7F800000 if c_sp == "+inf" else 0xFF800000
    else:
        infs = []
        c_sp = _special(c_bits, 23)
        if c_sp in ("+inf", "-inf"):
            infs.append(c_sp)                 # c's inf joins the sign mix
        for a, b in zip(a_vals, b_vals):
            sa, sb = _special(a, mant), _special(b, mant)
            if sa == "nan" or sb == "nan":
                return NAN_OUT
            if sa in ("+inf", "-inf") or sb in ("+inf", "-inf"):
                za, zb = _is_zero_half(a, mant), _is_zero_half(b, mant)
                if (sa in ("+inf", "-inf") and zb) or (sb in ("+inf", "-inf") and za):
                    return NAN_OUT                      # 0 * inf
                # product sign: finite * inf and inf * inf follow the sign
                if sa in ("+inf", "-inf") and sb in ("+inf", "-inf"):
                    prod = "+inf" if sa == sb else "-inf"
                elif sa in ("+inf", "-inf"):
                    prod = sa if _sign_pos(b, mant) else ("-inf" if sa == "+inf" else "+inf")
                else:
                    prod = sb if _sign_pos(a, mant) else ("-inf" if sb == "+inf" else "+inf")
                infs.append(prod)
        if infs:
            if "+inf" in infs and "-inf" in infs:
                return NAN_OUT
            return 0x7F800000 if "+inf" in infs else 0xFF800000

    # ---- Step 2: exact products (significand x exponent, no normalization) --
    c_sign, c_num, c_den, c_e = _fp32_sm(c_bits)
    have_c = c_num != 0
    prods = []
    e_max = c_e if have_c else None
    for a, b in zip(a_vals, b_vals):
        if is_fp8:
            sa, anum, aden, ae = _sm_fp8(a)
            sb, bnum, bden, be = _sm_fp8(b)
        else:
            sa, anum, aden, ae = _sm(a, mant, bias)
            sb, bnum, bden, be = _sm(b, mant, bias)
        p = (sa * sb, anum * bnum, aden + bden, ae + be)
        prods.append(p)
        if e_max is None or p[3] > e_max:
            e_max = p[3]
    if e_max is None:
        e_max = 0

    # ---- Step 3/4: align to e_max, truncate (RZ) to F bits, exact sum -------
    total = 0
    if have_c:
        total += _to_fixed(c_sign * c_num, c_den, c_e - e_max + F)
    for sign, num, den_log2, e in prods:
        total += _to_fixed(sign * num, den_log2, e - e_max + F)

    # ---- Step 5: normalize to FP32, RZ at bit 23 ---------------------------
    if total == 0:
        return 0x00000000
    neg = total < 0
    t = -total if neg else total
    bl = t.bit_length()
    e_val = (e_max - F) + (bl - 1)          # unbiased exponent of |sum|
    if e_val >= 128:                         # |sum| >= 2^128 -> infinity
        return 0xFF800000 if neg else 0x7F800000
    if e_val < -126:
        # subnormal: scale to 2^-149 units, truncate toward zero
        shift = e_val + 149
        if shift < 0:
            return 0x80000000 if neg else 0x00000000
        m = t >> shift
        if m == 0:
            return 0x80000000 if neg else 0x00000000
        return (0x80000000 if neg else 0) | m
    # normal: RZ keep 23 mantissa bits (drop bits below bit 23)
    if bl >= 24:
        m = (t >> (bl - 24)) & 0x7FFFFF      # top 23 mantissa bits (strip lead 1)
    else:
        m = (t << (24 - bl)) & 0x7FFFFF      # value < 2^0: left-fill to bit 23
    return (0x80000000 if neg else 0) | ((e_val + 127) << 23) | m


def frag_pairs(frag16):
    """m16n8k16 fragment (16 words: a0..a3, b0..b1, c0..c3) -> k-pair lists.

    Layout (probed on hardware): D0 and D1 share one set of 16 k-pairs,
    D2 and D3 share another.  Each (a-slot, b-slot) pair is repeated 4x
    (the four k values the hardware folds into one bf16 slot):

      D0/D1: {a0.lo,b0.lo}x4 {a0.hi,b0.hi}x4 {a2.lo,b1.lo}x4 {a2.hi,b1.hi}x4
      D2/D3: {a1.lo,b0.lo}x4 {a1.hi,b0.hi}x4 {a3.lo,b1.lo}x4 {a3.hi,b1.hi}x4

    Returns (c0,c1,c2,c3, P_pairs, Q_pairs) where each _pairs is a flat
    [a,b,a,b,...] list of 16 k-pairs (half-precision bit values).
    """
    a = [frag16[i] for i in range(4)]
    b = [frag16[4], frag16[5]]
    al = [a[i] & 0xFFFF for i in range(4)]
    ah = [a[i] >> 16 for i in range(4)]
    b0l, b0h = b[0] & 0xFFFF, b[0] >> 16
    b1l, b1h = b[1] & 0xFFFF, b[1] >> 16
    P = ([al[0], b0l] * 4 + [ah[0], b0h] * 4 +
         [al[2], b1l] * 4 + [ah[2], b1h] * 4)
    Q = ([al[1], b0l] * 4 + [ah[1], b0h] * 4 +
         [al[3], b1l] * 4 + [ah[3], b1h] * 4)
    return frag16[8], frag16[9], frag16[10], frag16[11], P, Q


def hmma_frag(frag16, fmt="bf16"):
    """Compute D0..D3 for a full m16n8k16 fragment (16 words), as FP32 bits."""
    c0, c1, c2, c3, P, Q = frag_pairs(frag16)
    A = [P[i] for i in range(0, len(P), 2)]
    B = [P[i] for i in range(1, len(P), 2)]
    A2 = [Q[i] for i in range(0, len(Q), 2)]
    B2 = [Q[i] for i in range(1, len(Q), 2)]
    return [fda(c0, A, B, fmt), fda(c1, A, B, fmt),
            fda(c2, A2, B2, fmt), fda(c3, A2, B2, fmt)]


def qmma_frag_pairs(frag16):
    """m16n8k32 fp8 fragment (16 words: a0..a3, b0..b1, c0..c3) -> k-pairs.

    Each a/b word holds 4 fp8 values (byte i, little-endian).  Probed on SM120:
    fp8 byte i pairs only with byte i (no cross-byte), each pair folds 4 k.

      D0/D1: {a0.i,b0.i} {a2.i,b1.i}  for i in 0..3   (8 pairs x 4k = 32k)
      D2/D3: {a1.i,b0.i} {a3.i,b1.i}  for i in 0..3

    Returns (c0,c1,c2,c3, P_pairs, Q_pairs) with flat [a,b,a,b,...] of 8
    fp8 k-pairs each.
    """
    a = [frag16[i] for i in range(4)]
    b = [frag16[4], frag16[5]]
    ai = [[(a[i] >> (8 * j)) & 0xFF for j in range(4)] for i in range(4)]
    bi = [[(b[i] >> (8 * j)) & 0xFF for j in range(4)] for i in range(2)]
    P = []
    Q = []
    for j in range(4):
        P += [ai[0][j], bi[0][j]] * 4 + [ai[2][j], bi[1][j]] * 4
        Q += [ai[1][j], bi[0][j]] * 4 + [ai[3][j], bi[1][j]] * 4
    return frag16[8], frag16[9], frag16[10], frag16[11], P, Q


def qmma_frag(frag16):
    """Compute D0..D3 for a full m16n8k32 e4m3 fragment, as FP32 bits."""
    c0, c1, c2, c3, P, Q = qmma_frag_pairs(frag16)
    A = [P[i] for i in range(0, len(P), 2)]
    B = [P[i] for i in range(1, len(P), 2)]
    A2 = [Q[i] for i in range(0, len(Q), 2)]
    B2 = [Q[i] for i in range(1, len(Q), 2)]
    return [fda(c0, A, B, "e4m3"), fda(c1, A, B, "e4m3"),
            fda(c2, A2, B2, "e4m3"), fda(c3, A2, B2, "e4m3")]


# ---- self-test against hardware-verified vectors ---------------------------
def _check(name, got, want):
    ok = got == want
    print(f"{'ok ' if ok else 'FAIL'} {name:<42} {got:#x} (exp {want:#x})")
    return ok


def selftest():
    ok = True
    B = "bf16"
    F16 = "f16"
    ONE_B = 0x3F80
    ONE_F = 0x3C00
    a1 = [ONE_B] * 4
    b3340 = [0x3340] * 4        # bf16 3*2^-26
    ok &= _check("bf16 c=1.0 + 3*2^-24 (RZ -> 1ulp)",
                 fda(0x3F800000, a1, b3340, B), 0x3F800001)
    ok &= _check("bf16 c=-1.0 + 3*2^-24 (RZ -> 1ulp)",
                 fda(0xBF800000, a1, b3340, B), 0xBF7FFFFE)
    ok &= _check("bf16 c=0 + 3*2^-24 exact",
                 fda(0, a1, b3340, B), 0x34400000)
    ok &= _check("bf16 c=2^20 + P=8",
                 fda(0x49800000, a1, [0x4000] * 4, B), 0x49800040)
    ok &= _check("c=NaN -> canonical", fda(0x7FC00000, a1, b3340, B), 0x7FFFFFFF)
    ok &= _check("a=NaN", fda(0, [0x7FC0] + [ONE_B] * 3, b3340, B), 0x7FFFFFFF)
    ok &= _check("0*inf -> NaN", fda(0, [0] * 4, [0x7F80] * 4, B), 0x7FFFFFFF)
    ok &= _check("+inf*-inf -> -inf", fda(0, [0x7F80, ONE_B, ONE_B, ONE_B],
                                          [0xFF80, 0, 0, 0], B), 0xFF800000)
    ok &= _check("mixed +inf/-inf -> NaN", fda(0, [0x7F80, 0x7F80, 0, 0],
                                               [0x7F80, 0xFF80, 0, 0], B), 0x7FFFFFFF)
    ok &= _check("c=+inf -> +inf", fda(0x7F800000, a1, b3340, B), 0x7F800000)
    ok &= _check("c=-inf -> -inf", fda(0xFF800000, a1, b3340, B), 0xFF800000)
    # c's inf joins the sign mix: c=-inf + product +inf -> NaN
    ok &= _check("c=-inf + prod +inf -> NaN",
                 fda(0xFF800000, [0x7F80] * 4, [0x7F80] * 4, B), 0x7FFFFFFF)
    # negative finite * +inf -> -inf (product sign)
    ok &= _check("neg * +inf -> -inf",
                 fda(0, [0xBF80, ONE_B, ONE_B, ONE_B], [0x7F80, 0, 0, 0], B), 0xFF800000)
    ok &= _check("f16 c=1.0 + 3*2^-22 (subnormal b=3*2^-24)",
                 fda(0x3F800000, [ONE_F] * 4, [0x0003] * 4, F16), 0x3F800006)
    ok &= _check("product overflow -> +inf",
                 fda(0, [0x7F80] * 4, [0x7F80] * 4, B), 0x7F800000)
    ok &= _check("f16 subnormal 2^-24 * 4 = 2^-22",
                 fda(0, [ONE_F] * 4, [0x0001] * 4, F16), 0x34800000)
    # ---- QMMA m16n8k32 e4m3 (via fragment layout) ------------------------
    def fiv(v): return struct.unpack("<I", struct.pack("<f", v))[0]
    qf = [0] * 16
    for i in range(6):
        qf[i] = 0x38383838                     # fp8 e4m3 1.0 x4
    for i in range(4):
        qf[8 + i] = fiv(float([10, 11, 12, 13][i]))
    ok &= _check("qmma A=B=1 -> 42,43,44,45",
                 qmma_frag(qf)[0], 0x42280000)
    ok &= _check("qmma A=B=1 D1", qmma_frag(qf)[1], 0x422C0000)
    ok &= _check("qmma A=B=1 D2", qmma_frag(qf)[2], 0x42300000)
    ok &= _check("qmma A=B=1 D3", qmma_frag(qf)[3], 0x42340000)
    # RZ: c0 = 1.0 + 3*2^-22 (0x3F800006), P=4 -> D0 = 5.0 + 1.5ulp -> 1ulp
    qf2 = [0] * 16
    qf2[0], qf2[4], qf2[8] = 0x38, 0x38, 0x3F800006
    ok &= _check("qmma RZ 1.5ulp -> 1ulp", qmma_frag(qf2)[0], 0x40A00001)
    # F=25: c0 = 1.0 + 2^-14, P=4 -> 5.0 + 2^-14 (0x40A00080)
    qf3 = [0] * 16
    qf3[0], qf3[4], qf3[8] = 0x38, 0x38, 0x3F800200
    ok &= _check("qmma F=25 (5.0+2^-14)", qmma_frag(qf3)[0], 0x40A00080)
    # fp8 NaN (0x7F all-ones) -> canonical; exp-15 mant<7 is an ordinary value
    ok &= _check("qmma fp8 NaN -> canonical",
                 qmma_frag([0x7F, 0, 0, 0, 0x38, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])[0],
                 0x7FFFFFFF)
    ok &= _check("qmma fp8 0x7C = 384 (exp15 value)",
                 qmma_frag([0x7C, 0, 0, 0, 0x38, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])[0],
                 0x44C00000)
    print(f"\nFDA self-test: {'ALL PASS' if ok else 'FAILURES'}")
    return ok


if __name__ == "__main__":
    selftest()
