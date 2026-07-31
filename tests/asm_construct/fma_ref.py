"""Bit-exact IEEE-754 binary32 fused multiply-add reference (pure Python).

Used to verify SASS FFMA semantics on SM120 against the ISA:
    Rd = round(Ra * Rb + Rc)

The exact sum Ra*Rb+Rc is computed with big integers (no intermediate
rounding), then rounded once to binary32 under the requested rounding
direction.  Flush-to-zero / flush-multiply-input behaviours are modelled
with independent knobs so the SASS-only .FMZ modifier (which has no PTX
equivalent) can be pinned down empirically.

Rounding-direction attribute for the final round (IEEE 754-2019 4.3.3):
    RN  roundTiesToEven   tie -> even mantissa
    RM  roundTowardNegative
    RP  roundTowardPositive
    RZ  roundTowardZero

Zero-sign rule (IEEE 754-2019 5.4.2 fusedMultiplyAdd): when the exact
result is zero, the sign is +0 except under roundTowardNegative (-0).
Two zeros with opposite signs sum to +0 (RN/RZ/RP) or -0 (RM).
"""

PDEN = -149   # exponent of the denormal grid (ULP = 2^-149)
BITS = 24     # binary32 significand precision
MIN_EXP = -126


def is_denorm_bits(x: int) -> bool:
    return (x & 0x7F800000) == 0 and (x & 0x007FFFFF) != 0


def _split(x: int):
    """Return (sign, infinite, nan, mag, scale) where |x| = mag * 2^scale."""
    s = (x >> 31) & 1
    e = (x >> 23) & 0xFF
    f = x & 0x7FFFFF
    if e == 0xFF:
        return s, f == 0, f != 0, 0, 0
    if e == 0:
        if f == 0:
            return s, False, False, 0, 0
        return s, False, False, f, PDEN
    return s, False, False, (1 << 23) | f, e - 127 - 23


def _overflow(sign: int, rnd: str) -> int:
    if rnd == "RN" or (rnd == "RM" and sign) or (rnd == "RP" and not sign):
        return (sign << 31) | 0x7F800000          # infinity
    return (sign << 31) | 0x7F7FFFFF              # clamp to max finite


def _round(T: int, ps: int, rnd: str, flush_out: bool) -> int:
    """Round signed big-int T (value = T * 2^ps) to binary32 under `rnd`."""
    sign = T < 0
    t = abs(T)
    L = t.bit_length() - 1 + ps      # exponent of the leading bit

    if L > 127:
        return _overflow(sign, rnd)  # |value| >= 2^128

    # rounding grid: 24 significant bits for normals, 2^-149 for denormals
    g = L - (BITS - 1) if L >= MIN_EXP else PDEN

    if ps < g:
        q = g - ps
        keep = t >> q
        rem = t & ((1 << q) - 1)
        half = 1 << (q - 1)
        if rnd == "RN":
            if rem > half:
                keep += 1
            elif rem == half:
                keep += keep & 1
        elif rnd == "RM":
            if sign and rem:
                keep += 1
        elif rnd == "RP":
            if not sign and rem:
                keep += 1
        # RZ: truncate toward zero
    else:
        keep = t                     # already exact on the grid

    if keep >= (1 << BITS):
        # carry out of rounding: normal mantissa bumped to 2^24
        if L == 127:
            return _overflow(sign, rnd)  # 2^127 grid carry -> 2^128
        keep >>= 1
        g += 1
        L += 1

    if keep == 0:
        return sign << 31            # denormal rounded down to zero

    # flush a denormal output to sign-preserving zero (.FTZ / .FMZ hypothesis)
    if flush_out and L < MIN_EXP:
        return sign << 31

    if keep >= (1 << 23):            # normal result
        exp8 = L + 127
        return (sign << 31) | (exp8 << 23) | (keep & 0x7FFFFF)
    return (sign << 31) | keep       # denormal result: keep * 2^-149


def fma32(a: int, b: int, c: int, rnd: str = "RN",
          ftz: bool = False, **flush) -> int:
    """SASS FFMA semantic model.  Inputs/outputs are raw binary32 bit fields.

    rnd in {RN,RM,RP,RZ}.  ftz = SASS .FTZ (flush all denormal inputs and a
    denormal result).  Extra **flush knobs (flush_a/b/c/out) implement .FMZ
    hypotheses; by default (.FMZ) nothing is flushed.
    """
    if ftz:
        flush.setdefault("flush_a", True)
        flush.setdefault("flush_b", True)
        flush.setdefault("flush_c", True)
        flush.setdefault("flush_out", True)

    if flush.get("flush_a"):
        a = a & 0x80000000 if is_denorm_bits(a) else a
    if flush.get("flush_b"):
        b = b & 0x80000000 if is_denorm_bits(b) else b
    if flush.get("flush_c"):
        c = c & 0x80000000 if is_denorm_bits(c) else c

    sa, ai, an, ma, pa = _split(a)
    sb, bi, bn, mb, pb = _split(b)
    sc, ci, cn, mc, pc = _split(c)

    if an or bn or cn:
        return 0x7FFFFFFF            # canonical NaN (NVIDIA: all-1 mantissa)

    # ---- multiply specials (inf / zero) --------------------------------
    if ai or bi:
        if (ai and mb == 0) or (bi and ma == 0):
            return 0x7FFFFFFF        # inf * 0 -> NaN
        sprod = sa ^ sb
        if ci:
            return 0x7FFFFFFF if sc != sprod \
                else (sprod << 31) | 0x7F800000
        return (sprod << 31) | 0x7F800000
    if ci:
        return (sc << 31) | 0x7F800000
    if ma == 0:
        if mc == 0:                  # sum of two zeros
            if (sa ^ sb) == sc:
                return sc << 31
            return 0 if rnd != "RM" else 0x80000000
        return c                     # 0 + c = c

    # ---- exact sum: value = T * 2^ps (big-int, single rounding) --------
    sprod = sa ^ sb
    ps = min(pa + pb, pc)
    T = (1 if sprod == 0 else -1) * (ma * mb << (pa + pb - ps)) \
        + (1 if sc == 0 else -1) * (mc << (pc - ps))

    if T == 0:                       # exact cancellation (both non-zero)
        return 0 if rnd != "RM" else 0x80000000
    return _round(T, ps, rnd, bool(flush.get("flush_out")))


def pack_split(sign: int, mag: int, scale: int) -> int:
    """Re-encode |value| = mag * 2^scale (normal/denormal) as binary32."""
    if mag == 0:
        return sign << 31
    L = mag.bit_length() - 1 + scale
    if L < MIN_EXP:
        # denormal
        shift = PDEN - scale
        if shift > 0:
            mag >>= shift
        return (sign << 31) | (mag & 0x7FFFFF)
    # normal (exact, no rounding here)
    exp8 = L + 127
    mant = (mag << (23 - (mag.bit_length() - 1))) & 0x7FFFFF
    return (sign << 31) | (exp8 << 23) | mant
