// Fast FP leaf semantics (SIM_PLAN Phase 5.5).
//
// Native host float/double/std::fma under a run-scope round-to-nearest fenv.
// No per-instruction fegetround/fesetround/RoundingGuard.  Results are NOT
// sm_120 bit-exact; only the precise fp.cpp path is GPU-validated.

#include <semu/fp/fast_fp.hpp>

#include <bit>
#include <cmath>
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

}  // namespace

std::uint32_t fast_sat32(std::uint32_t bits) {
    const float f = float_of(bits);
    if (std::isnan(f) || f == 0.0f || f < 0.0f) return 0;
    if (f > 1.0f) return 0x3f800000u;  // +inf / >1 -> 1.0
    return bits;
}

std::uint32_t fast_fadd(std::uint32_t a, std::uint32_t b, int /*rnd*/,
                        bool /*ftz*/, bool sat) {
    std::uint32_t out = bits_of(float_of(a) + float_of(b));
    return sat ? fast_sat32(out) : out;
}

std::uint32_t fast_fmul(std::uint32_t a, std::uint32_t b, int /*rnd*/,
                        bool /*ftz*/, bool sat) {
    std::uint32_t out = bits_of(float_of(a) * float_of(b));
    return sat ? fast_sat32(out) : out;
}

std::uint32_t fast_ffma(std::uint32_t a, std::uint32_t b, std::uint32_t c,
                        int /*rnd*/, bool /*fmz*/, bool sat) {
    std::uint32_t out =
        bits_of(std::fma(float_of(a), float_of(b), float_of(c)));
    return sat ? fast_sat32(out) : out;
}

std::uint64_t fast_fadd64(std::uint64_t a, std::uint64_t b, int /*rnd*/,
                          bool sat) {
    const double r = double_of(a) + double_of(b);
    std::uint64_t out = bits_of(r);
    if (!sat) return out;
    if (std::isnan(r) || r == 0.0 || r < 0.0) return 0;
    if (r > 1.0) return std::bit_cast<std::uint64_t>(1.0);
    return out;
}

std::uint64_t fast_fmul64(std::uint64_t a, std::uint64_t b, int /*rnd*/,
                          bool sat) {
    const double r = double_of(a) * double_of(b);
    std::uint64_t out = bits_of(r);
    if (!sat) return out;
    if (std::isnan(r) || r == 0.0 || r < 0.0) return 0;
    if (r > 1.0) return std::bit_cast<std::uint64_t>(1.0);
    return out;
}

std::uint64_t fast_fma64(std::uint64_t a, std::uint64_t b, std::uint64_t c,
                         int /*rnd*/, bool sat) {
    const double r = std::fma(double_of(a), double_of(b), double_of(c));
    std::uint64_t out = bits_of(r);
    if (!sat) return out;
    if (std::isnan(r) || r == 0.0 || r < 0.0) return 0;
    if (r > 1.0) return std::bit_cast<std::uint64_t>(1.0);
    return out;
}

bool fast_f2i(std::uint32_t src_bits, int dstfmt, int rnd, bool /*ftz*/,
              std::uint32_t* out) {
    const float f = float_of(src_bits);
    if (std::isnan(f) || std::isinf(f)) return false;  // caller must fall back
    // Checked range before any cast (no UB): U32 [0, 2^32), S32 [-2^31, 2^31).
    const double d = static_cast<double>(f);
    double rv;
    switch (rnd) {
        case kFastRm: rv = std::floor(d); break;
        case kFastRp: rv = std::ceil(d); break;
        case kFastRz: rv = std::trunc(d); break;
        default: rv = std::nearbyint(d); break;  // RN ties-to-even
    }
    if (dstfmt == 4) {  // U32
        if (rv < 0.0 || rv >= 4294967296.0) return false;
        *out = static_cast<std::uint32_t>(rv);
        return true;
    }
    if (dstfmt == 5) {  // S32
        if (rv < -2147483648.0 || rv >= 2147483648.0) return false;
        *out = static_cast<std::uint32_t>(static_cast<std::int32_t>(rv));
        return true;
    }
    return false;  // unsupported destination: fall back
}

// Native (host) FP16 conversion under round-to-nearest.  `_Float16` is the
// gcc/clang ISO-extension FP16 type; conversions are correctly-rounded.
std::uint16_t host_f16(std::uint32_t bits) {
    const _Float16 h = static_cast<_Float16>(float_of(bits));
    return std::bit_cast<std::uint16_t>(h);
}

// Native (host) BF16 conversion: round-to-nearest-even the top 16 bits of
// the FP32 mantissa (the standard BF16 narrowing).  The BF16 pattern is
// returned in the LOW 16 bits (0x0000xxxx), matching the precise/sm120
// contract (f32_to_bf16(1.0f) == 0x00003f80).  Only correct for finite
// in-range values; NaN/Inf/subnormal are handled by the fallback decision.
std::uint16_t host_bf16(std::uint32_t bits) {
    // Round-to-nearest-even on the discarded low 16 bits.
    const std::uint32_t lsb = (bits >> 16) & 1u;
    return static_cast<std::uint16_t>((bits + 0x7fffu + lsb) >> 16);
}

bool fast_f2f(std::uint32_t src, std::uint32_t src_hi, int dstfmt, int srcfmt,
              std::uint32_t* out, std::uint32_t* out_hi) {
    // Native path only for RN-equivalent conversions between the types the
    // host can do exactly: F16<->F32, F32->BF16, BF16->F32, F32->F64,
    // F64->F32.  NaN/Inf/subnormal inputs fall back (exceptional policy).
    if (srcfmt == 1 && dstfmt == 0) {  // F32 -> F16
        *out = host_f16(src);
        *out_hi = 0;
        return true;
    }
    if (srcfmt == 0 && dstfmt == 1) {  // F16 -> F32
        const std::uint16_t h = static_cast<std::uint16_t>(src & 0xffffu);
        const unsigned exp = (h >> 10) & 0x1Fu;
        if (exp == 0x1Fu) {  // NaN / Inf map to the F32 canonical forms.
            if (h & 0x3FFu) {
                *out = 0x7fffffff;  // kCanonicalNan32
            } else {
                *out = (h & 0x8000u) ? 0xff800000u : 0x7f800000u;
            }
        } else {
            *out = bits_of(static_cast<float>(std::bit_cast<_Float16>(h)));
        }
        *out_hi = 0;
        return true;
    }
    if (srcfmt == 1 && dstfmt == 3) {  // F32 -> BF16 (BF16 in low 16 bits)
        *out = host_bf16(src);
        *out_hi = 0;
        return true;
    }
    if (srcfmt == 3 && dstfmt == 1) {  // BF16 -> F32 (BF16 from low 16 bits,
                                       // zero-extended into the high half)
        const std::uint32_t bf = src & 0xffffu;
        const std::uint32_t exp = (bf >> 7) & 0xffu;
        // NaN / Inf map to the F32 NaN (canonical) / inf, matching precise.
        if (exp == 0xffu) {
            if (bf & 0x7fu) {
                *out = 0x7fffffff;  // kCanonicalNan32
            } else {
                *out = (bf & 0x8000u) ? 0xff800000u : 0x7f800000u;
            }
        } else {
            *out = bf << 16;
        }
        *out_hi = 0;
        return true;
    }
    if (srcfmt == 1 && dstfmt == 2) {  // F32 -> F64 (exact)
        const double d = static_cast<double>(float_of(src));
        const std::uint64_t bits = bits_of(d);
        *out = static_cast<std::uint32_t>(bits & 0xffffffffu);
        *out_hi = static_cast<std::uint32_t>(bits >> 32);
        return true;
    }
    if (srcfmt == 2 && dstfmt == 1) {  // F64 -> F32
        const std::uint64_t pair =
            (static_cast<std::uint64_t>(src_hi) << 32) |
            (static_cast<std::uint64_t>(src) & 0xffffffffu);
        *out = bits_of(static_cast<float>(double_of(pair)));
        *out_hi = 0;
        return true;
    }
    return false;
}

bool fast_i2f(std::uint32_t val, int dstfmt, int srcfmt, std::uint32_t* out,
              std::uint32_t* out_hi) {
    // I2F source format (raw encoding values, matching sm120 enums:
    // U8=0, S8=1, U16=2, S16=3, U32=4, S32=5).  Sign-extend signed sources
    // BEFORE converting so e.g. S32 -1 (0xFFFFFFFF) becomes -1.0, not
    // 4294967295.0.  Only F32/F64 destinations are handled natively.
    double dv;
    switch (srcfmt) {
        case 0:  dv = static_cast<double>(static_cast<std::uint8_t>(val)); break;
        case 1:  dv = static_cast<double>(static_cast<std::int8_t>(val)); break;
        case 2:  dv = static_cast<double>(static_cast<std::uint16_t>(val)); break;
        case 3:  dv = static_cast<double>(static_cast<std::int16_t>(val)); break;
        case 5:  dv = static_cast<double>(static_cast<std::int32_t>(val)); break;
        case 4:
        default: dv = static_cast<double>(static_cast<std::uint32_t>(val)); break;
    }
    if (dstfmt == 2) {  // F64 destination.
        const std::uint64_t bits = bits_of(dv);
        *out = static_cast<std::uint32_t>(bits & 0xffffffffu);
        *out_hi = static_cast<std::uint32_t>(bits >> 32);
        return true;
    }
    if (dstfmt == 1) {  // F32 destination.
        *out = bits_of(static_cast<float>(dv));
        *out_hi = 0;
        return true;
    }
    return false;  // F16 / BF16 destinations: precise path
}

}  // namespace semu::fp
