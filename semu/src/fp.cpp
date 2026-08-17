// Bit-exact FP semantics (SIM_PLAN Phase 5).  See fp.hpp.
//
// This translation unit computes FP results under a dynamic rounding mode
// (via fesetround).  The -frounding-math build flag (see
// semu/src/CMakeLists.txt) is the compile contract that keeps the compiler
// from constant-folding or reassociating away the rounding dependence.
// `#pragma STDC FENV_ACCESS ON` is the C99 contract; GCC < 13 warns on it,
// so it is enabled only on compilers that accept it (Clang).
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#endif

#include <semu/fp.hpp>

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace semu::fp {
namespace {

std::uint32_t bits_of(float f) {
    std::uint32_t b;
    std::memcpy(&b, &f, 4);
    return b;
}
float float_of(std::uint32_t b) {
    float f;
    std::memcpy(&f, &b, 4);
    return f;
}
std::uint64_t bits_of(double d) {
    std::uint64_t b;
    std::memcpy(&b, &d, 8);
    return b;
}
double double_of(std::uint64_t b) {
    double d;
    std::memcpy(&d, &b, 8);
    return d;
}

int fenv_of(Rnd rnd) {
    switch (rnd) {
        case Rnd::kRn: return FE_TONEAREST;
        case Rnd::kRz: return FE_TOWARDZERO;
        case Rnd::kRm: return FE_DOWNWARD;
        case Rnd::kRp: return FE_UPWARD;
        default: return FE_TONEAREST;
    }
}

constexpr std::uint32_t kF32ExpMask = 0x7f800000;
constexpr std::uint32_t kF32FracMask = 0x007fffff;
constexpr std::uint64_t kF64ExpMask = 0x7ff0000000000000ULL;
constexpr std::uint64_t kF64FracMask = 0x000fffffffffffffULL;

}  // namespace

int push_rounding(Rnd rnd) {
    const int saved = std::fegetround();
    std::fesetround(fenv_of(rnd));
    return saved;
}

void pop_rounding(int saved) { std::fesetround(saved); }

std::uint32_t flush_f32(std::uint32_t bits) {
    if ((bits & kF32ExpMask) == 0 && (bits & kF32FracMask) != 0) {
        // Subnormal: flush to signed zero.
        return bits & 0x80000000u;
    }
    return bits;
}

std::uint64_t flush_f64(std::uint64_t bits) {
    if ((bits & kF64ExpMask) == 0 && (bits & kF64FracMask) != 0) {
        return bits & 0x8000000000000000ULL;
    }
    return bits;
}

std::uint32_t sat_f32(std::uint32_t bits) {
    // Clamp to [0,1] (verified sm120): NaN and negative clamp to +0, >1 to
    // 1.0, +inf to 1.0, -inf to +0; -0 is normalised to +0.
    const float f = float_of(bits);
    if (std::isnan(f)) return 0;
    if (f == 0.0f) return 0;  // -0 -> +0
    const float s = f < 0.0f ? 0.0f : (f > 1.0f ? 1.0f : f);
    return bits_of(s);
}

std::uint64_t sat_f64(std::uint64_t bits) {
    const double d = double_of(bits);
    if (std::isnan(d)) return 0;
    if (d == 0.0) return 0;  // -0 -> +0
    const double s = d < 0.0 ? 0.0 : (d > 1.0 ? 1.0 : d);
    return bits_of(s);
}

std::uint32_t fadd(std::uint32_t a, std::uint32_t b, Rnd rnd, bool flush,
                   bool sat) {
    if (flush) {
        a = flush_f32(a);
        b = flush_f32(b);
    }
    if (std::isnan(float_of(a)) || std::isnan(float_of(b))) {
        // SAT clamps NaN to +0 (verified sm120).
        return sat ? 0 : kCanonicalNan32;
    }
    const RoundingGuard rg(rnd);
    const float r = float_of(a) + float_of(b);
    // FTZ output: flush subnormal results to zero too.
    std::uint32_t out = bits_of(r);
    if (std::isnan(r)) out = kCanonicalNan32;
    if (flush) out = flush_f32(out);
    if (sat) out = sat_f32(out);
    return out;
}

std::uint32_t fmul(std::uint32_t a, std::uint32_t b, Rnd rnd, bool flush,
                   bool sat) {
    if (flush) {
        a = flush_f32(a);
        b = flush_f32(b);
    }
    if (std::isnan(float_of(a)) || std::isnan(float_of(b))) {
        return sat ? 0 : kCanonicalNan32;
    }
    const RoundingGuard rg(rnd);
    const float r = float_of(a) * float_of(b);
    std::uint32_t out = bits_of(r);
    if (std::isnan(r)) out = kCanonicalNan32;
    if (flush) out = flush_f32(out);
    if (sat) out = sat_f32(out);
    return out;
}

std::uint32_t ffma(std::uint32_t a, std::uint32_t b, std::uint32_t c,
                   Rnd rnd, bool fmz, bool sat) {
    // FMZ/FTZ on FFMA flushes ALL THREE denormal inputs (multiply inputs and
    // addend) sign-preserving (verified matrix on sm120: denormal a/b/c each
    // become signed zero).  A denormal RESULT flushes to zero with a sign
    // that depends on rounding: RN/RP/RZ -> +0, RM -> result sign.
    if (fmz) {
        a = flush_f32(a);
        b = flush_f32(b);
        c = flush_f32(c);
    }
    if (std::isnan(float_of(a)) || std::isnan(float_of(b)) ||
        std::isnan(float_of(c))) {
        return sat ? 0 : kCanonicalNan32;
    }
    const RoundingGuard rg(rnd);
    const float r = std::fma(float_of(a), float_of(b), float_of(c));
    std::uint32_t out = bits_of(r);
    if (std::isnan(r)) out = kCanonicalNan32;
    if (fmz && (out & kF32ExpMask) == 0) {
        // Under FTZ, a denormal or zero result flushes: RN/RP/RZ -> +0;
        // RM -> the flushed addend's sign (verified on sm120: the sign of a
        // zero result tracks the addend c under RM, e.g.
        // FFMA.RM.FMZ(+0,-b,+0)=+0 but FFMA.RM.FMZ(+0,+b,-0)=-0).
        out = (rnd == Rnd::kRm) ? (c & 0x80000000u) : 0;
    }
    if (sat) out = sat_f32(out);
    return out;
}

// Pick the FP64 NaN result.  Verified on sm120:
//   DMUL(NaN1, x)     -> NaN1
//   DMUL(x, NaN2)     -> NaN2
//   DMUL(NaN1, NaN2)  -> NaN2 (second operand wins among two NaNs)
std::uint64_t pick_nan64(std::uint64_t a, std::uint64_t b,
                         std::uint64_t c = 0) {
    const bool an = std::isnan(double_of(a));
    const bool bn = std::isnan(double_of(b));
    const bool cn = std::isnan(double_of(c));
    if (cn) return c;
    if (bn) return b;
    if (an) return a;
    return a;  // unreachable
}

std::uint64_t fadd64(std::uint64_t a, std::uint64_t b, Rnd rnd, bool sat) {
    if (std::isnan(double_of(a)) || std::isnan(double_of(b))) {
        return sat ? 0 : pick_nan64(a, b);
    }
    const RoundingGuard rg(rnd);
    const double r = double_of(a) + double_of(b);
    std::uint64_t out = bits_of(r);
    if (std::isnan(r)) out = pick_nan64(a, b);
    if (sat) out = sat_f64(out);
    return out;
}

std::uint64_t fmul64(std::uint64_t a, std::uint64_t b, Rnd rnd, bool sat) {
    if (std::isnan(double_of(a)) || std::isnan(double_of(b))) {
        return sat ? 0 : pick_nan64(a, b);
    }
    const RoundingGuard rg(rnd);
    const double r = double_of(a) * double_of(b);
    std::uint64_t out = bits_of(r);
    if (std::isnan(r)) out = pick_nan64(a, b);
    if (sat) out = sat_f64(out);
    return out;
}

std::uint64_t fma64(std::uint64_t a, std::uint64_t b, std::uint64_t c,
                    Rnd rnd, bool sat) {
    if (std::isnan(double_of(a)) || std::isnan(double_of(b)) ||
        std::isnan(double_of(c))) {
        return sat ? 0 : pick_nan64(a, b, c);
    }
    const RoundingGuard rg(rnd);
    const double r = std::fma(double_of(a), double_of(b), double_of(c));
    std::uint64_t out = bits_of(r);
    if (std::isnan(r)) out = pick_nan64(a, b, c);
    if (sat) out = sat_f64(out);
    return out;
}

// --- conversions ----------------------------------------------------------

// SASS format enums for F2F/F2I/I2F.
constexpr int kFmtF16 = 0;
constexpr int kFmtF32 = 1;
constexpr int kFmtF64 = 2;
constexpr int kFmtBf16 = 3;
constexpr int kFmtU32 = 4;
constexpr int kFmtS32 = 5;
constexpr int kFmtU16 = 6;
constexpr int kFmtS16 = 7;
constexpr int kFmtU8 = 8;
constexpr int kFmtS8 = 9;

// Round fp32 to fp16 (RN/RZ/RM/RP) returning the 16-bit half pattern.
// Implements IEEE-754 directed rounding with full discarded-bit accounting,
// including the subnormal fp16 path (values < 2^-14).  Verified against the
// GPU in tools/diff_phase5.py over FP16 subnormal boundaries.
std::uint16_t f32_to_f16(std::uint32_t bits, Rnd rnd, bool ftz) {
    if (ftz) bits = flush_f32(bits);
    // f16 sign lives at bit 15 (not the f32's bit 31).
    const std::uint32_t sign = (bits & 0x80000000u) >> 16;
    const std::uint32_t exp = (bits >> 23) & 0xff;
    const std::uint32_t frac = bits & 0x7fffffu;
    const bool negative = sign != 0;

    if (exp == 0xff) {  // inf / nan
        if (frac != 0) return static_cast<std::uint16_t>(sign | 0x7e00u);
        return static_cast<std::uint16_t>(sign | 0x7c00u);
    }
    if (exp == 0 && frac == 0) return static_cast<std::uint16_t>(sign);  // +/-0

    // Full 24-bit mantissa; value = M * 2^(E-150).
    const std::uint32_t M = exp ? (0x800000u | frac) : frac;
    const int E = static_cast<int>(exp);

    // Rounding decision from the discarded bits `rem` (0 <= rem < 2^shift)
    // vs the halfway value `half = 2^(shift-1)`, given the retained value's
    // parity (for ties-to-even).  Returns true when retained increments.
    auto round_up = [&](std::uint32_t rem, std::uint32_t half,
                        bool retained_odd) -> bool {
        switch (rnd) {
            case Rnd::kRn: return rem > half || (rem == half && retained_odd);
            case Rnd::kRz: return false;
            case Rnd::kRm: return negative && rem != 0;
            case Rnd::kRp: return !negative && rem != 0;
            default: return false;
        }
    };

    // Overflow helper: value >= 2^16 (or rounds up to it).
    auto overflow_result = [&]() -> std::uint16_t {
        // RN and away-from-sign-rounding overflow to inf; the opposite
        // directed mode saturates to the max finite fp16 (65504).
        const bool to_inf = (rnd == Rnd::kRn) ||
                            (rnd == Rnd::kRp && !negative) ||
                            (rnd == Rnd::kRm && negative);
        return static_cast<std::uint16_t>(sign | (to_inf ? 0x7c00u : 0x7bffu));
    };

    // fp16 exponent field ef: value = 1.f * 2^(ef-15).  ef = E - 112.
    const int ef = E - 112;
    if (ef >= 31) return overflow_result();

    if (ef >= 1) {
        // Normal fp16: keep 10 explicit fraction bits out of 23.
        const int shift = 23 - 10;
        std::uint32_t retained = M >> shift;  // 11 bits (implicit 1 + 10 frac)
        const std::uint32_t rem = M & ((1u << shift) - 1u);
        if (round_up(rem, 1u << (shift - 1), retained & 1u)) {
            ++retained;
            if (retained == 0x800u) {  // fraction overflow -> exponent bump
                if (ef + 1 >= 31) return overflow_result();
                return static_cast<std::uint16_t>(sign |
                                                  ((ef + 1) << 10));
            }
        }
        return static_cast<std::uint16_t>(sign | (ef << 10) |
                                          (retained & 0x3ffu));
    }

    // Subnormal or zero: value < 2^-14.  fp16 subnormal m (0..1023) = m*2^-24,
    // so m = value*2^24 = M*2^(E-126).  sh = 126 - E (>= 14 for E <= 112).
    const int sh = 126 - E;
    std::uint32_t retained = (sh >= 24) ? 0 : (M >> sh);
    std::uint32_t rem = (sh >= 24) ? M : (M & ((1u << sh) - 1u));
    bool carry = false;
    if (rnd == Rnd::kRn) {
        // half = 2^(sh-1).  For sh >= 26, half >= 2^25 > rem (rem < 2^24),
        // so the value is below the halfway point and never rounds up.
        if (sh <= 25) {
            carry = round_up(rem, 1u << (sh - 1), retained & 1u);
        }
    } else {
        carry = round_up(rem, 0, retained & 1u);  // RZ never carries; RM/RP
    }
    if (carry) ++retained;
    if (retained == 1024u) {
        // Rounded up to the smallest normal fp16 (2^-14, ef=1, frac=0).
        return static_cast<std::uint16_t>(sign | 0x400u);
    }
    return static_cast<std::uint16_t>(sign | retained);
}

std::uint32_t f16_to_f32(std::uint16_t half) {
    const std::uint32_t sign = (half & 0x8000u) << 16;
    const std::uint32_t exp = (half >> 10) & 0x1f;
    const std::uint32_t frac = half & 0x3ffu;
    if (exp == 0x1f) {
        if (frac != 0) return kCanonicalNan32;   // NaN (canonicalized)
        return sign | 0x7f800000u;                 // inf
    }
    if (exp == 0) {
        if (frac == 0) return sign;  // +/-0
        // subnormal half -> normal f32
        int e = -14;
        std::uint32_t m = frac;
        while (!(m & 0x400u)) { m <<= 1; --e; }
        m &= 0x3ffu;
        const std::uint32_t f32exp = static_cast<std::uint32_t>(e + 127);
        return sign | (f32exp << 23) | (m << 13);
    }
    return sign | ((exp + 112) << 23) | (frac << 13);
}

std::uint32_t f32_to_bf16(std::uint32_t bits, Rnd rnd, bool ftz) {
    if (ftz) bits = flush_f32(bits);
    // BF16 = top 16 bits of fp32 (RN by default on modern HW).
    (void)rnd;
    const std::uint32_t lower = bits & 0xffffu;
    std::uint32_t hi = bits >> 16;
    const std::uint32_t halfway = 0x8000u;
    const bool sign = (bits & 0x80000000u) != 0;
    switch (rnd) {
        case Rnd::kRn:
            if (lower > halfway || (lower == halfway && (hi & 1))) {
                hi = (bits + 0x8000u) >> 16;
            }
            break;
        case Rnd::kRz: break;
        case Rnd::kRm:
            if (sign && lower != 0) hi++;
            break;
        case Rnd::kRp:
            if (!sign && lower != 0) hi++;
            break;
        default: break;
    }
    if (hi > 0x7f800000u) hi = 0x7f800000u;  // inf clamp
    return hi;
}

std::uint32_t f2f(std::uint32_t src_bits, int dstfmt, int srcfmt, Rnd rnd,
                  bool ftz, bool sat) {
    (void)dstfmt;
    if (srcfmt == kFmtF32 && dstfmt == kFmtF32) {
        std::uint32_t r = ftz ? flush_f32(src_bits) : src_bits;
        return sat ? sat_f32(r) : r;
    }
    if (srcfmt == kFmtF32 && dstfmt == kFmtF64) {
        // f32 -> f64 exact.
        std::uint32_t s = ftz ? flush_f32(src_bits) : src_bits;
        std::uint64_t d = bits_of(static_cast<double>(float_of(s)));
        return static_cast<std::uint32_t>(d >> 32);
    }
    if (srcfmt == kFmtF32 && dstfmt == kFmtF16) {
        return f32_to_f16(src_bits, rnd, ftz);
    }
    if (srcfmt == kFmtF32 && dstfmt == kFmtBf16) {
        return f32_to_bf16(src_bits, rnd, ftz);
    }
    if (srcfmt == kFmtF16 && dstfmt == kFmtF32) {
        return f16_to_f32(static_cast<std::uint16_t>(src_bits & 0xffffu));
    }
    if (srcfmt == kFmtBf16 && dstfmt == kFmtF32) {
        // BF16 lives in the low 16 bits; F32 result zero-extends it
        // (verified: F2F.F32.BF16 0xBF80 -> 0xBF800000).  BF16 NaN/inf map
        // to the F32 NaN (canonical) / inf.
        const std::uint32_t bf = src_bits & 0xffffu;
        const std::uint32_t exp = (bf >> 7) & 0xff;
        if (exp == 0xff) {
            if (bf & 0x7f) return kCanonicalNan32;
            return (bf & 0x8000u) ? 0xff800000u : 0x7f800000u;
        }
        return bf << 16;
    }
    if (srcfmt == kFmtF16 && dstfmt == kFmtF16) return src_bits & 0xffffu;
    if (srcfmt == kFmtBf16 && dstfmt == kFmtBf16) {
        return src_bits & 0xffff0000u;
    }
    // Unsupported combination: return a canonical NaN.
    return 0x7fc00000u;
}

std::uint64_t f2f64(std::uint32_t src_bits, int dstfmt, int srcfmt, Rnd rnd,
                    bool ftz, bool sat) {
    (void)dstfmt;
    (void)rnd;
    // Used when dstfmt == F64.  f32->f64 exact; f16/bf16->f64 via f32.
    std::uint32_t f32 = src_bits;
    if (srcfmt == kFmtF16) f32 = f16_to_f32(static_cast<std::uint16_t>(src_bits & 0xffffu));
    if (srcfmt == kFmtBf16) f32 = src_bits & 0xffff0000u;
    if (ftz) f32 = flush_f32(f32);
    std::uint64_t out = bits_of(static_cast<double>(float_of(f32)));
    if (sat) out = sat_f64(out);
    return out;
}

std::uint64_t i2f(std::uint64_t src, int dstfmt, int srcfmt, Rnd rnd,
                  bool sat) {
    (void)srcfmt;
    // srcfmt: U32/S32 (also U16/S16/U8/S8); dstfmt: F32/F64/F16/BF16.
    const RoundingGuard rg(rnd);
    double dv = 0;
    if (srcfmt == kFmtU32) dv = static_cast<double>(static_cast<std::uint32_t>(src));
    else if (srcfmt == kFmtS32) dv = static_cast<double>(static_cast<std::int32_t>(src));
    else if (srcfmt == kFmtU16) dv = static_cast<double>(static_cast<std::uint16_t>(src));
    else if (srcfmt == kFmtS16) dv = static_cast<double>(static_cast<std::int16_t>(src));
    else if (srcfmt == kFmtU8) dv = static_cast<double>(static_cast<std::uint8_t>(src));
    else if (srcfmt == kFmtS8) dv = static_cast<double>(static_cast<std::int8_t>(src));
    else dv = static_cast<double>(static_cast<std::uint32_t>(src));
    if (dstfmt == kFmtF64) {
        std::uint64_t out = bits_of(dv);
        if (sat) out = sat_f64(out);
        return out;
    }
    if (dstfmt == kFmtF16) {
        std::uint32_t f32 = bits_of(static_cast<float>(dv));
        return f32_to_f16(f32, rnd, false);
    }
    if (dstfmt == kFmtBf16) {
        std::uint32_t f32 = bits_of(static_cast<float>(dv));
        return f32_to_bf16(f32, rnd, false);
    }
    std::uint32_t out = bits_of(static_cast<float>(dv));
    if (sat) out = sat_f32(out);
    return out;
}

std::uint64_t f2i(std::uint32_t src_bits, int dstfmt, int srcfmt, Rnd rnd,
                  bool ftz, bool ntz) {
    (void)ntz;
    (void)srcfmt;
    if (ftz) src_bits = flush_f32(src_bits);
    const float f = float_of(src_bits);
    // NaN -> 0x80000000 for every dst/mode (verified on sm120).  Inf
    // saturates: +inf -> max (0xFFFFFFFF for U32, 0x7FFFFFFF for S32);
    // -inf -> min (0 for U32, 0x80000000 for S32).
    if (std::isnan(f)) return 0x80000000ULL;
    if (std::isinf(f)) {
        if (f > 0) {
            return (dstfmt == kFmtU32) ? 0xffffffffULL : 0x7fffffffULL;
        }
        return (dstfmt == kFmtU32) ? 0 : 0x80000000ULL;
    }
    const RoundingGuard rg(rnd);
    double d = static_cast<double>(f);
    // Clamp the double to the destination range BEFORE any int cast
    // (values beyond INT64/INT32 range would be UB in static_cast).
    std::int64_t iv = 0;
    const double dmax_s32 = 2147483647.0;
    const double dmin_s32 = -2147483648.0;
    const double dmax_u32 = 4294967295.0;
    const double dmin_u32 = 0.0;
    if (dstfmt == kFmtS32 || dstfmt == kFmtS16 || dstfmt == kFmtS8) {
        d = std::clamp(d, dmin_s32, dmax_s32);
    } else {
        d = std::clamp(d, dmin_u32, dmax_u32);
    }
    if (rnd == Rnd::kRz) iv = static_cast<std::int64_t>(std::trunc(d));
    else if (rnd == Rnd::kRn) iv = static_cast<std::int64_t>(std::nearbyint(d));
    else if (rnd == Rnd::kRm) iv = static_cast<std::int64_t>(std::floor(d));
    else if (rnd == Rnd::kRp) iv = static_cast<std::int64_t>(std::ceil(d));
    else iv = static_cast<std::int64_t>(std::trunc(d));
    // Clamp out-of-range results (F2I saturates).
    if (dstfmt == kFmtU32) {
        if (iv < 0) return 0;
        if (iv > 0xffffffffLL) return 0xffffffffULL;
    } else if (dstfmt == kFmtS32) {
        if (iv > 0x7fffffff) return 0x7fffffffULL;
        if (iv < -0x80000000LL) return 0x80000000ULL;
    }
    if (dstfmt == kFmtU32)
        return static_cast<std::uint32_t>(static_cast<std::uint64_t>(iv));
    if (dstfmt == kFmtS32) return static_cast<std::uint32_t>(iv);
    if (dstfmt == kFmtU16) return static_cast<std::uint16_t>(iv);
    if (dstfmt == kFmtS16) return static_cast<std::uint16_t>(iv);
    if (dstfmt == kFmtU8) return static_cast<std::uint8_t>(iv);
    if (dstfmt == kFmtS8) return static_cast<std::uint8_t>(iv);
    return static_cast<std::uint32_t>(iv);
}

// FP64 -> narrow float direct bit-pattern conversions (F64.F32 / F64.F16 /
// F64.BF16).  These round DIRECTLY from the FP64 sign/exponent/53-bit
// significand to the target precision — never through an FP32 intermediate
// (which would double-round).  `fmt` selects the target:
//   0 = FP16 (5-bit exp, 10-bit frac, bias 15, subnormal unit 2^-24)
//   1 = FP32 (8-bit exp, 23-bit frac, bias 127, subnormal unit 2^-149)
//   2 = BF16 (8-bit exp, 7-bit frac, bias 127, subnormal unit 2^-133)
// Returns the raw register pattern: FP32 in [31:0]; FP16/BF16 in [15:0].
std::uint32_t f64_down_round(std::uint64_t bits, Rnd rnd, int fmt,
                             bool ftz, bool sat) {
    const int frac_bits = (fmt == 0) ? 10 : (fmt == 2) ? 7 : 23;
    const int bias = (fmt == 0) ? 15 : 127;
    const int exp_bits = (fmt == 0) ? 5 : 8;
    const int max_exp = (1 << exp_bits) - 1;           // all-ones exp field
    const int max_norm = max_exp - 1;                  // largest normal
    const int sub_unit = 1 - bias - frac_bits;         // subnormal unit 2^..
    const bool negative = (bits >> 63) & 1;
    const int exp = static_cast<int>((bits >> 52) & 0x7FF);
    const std::uint64_t frac = bits & 0xFFFFFFFFFFFFFULL;

    auto sign_bit = [&]() -> std::uint32_t {
        // F32 keeps the sign at bit 31; F16/BF16 results live in bits [15:0]
        // with the sign at bit 15 (the high half stays zero).
        return negative ? (fmt == 1 ? 0x80000000u : 0x8000u) : 0;
    };
    // SAT finalize for a FINITE F32 target pattern: applied on every exit
    // (including zero, mantissa-carry and subnormal->smallest-normal paths,
    // which previously bypassed the clamp).  sm120 rules: +0 normalization
    // (-0 -> +0), >1 -> 1.0, negative -> +0.
    auto sat_final = [&](std::uint32_t out) -> std::uint32_t {
        if (!sat || fmt != 1) return out;
        return sat_f32(out);
    };
    auto overflow_result = [&]() -> std::uint32_t {
        // RN and away-from-sign overflow to inf; the opposite directed mode
        // saturates to max finite (65504 for FP16, 3.4e38 for FP32/BF16).
        // Under SAT (F32 only) any overflowed magnitude clamps: positive ->
        // 1.0, negative -> +0.
        if (sat && fmt == 1) return negative ? 0 : 0x3f800000u;
        const bool to_inf = (rnd == Rnd::kRn) ||
                            (rnd == Rnd::kRp && !negative) ||
                            (rnd == Rnd::kRm && negative);
        std::uint32_t inf = sign_bit() |
                            (static_cast<std::uint32_t>(max_exp) << frac_bits);
        std::uint32_t maxf = sign_bit() |
                             (static_cast<std::uint32_t>(max_norm) << frac_bits) |
                             ((1u << frac_bits) - 1);
        return to_inf ? inf : maxf;
    };

    if (exp == 0x7FF) {  // inf / nan
        if (frac != 0) {
            // F32 target preserves the F64 NaN payload: sign + all-ones exp +
            // (52-bit payload >> 29) with the quiet bit set (verified:
            // F32.F64(0x7ff123456789abcd) -> 0x7fc91a2b).  Under SAT a NaN
            // clamps to +0 (verified sm120 FADD/FFMA.SAT).
            if (fmt == 1) {
                std::uint32_t out = sign_bit() | (0x7f800000u) |
                       (static_cast<std::uint32_t>(frac >> 29) | 0x400000u);
                return sat ? 0 : out;
            }
            // F16/BF16 quiet NaN in the low 16 bits (SAT not applicable).
            return sign_bit() |
                   (static_cast<std::uint32_t>(max_exp) << frac_bits) |
                   (1u << (frac_bits - 1));  // quiet NaN payload
        }
        // Inf under SAT clamps: +inf -> 1.0, -inf -> +0 (sm120 verified).
        if (sat && fmt == 1) return negative ? 0 : 0x3f800000u;
        return sign_bit() | (static_cast<std::uint32_t>(max_exp) << frac_bits);
    }
    if (exp == 0 && frac == 0) return sat_final(sign_bit());  // +/-0 (SAT -> +0)

    // Normalize: subnormal f64 -> E=1, M=frac; normal -> E=exp, M=(1<<52)|frac.
    const std::uint64_t M = exp ? ((1ULL << 52) | frac) : frac;
    const int E = exp ? exp : 1;
    // value = M * 2^(E-1075).  Target normal exponent field ef = E-1023+bias.
    const int ef = E - 1023 + bias;

    // Directed-rounding carry from the discarded low bits.
    auto carry = [&](std::uint64_t rem, int shift, std::uint64_t m) -> bool {
        if (rnd == Rnd::kRn) {
            // For shift >= 64 the halfway value 2^(shift-1) exceeds the
            // 53-bit significand, so rem (<= 2^53-1) can never reach it and
            // there is no round-up (avoids 1ULL<<N UB for N >= 64).
            if (shift <= 0) return false;
            if (shift >= 64) return false;
            const std::uint64_t half = 1ULL << (shift - 1);
            return rem > half || (rem == half && (m & 1));
        }
        if (rnd == Rnd::kRz) return false;
        if (rnd == Rnd::kRm) return negative && rem != 0;
        return !negative && rem != 0;  // kRp
    };

    if (ef >= max_exp) return overflow_result();  // >= 2^(max_norm+1-bias)

    if (ef >= 1) {  // normal: keep (frac_bits+1) bits out of 53
        const int shift = 52 - frac_bits;
        std::uint64_t m = M >> shift;
        const std::uint64_t rem = M & ((1ULL << shift) - 1);
        if (carry(rem, shift, m)) {
            ++m;
            if (m == (1ULL << (frac_bits + 1))) {  // mantissa carry -> exp bump
                if (ef + 1 >= max_exp) return sat_final(overflow_result());
                return sat_final(sign_bit() |
                                 (static_cast<std::uint32_t>(ef + 1) << frac_bits));
            }
        }
        std::uint32_t out = sign_bit() |
                            (static_cast<std::uint32_t>(ef) << frac_bits) |
                            static_cast<std::uint32_t>(m & ((1u << frac_bits) - 1));
        return sat_final(out);
    }

    // Subnormal / zero: m = value / 2^sub_unit, where
    //   value = M * 2^(E-1075)  and  sub_unit = 1-bias-frac_bits.
    // So m = M * 2^(E-1075 - sub_unit); the integer part drops
    // m_shift = 1075 + sub_unit - E bits of M.
    const int m_shift = 1075 + sub_unit - E;
    std::uint64_t m;
    std::uint64_t rem;
    if (m_shift >= 53) {
        m = 0;
        rem = M;
    } else if (m_shift > 0) {
        m = M >> m_shift;
        rem = M & ((1ULL << m_shift) - 1);
    } else {  // m_shift <= 0 (value is an exact small multiple of the unit)
        m = M << (-m_shift);
        rem = 0;
    }
    if (carry(rem, m_shift > 0 ? m_shift : 0, m)) ++m;
    if (m >= (1ULL << frac_bits)) {
        // rounds up to the smallest normal (exp field 1, frac 0)
        return sat_final(sign_bit() | (1u << frac_bits));
    }
    std::uint32_t out = sign_bit() |
                        static_cast<std::uint32_t>(m & ((1u << frac_bits) - 1));
    // FTZ: a subnormal/zero target result flushes; RN/RP/RZ -> +0, RM keeps
    // the sign (sm120 rule).  F16/BF16 keep the sign at bit 15.
    if (ftz && (out & (static_cast<std::uint32_t>(max_exp) << frac_bits)) == 0) {
        out = (rnd == Rnd::kRm) ? (out & (fmt == 1 ? 0x80000000u : 0x8000u)) : 0;
    }
    return sat_final(out);
}

std::uint32_t f64_to_f32(std::uint64_t bits, Rnd rnd, bool ftz, bool sat) {
    return f64_down_round(bits, rnd, 1, ftz, sat);
}

std::uint32_t f64_to_f16(std::uint64_t bits, Rnd rnd, bool ftz, bool sat) {
    return f64_down_round(bits, rnd, 0, ftz, sat);
}

std::uint32_t f64_to_bf16(std::uint64_t bits, Rnd rnd, bool ftz, bool sat) {
    return f64_down_round(bits, rnd, 2, ftz, sat);
}

}  // namespace semu::fp
