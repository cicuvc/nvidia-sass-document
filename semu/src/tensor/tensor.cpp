// Bit-accurate tensor-core math engine (SIM_PLAN Phase 9).
//
// C++ port of tools/hmma_model.py (FDA = Fused-Dot-Add after MMA-Sim
// arXiv:2511.10909, Hopper/Blackwell column; GDFS = group-of-16 block-scaled
// MXFP4 path).  The interpreter uses this to execute HMMA / QMMA / OMMA
// functionally; the C++ unit tests and the Python differential harness compare
// against the same code so interpreter results equal the Python model
// bit-for-bit by construction.
//
// Arithmetic contract (identical to the Python reference):
//   * F = 25 fractional bits for the FDA align/truncate step; F = 35 for GDFS.
//   * exact fixed-point sum (order-independent), round-to-zero (RZ) at the
//     FP32 23rd fractional bit on output.
//   * |result| >= 2^128 -> infinity; subnormals honored down to 2^-149.
//   * fp16/bf16 specials: any NaN -> canonical 0x7FFFFFFF; 0*inf -> NaN; only
//     one inf kind -> that inf; both +inf and -inf -> NaN.
//   * fp8 inputs carry NO special values except the all-ones pattern 0x7F/0xFF
//     (NaN); exp-max with a lower mantissa is an ordinary value (verified for
//     e4m3 on SM120, applied to all fp8 formats following the identical FDA
//     structure).
//   * E8M0 scales: 2^(byte-127); 0xFF is NaN.  MXFP4 e2m1: sign bit 3,
//     exp bits [2:1] bias 1, mantissa bit 0 (0x1=0.5, 0x2=1.0, 0x6=4.0).

#include <semu/tensor/tensor.hpp>

#include <cstdint>
#include <limits>

namespace semu::tensor {

namespace {

// FDA align-step fractional bits (Hopper HMMA / Blackwell QMMA column).
constexpr int kFdaF = 25;
// GDFS align-step fractional bits (Blackwell OMMA.SF MXFP4 column).
constexpr int kGdfsF = 35;
// Canonical FP32 NaN (NVIDIA).
constexpr std::uint32_t kNanOut = 0x7FFFFFFF;
// E8M0 NaN sentinel returned by e8m0_exp for byte 0xFF (see the header).
constexpr std::int8_t kE8m0NanSentinel = -128;
// Internal marker used by the gdfs body for a NaN scale exponent.
constexpr int kScaleNan = 0xFF;

enum Sp { kNum, kPosInf, kNegInf, kNan };

int ebits_of(int mant) { return mant == 7 ? 8 : (mant == 10 ? 5 : 8); }

// Classify a value with `mant` mantissa bits (7=bf16, 10=f16, 23=fp32).
Sp classify(std::uint32_t v, int mant) {
    const int eb = ebits_of(mant);
    const std::uint32_t e = (v >> mant) & ((1u << eb) - 1);
    const std::uint32_t emax = (1u << eb) - 1;
    if (e == emax) {
        const std::uint32_t m = v & ((1u << mant) - 1);
        if (m) return kNan;
        return (v >> (mant + eb)) ? kNegInf : kPosInf;
    }
    return kNum;
}

// Decompose a bf16/f16 value: value = sign * num * 2^(exp - den_log2).
struct Sm {
    int sign = 1;
    std::uint32_t num = 0;
    int den = 0;  // den_log2
    int e = 0;    // unbiased exponent
};

Sm decompose(std::uint32_t v, int mant, int bias) {
    const int eb = ebits_of(mant);
    Sm out;
    out.sign = (v >> (mant + eb)) ? -1 : 1;
    const std::uint32_t e = (v >> mant) & ((1u << eb) - 1);
    const std::uint32_t m = v & ((1u << mant) - 1);
    if (e == 0) {  // subnormal
        out.num = m;
        out.den = mant;
        out.e = 1 - bias;
    } else {
        out.num = (1u << mant) + m;
        out.den = mant;
        out.e = static_cast<int>(e) - bias;
    }
    return out;
}

// FP32 decomposition (mantissa 23, bias 127, 8-bit exponent).
Sm fp32_decomp(std::uint32_t x) {
    Sm out;
    out.sign = (x >> 31) ? -1 : 1;
    const std::uint32_t e = (x >> 23) & 0xFF;
    const std::uint32_t m = x & 0x7FFFFF;
    if (e == 0) {  // subnormal
        out.num = m;
        out.den = 23;
        out.e = 1 - 127;
    } else {
        out.num = (1u << 23) + m;
        out.den = 23;
        out.e = static_cast<int>(e) - 127;
    }
    return out;
}

// fp8 decomposition (explicit ebits).  NVIDIA QMMA treats the all-ones
// exponent as an ordinary value (there are NO inf values in fp8 inputs); only
// the all-ones pattern (0x7F/0xFF) is NaN.
Sm fp8_decomp(std::uint32_t v, int mant, int bias, int ebits) {
    Sm out;
    out.sign = (v >> (mant + ebits)) ? -1 : 1;
    const std::uint32_t e = (v >> mant) & ((1u << ebits) - 1);
    const std::uint32_t m = v & ((1u << mant) - 1);
    if (e == 0) {
        out.num = m;
        out.den = mant;
        out.e = 1 - bias;
    } else {
        out.num = (1u << mant) + m;
        out.den = mant;
        out.e = static_cast<int>(e) - bias;
    }
    return out;
}

// MXFP4 e2m1 decomposition (sign bit 3, exp bits [2:1] bias 1, mantissa bit 0):
// value = sign * num / 2^1 * 2^(exp-1); subnormal (exp 0) = mant * 2^-1.
// Probed on SM120: 0x1=0.5, 0x2=1.0, 0x6=4.0.
Sm e2m1_decomp(std::uint32_t v) {
    Sm out;
    out.sign = (v >> 3) ? -1 : 1;
    const std::uint32_t e = (v >> 1) & 0x3;
    const std::uint32_t m = v & 1;
    if (e == 0) {
        out.num = m;
        out.den = 0;
        out.e = -1;
    } else {
        out.num = 2 + m;
        out.den = 1;
        out.e = static_cast<int>(e) - 1;
    }
    return out;
}

// num != 0 iff the sign+mantissa bits are all clear (exp zero too).
bool is_zero_any(std::uint32_t v, int mant) {
    return (v & ((1u << (mant + 1)) - 1)) == 0;
}

bool sign_pos(std::uint32_t v, int mant) {
    return !(v >> (mant + ebits_of(mant)));
}

// num / 2^n truncated toward zero (RZ), not floor.  C++'s / already truncates
// toward zero; this named wrapper handles negative dividends the same way the
// Python reference's explicit tz correction does, and guards n >= 63 (every
// bit shifted out -> 0, mirroring Python's arbitrary-precision >>).
std::int64_t rz_pow2_div(std::int64_t num, unsigned n) {
    if (n >= 63) return 0;
    if (num >= 0) return num >> n;
    return -((-num) >> n);
}

// num * 2^(shift - den_log2), RZ-truncated.  num may be negative; the shift
// product must never overflow int64 (num <= 2^24, |shift| <= ~40 for the
// engine's K <= 64 shapes).  Right shifts beyond the value's bit width
// truncate to zero (mirrors Python's arbitrary-precision >>).
std::int64_t to_fixed(std::int64_t num, int den_log2, int shift) {
    const long long k = static_cast<long long>(shift) - den_log2;
    if (k >= 0) {
        if (num == 0) return 0;
        const std::uint64_t mag =
            (num < 0) ? static_cast<std::uint64_t>(-num)
                      : static_cast<std::uint64_t>(num);
        const std::uint64_t shifted = mag << static_cast<unsigned>(k);
        const std::int64_t v = static_cast<std::int64_t>(shifted);
        return num < 0 ? -v : v;
    }
    const long long shift_amt = -k;
    if (shift_amt >= 63) return 0;  // every bit shifted out -> 0
    if (num >= 0) return num >> shift_amt;
    return -((-num) >> shift_amt);
}

int bit_length_128(unsigned __int128 t) {
    int n = 0;
    while (t) {
        ++n;
        t >>= 1;
    }
    return n;
}

// |total| as an unsigned 128-bit magnitude (total is never INT128_MIN here).
unsigned __int128 abs128(__int128 total) {
    return total < 0 ? static_cast<unsigned __int128>(-total)
                     : static_cast<unsigned __int128>(total);
}

// Shared FP32 normalization: value = total * 2^e_base; RZ at bit 23,
// |sum| >= 2^128 -> inf, subnormal down to 2^-149.
std::uint32_t normalize_fp32(__int128 total, int e_base) {
    if (total == 0) return 0x00000000;
    const bool neg = total < 0;
    const unsigned __int128 t = abs128(total);
    const int bl = bit_length_128(t);
    const int e_val = e_base + (bl - 1);
    if (e_val >= 128) return neg ? 0xFF800000u : 0x7F800000u;
    if (e_val < -126) {
        const int shift = e_val + 149;
        if (shift < 0) return neg ? 0x80000000u : 0x00000000u;
        const unsigned __int128 m = t >> static_cast<unsigned>(shift);
        if (m == 0) return neg ? 0x80000000u : 0x00000000u;
        return (neg ? 0x80000000u : 0) | static_cast<std::uint32_t>(m);
    }
    std::uint32_t m;
    if (bl >= 24) {
        m = static_cast<std::uint32_t>((t >> static_cast<unsigned>(bl - 24)) &
                                       0x7FFFFF);
    } else {
        m = static_cast<std::uint32_t>(
            static_cast<std::uint64_t>(t << static_cast<unsigned>(24 - bl)) &
            0x7FFFFF);
    }
    return (neg ? 0x80000000u : 0) |
           (static_cast<std::uint32_t>(e_val + 127) << 23) | m;
}

// Per-format arithmetic parameters.
struct FmtParams {
    int mant = 7;    // mantissa bits
    int bias = 127;  // exponent bias
    int ebits = 8;   // exponent bits
    bool is_fp8 = false;
};

// fp8 special-class classification (verified on sm120 RTX 5090, CUDA 13.1).
// Returns kPosInf/kNegInf/kNan/kNone.  Only e5m2 carries true +/-inf
// (0x7C/0xFC) and NaN (0x7D-0x7F / 0xFD-0xFF); e4m3/e3m4 carry only the
// all-ones NaN; the other fp8 formats have no special values.
enum class Fp8Sp { kNone, kPosInf, kNegInf, kNan };

Fp8Sp fp8_special_i(std::uint8_t v, const FmtParams& p) {
    const std::uint8_t m = static_cast<std::uint8_t>(v & 0x7F);
    if (p.ebits == 5 && p.mant == 2) {  // e5m2
        if (m == 0x7C) return (v & 0x80) ? Fp8Sp::kNegInf : Fp8Sp::kPosInf;
        if (m == 0x7D || m == 0x7E || m == 0x7F) return Fp8Sp::kNan;
        return Fp8Sp::kNone;
    }
    if ((p.mant == 3 && p.ebits == 4) || (p.mant == 4 && p.ebits == 3)) {
        if (m == 0x7F) return Fp8Sp::kNan;
        return Fp8Sp::kNone;
    }
    return Fp8Sp::kNone;
}

FmtParams params_of(Format f) {
    switch (f) {
        case Format::kF16: return {10, 15, 5, false};
        case Format::kBf16: return {7, 127, 8, false};
        case Format::kFp8E4M3: return {3, 7, 4, true};
        case Format::kFp8E5M2: return {2, 15, 5, true};
        case Format::kFp8E3M4: return {4, 3, 3, true};
        case Format::kFp8E2M3: return {3, 1, 2, true};
        case Format::kFp8E3M2: return {2, 3, 3, true};
        case Format::kFp8E2M1: return {1, 1, 2, true};
        case Format::kMxfp4E2M1:
            // gdfs path only; the raw value is a nibble, decomposed via
            // e2m1_decomp inside gdfs_impl.
            return {1, 1, 2, false};
    }
    return {7, 127, 8, false};
}

struct Prod {
    int sign;  // +/-1
    std::uint32_t num;
    int den;
    int e;
};

// Shared FDA body: one output element d = f(c, a_0..K-1, b_0..K-1).
std::uint32_t fda_impl(std::uint32_t c, const std::uint32_t* a_vals,
                       const std::uint32_t* b_vals, std::size_t k,
                       const FmtParams& p) {
    // ---- Step 1: special values ------------------------------------------
    // fp8 inputs carry NO special values except the all-ones NaN; only the
    // FP32 accumulator C can carry NaN/inf.  For bf16/f16 the full FDA
    // special-value logic applies.
    const Sp csp = classify(c, 23);
    if (csp == kNan) return kNanOut;
    if (p.is_fp8) {
        // fp8 special values VERIFIED on sm120 (RTX 5090, CUDA 13.1): only
        // e5m2 has true +/-inf (0x7C/0xFC) and NaN (0x7D-0x7F); e4m3/e3m4
        // have only the all-ones NaN; e3m2/e2m3/e2m1 have none.  NaN in any
        // fp8 input wins over c's inf.
        bool nan = false;
        Fp8Sp pos = Fp8Sp::kNone, neg = Fp8Sp::kNone;
        for (std::size_t i = 0; i < k; ++i) {
            const Fp8Sp sa = fp8_special_i(a_vals[i] & 0xFF, p);
            const Fp8Sp sb = fp8_special_i(b_vals[i] & 0xFF, p);
            if (sa == Fp8Sp::kNan || sb == Fp8Sp::kNan) nan = true;
            if (sa == Fp8Sp::kPosInf || sb == Fp8Sp::kPosInf) pos = Fp8Sp::kPosInf;
            if (sa == Fp8Sp::kNegInf || sb == Fp8Sp::kNegInf) neg = Fp8Sp::kNegInf;
        }
        if (nan) return kNanOut;
        if (pos == Fp8Sp::kPosInf && neg == Fp8Sp::kNegInf) return kNanOut;
        if (pos == Fp8Sp::kPosInf) return 0x7F800000u;
        if (neg == Fp8Sp::kNegInf) return 0xFF800000u;
        if (csp == kPosInf) return 0x7F800000u;
        if (csp == kNegInf) return 0xFF800000u;
    } else {
        bool pos_inf = false, neg_inf = false;
        if (csp == kPosInf) pos_inf = true;
        else if (csp == kNegInf) neg_inf = true;
        for (std::size_t i = 0; i < k; ++i) {
            const Sp sa = classify(a_vals[i], p.mant);
            const Sp sb = classify(b_vals[i], p.mant);
            if (sa == kNan || sb == kNan) return kNanOut;
            const bool ainf = sa == kPosInf || sa == kNegInf;
            const bool binf = sb == kPosInf || sb == kNegInf;
            if (ainf || binf) {
                const bool za = is_zero_any(a_vals[i], p.mant);
                const bool zb = is_zero_any(b_vals[i], p.mant);
                if ((ainf && zb) || (binf && za)) return kNanOut;  // 0*inf
                bool prod_pos;
                if (ainf && binf) {
                    prod_pos = sa == sb;
                } else if (ainf) {
                    prod_pos = (sa == kPosInf) == sign_pos(b_vals[i], p.mant);
                } else {
                    prod_pos = (sb == kPosInf) == sign_pos(a_vals[i], p.mant);
                }
                if (prod_pos) pos_inf = true;
                else neg_inf = true;
            }
        }
        if (pos_inf && neg_inf) return kNanOut;
        if (pos_inf) return 0x7F800000u;
        if (neg_inf) return 0xFF800000u;
    }

    // ---- Step 2: exact products (significand x exponent) ------------------
    const Sm cs = fp32_decomp(c);
    const bool have_c = cs.num != 0;
    int e_max = have_c ? cs.e : std::numeric_limits<int>::min();
    Prod prods[64];
    if (k > 64) k = 64;  // engine supports up to k64 (OMMA)
    for (std::size_t i = 0; i < k; ++i) {
        Prod pd;
        if (p.is_fp8) {
            const Sm a = fp8_decomp(a_vals[i], p.mant, p.bias, p.ebits);
            const Sm b = fp8_decomp(b_vals[i], p.mant, p.bias, p.ebits);
            pd = {a.sign * b.sign, a.num * b.num, a.den + b.den, a.e + b.e};
        } else {
            const Sm a = decompose(a_vals[i], p.mant, p.bias);
            const Sm b = decompose(b_vals[i], p.mant, p.bias);
            pd = {a.sign * b.sign, a.num * b.num, a.den + b.den, a.e + b.e};
        }
        prods[i] = pd;
        if (pd.e > e_max) e_max = pd.e;
    }
    if (e_max == std::numeric_limits<int>::min()) e_max = 0;

    // ---- Step 3/4: align to e_max, truncate (RZ) to F bits, exact sum ----
    __int128 total = 0;
    if (have_c) {
        total += to_fixed(static_cast<std::int64_t>(cs.sign) * cs.num, cs.den,
                          cs.e - e_max + kFdaF);
    }
    for (std::size_t i = 0; i < k; ++i) {
        const Prod& p = prods[i];
        total += to_fixed(static_cast<std::int64_t>(p.sign) * p.num, p.den,
                          p.e - e_max + kFdaF);
    }

    // ---- Step 5: normalize to FP32, RZ at bit 23 --------------------------
    return normalize_fp32(total, e_max - kFdaF);
}

// Shared GDFS body: one OMMA.SF output element.
std::uint32_t gdfs_impl(std::uint32_t c, const std::uint32_t* a_vals,
                        const std::uint32_t* b_vals, std::size_t k,
                        const std::int32_t* a_scale_exp,
                        const std::int32_t* b_scale_exp, int block) {
    if (classify(c, 23) == kNan) return kNanOut;
    const Sp csp = classify(c, 23);
    if (csp == kPosInf || csp == kNegInf) return c;  // d = c
    // scale NaN (E8M0 0xFF) -> canonical NaN
    const int n_blocks = static_cast<int>((k + block - 1) / block);
    for (int i = 0; i < n_blocks; ++i) {
        if (a_scale_exp[i] == kScaleNan || b_scale_exp[i] == kScaleNan) {
            return kNanOut;
        }
    }

    const Sm cs = fp32_decomp(c);
    const bool have_c = cs.num != 0;

    // Step 2: exact products (significand x exponent, no normalization)
    Prod prods[64];
    if (k > 64) k = 64;
    for (std::size_t i = 0; i < k; ++i) {
        const Sm a = e2m1_decomp(a_vals[i] & 0xF);
        const Sm b = e2m1_decomp(b_vals[i] & 0xF);
        prods[i] = {a.sign * b.sign, a.num * b.num, a.den + b.den, a.e + b.e};
    }

    // Step 3: group of 16 sums -> sigma_j (fixed point at F=35 fractional
    // bits relative to the group's max exponent); Step 4: scale by E8M0.
    constexpr int group = 16;
    constexpr int groups_per_block = 32 / group;  // block=32 -> 2 groups
    struct Sigma {
        __int128 total;  // integer at 2^e (den_log2 folded in)
        int e;           // exponent of the 2^-F unit
    };
    Sigma sigmas[4];
    int n_sigmas = 0;
    for (std::size_t j = 0; j < k; j += static_cast<std::size_t>(group)) {
        const int blk = static_cast<int>(j / (group * groups_per_block));
        const int sc = a_scale_exp[blk] + b_scale_exp[blk];
        int e_grp = prods[j].e;
        for (std::size_t q = j; q < j + group && q < k; ++q) {
            if (prods[q].e > e_grp) e_grp = prods[q].e;
        }
        __int128 total = 0;
        for (std::size_t q = j; q < j + group && q < k; ++q) {
            const Prod& p = prods[q];
            const int sh = p.e - e_grp - p.den + kGdfsF;
            const std::int64_t snum = static_cast<std::int64_t>(p.sign) * p.num;
            if (sh >= 0) {
                if (p.num == 0) continue;
                const unsigned __int128 mag =
                    static_cast<unsigned __int128>(p.num) << static_cast<unsigned>(sh);
                total += p.sign * static_cast<__int128>(mag);
            } else {
                total += rz_pow2_div(snum, static_cast<unsigned>(-sh));
            }
        }
        // sigma value = total * 2^(e_grp - F + sc)
        sigmas[n_sigmas++] = {total, e_grp - kGdfsF + sc};
    }

    // Step 5: align sigmas and c to e_max, truncate (RZ) to F bits.
    int e_max = have_c ? cs.e : std::numeric_limits<int>::min();
    for (int i = 0; i < n_sigmas; ++i) {
        if (sigmas[i].e > e_max) e_max = sigmas[i].e;
    }
    if (e_max == std::numeric_limits<int>::min()) e_max = 0;
    __int128 total = 0;
    if (have_c) {
        total += to_fixed(static_cast<std::int64_t>(cs.sign) * cs.num, cs.den,
                          cs.e - e_max + kGdfsF);
    }
    for (int i = 0; i < n_sigmas; ++i) {
        // sigma is an integer at 2^e; align to e_max + F
        const int sh = sigmas[i].e - e_max + kGdfsF;
        if (sh >= 0) {
            // Shift the MAGNITUDE, then re-apply the sign (shifting a negative
            // value cast to unsigned would wrap past 2^128 and corrupt `total`).
            const unsigned __int128 mag =
                (sigmas[i].total < 0)
                    ? (static_cast<unsigned __int128>(-sigmas[i].total)
                       << static_cast<unsigned>(sh))
                    : (static_cast<unsigned __int128>(sigmas[i].total)
                       << static_cast<unsigned>(sh));
            total += (sigmas[i].total < 0)
                         ? -static_cast<__int128>(mag)
                         : static_cast<__int128>(mag);
        } else {
            total += rz_pow2_div(sigmas[i].total, static_cast<unsigned>(-sh));
        }
    }

    // Step 7: normalize to FP32 (RZ at bit 23, like FDA).
    return normalize_fp32(total, e_max - kGdfsF);
}

}  // namespace

// ---------------------------------------------------------------------------

std::int8_t e8m0_exp(std::uint8_t byte) {
    // Unbiased E8M0 exponent 2^(b-127); 0xFF (NaN) maps to the sentinel -128
    // so it is distinguishable from every valid exponent (-127..127).
    return (byte == 0xFF) ? kE8m0NanSentinel : std::int8_t(byte - 127);
}

std::uint32_t fda(std::uint32_t c, const std::uint32_t* a_vals,
                  const std::uint32_t* b_vals, std::size_t k, Format fmt) {
    return fda_impl(c, a_vals, b_vals, k, params_of(fmt));
}

std::uint32_t gdfs(std::uint32_t c, const std::uint8_t* a_vals,
                   const std::uint8_t* b_vals, std::size_t k,
                   const std::int8_t* a_scale_exp,
                   const std::int8_t* b_scale_exp, std::size_t n_scales) {
    // Convert the int8 sentinel (-128 = NaN) to the int32 0xFF marker the
    // engine body uses, then run the shared body.
    std::int32_t aes[4], bes[4];
    const std::size_t n = n_scales < 4 ? n_scales : 4;
    for (std::size_t i = 0; i < n; ++i) {
        aes[i] = (a_scale_exp[i] == kE8m0NanSentinel) ? kScaleNan
                                                      : a_scale_exp[i];
        bes[i] = (b_scale_exp[i] == kE8m0NanSentinel) ? kScaleNan
                                                      : b_scale_exp[i];
    }
    std::uint32_t a32[64], b32[64];
    for (std::size_t i = 0; i < k && i < 64; ++i) {
        a32[i] = a_vals[i];
        b32[i] = b_vals[i];
    }
    return gdfs_impl(c, a32, b32, k, aes, bes, 32);
}

bool hmma_shape(int size, int srcfmt, Shape* out) {
    if (!out) return false;
    // size: 0=1688(k8), 1=16816(k16), 2=1684(TF32).  The engine implements the
    // f16/bf16 F32-accumulator shapes only; TF32/E6M9 and the F16 accumulator
    // are decode-only.
    if (size < 0 || size > 1) return false;        // 1684 is TF32-only
    if (srcfmt != 0 && srcfmt != 1) return false;  // only F16/BF16
    out->regs_a = (size == 1) ? 4 : 2;
    out->regs_b = (size == 1) ? 2 : 1;
    out->regs_c = 4;
    out->k = (size == 1) ? 16 : 8;
    return true;
}

bool qmma_shape(int size, Shape* out) {
    if (!out) return false;
    // size: 0=16816 (k16), 1=16832 (k32).
    if (size != 0 && size != 1) return false;
    out->regs_a = (size == 1) ? 4 : 2;
    out->regs_b = (size == 1) ? 2 : 1;
    out->regs_c = 4;
    out->k = (size == 1) ? 32 : 16;
    return true;
}

bool omma_shape(Shape* out) {
    if (!out) return false;
    out->regs_a = 4;
    out->regs_b = 2;
    out->regs_c = 4;
    out->k = 64;
    return true;
}

// ---------------------------------------------------------------------------
// Per-lane fragment evaluation (mirrors tools/hmma_model.py's frag_* fns).

namespace {

void fold4(std::uint32_t* out, int* idx, std::uint32_t a, std::uint32_t b) {
    for (int i = 0; i < 4; ++i) {
        out[(*idx)++] = a;
        out[(*idx)++] = b;
    }
}

// Split a flat [a,b,a,b,...] pair list into A and B arrays.
void split_pairs(const std::uint32_t* flat, std::size_t n_pairs,
                 std::uint32_t* A, std::uint32_t* B) {
    for (std::size_t i = 0; i < n_pairs; ++i) {
        A[i] = flat[2 * i];
        B[i] = flat[2 * i + 1];
    }
}

}  // namespace

void hmma_k16(const std::uint32_t a[4], const std::uint32_t b[2],
              const std::uint32_t c[4], Format fmt, std::uint32_t out[4]) {
    const std::uint32_t al[4] = {a[0] & 0xFFFF, a[1] & 0xFFFF, a[2] & 0xFFFF,
                                 a[3] & 0xFFFF};
    const std::uint32_t ah[4] = {a[0] >> 16, a[1] >> 16, a[2] >> 16,
                                 a[3] >> 16};
    const std::uint32_t b0l = b[0] & 0xFFFF, b0h = b[0] >> 16;
    const std::uint32_t b1l = b[1] & 0xFFFF, b1h = b[1] >> 16;
    std::uint32_t P[32], Q[32];
    int ip = 0, iq = 0;
    fold4(P, &ip, al[0], b0l); fold4(P, &ip, ah[0], b0h);
    fold4(P, &ip, al[2], b1l); fold4(P, &ip, ah[2], b1h);
    fold4(Q, &iq, al[1], b0l); fold4(Q, &iq, ah[1], b0h);
    fold4(Q, &iq, al[3], b1l); fold4(Q, &iq, ah[3], b1h);
    std::uint32_t A[16], B[16], A2[16], B2[16];
    split_pairs(P, 16, A, B);
    split_pairs(Q, 16, A2, B2);
    out[0] = fda(c[0], A, B, 16, fmt);
    out[1] = fda(c[1], A, B, 16, fmt);
    out[2] = fda(c[2], A2, B2, 16, fmt);
    out[3] = fda(c[3], A2, B2, 16, fmt);
}

void hmma_k8(const std::uint32_t a[2], const std::uint32_t b[1],
             const std::uint32_t c[4], Format fmt, std::uint32_t out[4]) {
    const std::uint32_t al0 = a[0] & 0xFFFF, ah0 = a[0] >> 16;
    const std::uint32_t al1 = a[1] & 0xFFFF, ah1 = a[1] >> 16;
    const std::uint32_t b0l = b[0] & 0xFFFF, b0h = b[0] >> 16;
    std::uint32_t P[16], Q[16];
    int ip = 0, iq = 0;
    fold4(P, &ip, al0, b0l); fold4(P, &ip, ah0, b0h);
    fold4(Q, &iq, al1, b0l); fold4(Q, &iq, ah1, b0h);
    std::uint32_t A[8], B[8], A2[8], B2[8];
    split_pairs(P, 8, A, B);
    split_pairs(Q, 8, A2, B2);
    out[0] = fda(c[0], A, B, 8, fmt);
    out[1] = fda(c[1], A, B, 8, fmt);
    out[2] = fda(c[2], A2, B2, 8, fmt);
    out[3] = fda(c[3], A2, B2, 8, fmt);
}

void qmma_k32(const std::uint32_t a[4], const std::uint32_t b[2],
              const std::uint32_t c[4], Format fmt, std::uint32_t out[4]) {
    std::uint32_t P[64], Q[64];
    int ip = 0, iq = 0;
    for (int j = 0; j < 4; ++j) {
        const std::uint32_t a0j = (a[0] >> (8 * j)) & 0xFF;
        const std::uint32_t a1j = (a[1] >> (8 * j)) & 0xFF;
        const std::uint32_t a2j = (a[2] >> (8 * j)) & 0xFF;
        const std::uint32_t a3j = (a[3] >> (8 * j)) & 0xFF;
        const std::uint32_t b0j = (b[0] >> (8 * j)) & 0xFF;
        const std::uint32_t b1j = (b[1] >> (8 * j)) & 0xFF;
        fold4(P, &ip, a0j, b0j); fold4(P, &ip, a2j, b1j);
        fold4(Q, &iq, a1j, b0j); fold4(Q, &iq, a3j, b1j);
    }
    std::uint32_t A[32], B[32], A2[32], B2[32];
    split_pairs(P, 32, A, B);
    split_pairs(Q, 32, A2, B2);
    out[0] = fda(c[0], A, B, 32, fmt);
    out[1] = fda(c[1], A, B, 32, fmt);
    out[2] = fda(c[2], A2, B2, 32, fmt);
    out[3] = fda(c[3], A2, B2, 32, fmt);
}

void qmma_k16(const std::uint32_t a[2], const std::uint32_t b[1],
              const std::uint32_t c[4], Format fmt, std::uint32_t out[4]) {
    std::uint32_t P[32], Q[32];
    int ip = 0, iq = 0;
    for (int j = 0; j < 4; ++j) {
        const std::uint32_t a0j = (a[0] >> (8 * j)) & 0xFF;
        const std::uint32_t a1j = (a[1] >> (8 * j)) & 0xFF;
        const std::uint32_t b0j = (b[0] >> (8 * j)) & 0xFF;
        fold4(P, &ip, a0j, b0j);
        fold4(Q, &iq, a1j, b0j);
    }
    std::uint32_t A[16], B[16], A2[16], B2[16];
    split_pairs(P, 16, A, B);
    split_pairs(Q, 16, A2, B2);
    out[0] = fda(c[0], A, B, 16, fmt);
    out[1] = fda(c[1], A, B, 16, fmt);
    out[2] = fda(c[2], A2, B2, 16, fmt);
    out[3] = fda(c[3], A2, B2, 16, fmt);
}

void omma_k64(const std::uint32_t a[4], const std::uint32_t b[2],
              const std::uint32_t c[4], std::uint32_t re, std::uint32_t rh,
              std::uint32_t sel, std::uint32_t out[4]) {
    std::uint32_t P[128], Q[128];
    int ip = 0, iq = 0;
    for (int n = 0; n < 8; ++n) {
        const std::uint32_t a0n = (a[0] >> (4 * n)) & 0xF;
        const std::uint32_t a1n = (a[1] >> (4 * n)) & 0xF;
        fold4(P, &ip, a0n, (b[0] >> (4 * n)) & 0xF);
        fold4(Q, &iq, a1n, (b[0] >> (4 * n)) & 0xF);
    }
    for (int n = 0; n < 8; ++n) {
        const std::uint32_t a2n = (a[2] >> (4 * n)) & 0xF;
        const std::uint32_t a3n = (a[3] >> (4 * n)) & 0xF;
        fold4(P, &ip, a2n, (b[1] >> (4 * n)) & 0xF);
        fold4(Q, &iq, a3n, (b[1] >> (4 * n)) & 0xF);
    }
    std::uint32_t A[64], B[64], A2[64], B2[64];
    split_pairs(P, 64, A, B);
    split_pairs(Q, 64, A2, B2);

    // Scale words: byte 0 of Re/Rh scales k 0..31 (products 0..31), byte 1
    // scales k 32..63.  Unbiased exponents via e8m0_exp; only sel==0 is
    // verified legal (all others fault on hardware).
    std::int8_t aes[2] = {e8m0_exp(re & 0xFF), e8m0_exp((re >> 8) & 0xFF)};
    std::int8_t bes[2] = {e8m0_exp(rh & 0xFF), e8m0_exp((rh >> 8) & 0xFF)};

    // gdfs() consumes flat uint8 arrays; A/B already hold the 4-bit values.
    std::uint8_t raw_a[64], raw_b[64], raw_a2[64], raw_b2[64];
    for (int i = 0; i < 64; ++i) {
        raw_a[i] = static_cast<std::uint8_t>(A[i]);
        raw_b[i] = static_cast<std::uint8_t>(B[i]);
        raw_a2[i] = static_cast<std::uint8_t>(A2[i]);
        raw_b2[i] = static_cast<std::uint8_t>(B2[i]);
    }
    if (sel != 0) {
        // Only sel=0 is verified legal on SM120; the interpreter pre-checks
        // sel and faults before reaching the engine.
        out[0] = out[1] = out[2] = out[3] = kNanOut;
    } else {
        out[0] = gdfs(c[0], raw_a, raw_b, 64, aes, bes, 2);
        out[1] = gdfs(c[1], raw_a, raw_b, 64, aes, bes, 2);
        out[2] = gdfs(c[2], raw_a2, raw_b2, 64, aes, bes, 2);
        out[3] = gdfs(c[3], raw_a2, raw_b2, 64, aes, bes, 2);
    }
}

}  // namespace semu::tensor
