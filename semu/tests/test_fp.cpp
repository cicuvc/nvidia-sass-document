// FP semantics unit tests (SIM_PLAN Phase 5).
//
// Covers the bit-exact engine: rounding-mode separation (each mode must
// produce a distinct last bit on a rounding tie), FMA correctness, FMZ/FTZ
// flush rules, NaN canonicalization, and the fenv restore contract (the
// RoundingGuard leaves the host rounding mode unchanged after the call).

#include <semu/fp.hpp>
#include <semu/fast_fp.hpp>

#include <cfenv>
#include <cstdio>

#include "test_framework.hpp"

namespace {

using semu::fp::Rnd;
using semu::fp::RoundingGuard;
using semu::fp::fadd;
using semu::fp::ffma;
using semu::fp::fmul;
using semu::fp::fma64;
using semu::fp::fadd64;
using semu::fp::fmul64;

// 2^24 + 1 rounds differently per mode: RN/DOWN -> 2^24, UP -> 2^24+2,
// RZ -> 2^24.  Use a value whose last bit differs between modes to prove
// the dynamic rounding mode is actually in effect.
constexpr std::uint32_t kBig = 0x4b800000;  // 2^24
constexpr std::uint32_t kOne = 0x3f800000;  // 1.0

// A tie at the f32 boundary: 1.0 + 2^-24 (half ULP above 1.0).
// 0x3f800000 + 0x33800000 under RN ties-to-even stays 1.0; under RP it
// becomes 1+2^-23.  Verify each mode yields a distinct bit pattern.
TEST(fp_rounding_modes_distinct) {
    // (1.0 + 2^-24) * 1.0: product rounds per mode.
    const std::uint32_t tiny = 0x33800000;  // 2^-24
    const std::uint32_t rn = fmul(kBig, kOne, Rnd::kRn, false, false);
    const std::uint32_t up = fmul(kBig, kOne, Rnd::kRp, false, false);
    const std::uint32_t dn = fmul(kBig, kOne, Rnd::kRm, false, false);
    const std::uint32_t rz = fmul(kBig, kOne, Rnd::kRz, false, false);
    // All exact (2^24 * 1.0) but the compiler must not fold them: assert
    // that the result depends on the rounding mode by using a tie value.
    (void)tiny;
    const std::uint32_t rn_tie = fadd(0x3f800000u, tiny, Rnd::kRn, false, false);
    const std::uint32_t up_tie = fadd(0x3f800000u, tiny, Rnd::kRp, false, false);
    // 1.0 + 2^-24: RN (ties-to-even) -> 1.0 (0x3f800000); RP -> next ULP.
    CHECK(rn_tie == 0x3f800000u);
    CHECK(up_tie == 0x3f800001u);
    // The exact multiplications are equal but must not be constant-folded
    // to a wrong value under a non-default mode: 2^24 * 1.0 is exact so all
    // four agree on the bits.
    CHECK(rn == kBig && up == kBig && dn == kBig && rz == kBig);
}

TEST(fp_fma_tie_rounding) {
    // FFMA(1.0, 1.0, 2^-24) under RN ties-to-even -> 1.0; under RP -> 1+2^-23.
    const std::uint32_t rn = ffma(kOne, kOne, 0x33800000u, Rnd::kRn, 0, false);
    const std::uint32_t up = ffma(kOne, kOne, 0x33800000u, Rnd::kRp, 0, false);
    const std::uint32_t dn = ffma(kOne, kOne, 0x33800000u, Rnd::kRm, 0, false);
    CHECK(rn == 0x3f800000u);
    CHECK(up == 0x3f800001u);
    CHECK(dn == 0x3f800000u);
}

TEST(fp_nan_canonical) {
    // NaN operands canonicalize to 0x7fffffff.
    CHECK(ffma(0x7fc00000u, kOne, kOne, Rnd::kRn, 0, false) ==
          semu::fp::kCanonicalNan32);
    CHECK(fadd(0xffc00000u, kOne, Rnd::kRn, false, false) ==
          semu::fp::kCanonicalNan32);
}

TEST(fp_fmz_flush_all_inputs) {
    // FTZ (fmz=2) flushes all three denormal inputs sign-preserving; the
    // result of fma(0,0,0) is +0.
    CHECK(ffma(0x00000001u, 0x00000001u, 0x00000001u, Rnd::kRn, 2, false) ==
          0x00000000u);
    // FTZ subnormal/zero result follows the arithmetic sign: product
    // +0 * -1.5 = -0 plus addend -0 -> -0 under RN (verified sm120).
    CHECK(ffma(0x00000001u, 0xbf800000u, 0x807fffffu, Rnd::kRn, 2, false) ==
          0x80000000u);
    // FMZ (fmz=1) flushes the multiply inputs to POSITIVE zero: +0 * -1.5
    // is sign-neutral, addend -0 -> +0 under RN (verified sm120).
    CHECK(ffma(0x00000001u, 0xbf800000u, 0x807fffffu, Rnd::kRn, 1, false) ==
          0x00000000u);
    // FTZ flush of a negative subnormal RESULT is sign-preserving: -2^-150
    // (product of -2^-126 * +2^-126) -> -0 in every rounding mode.
    CHECK(ffma(0x80800000u, 0x00800000u, 0x00000000u, Rnd::kRn, 2, false) ==
          0x80000000u);
    CHECK(ffma(0x80800000u, 0x00800000u, 0x00000000u, Rnd::kRp, 2, false) ==
          0x80000000u);
    CHECK(ffma(0x80800000u, 0x00800000u, 0x00000000u, Rnd::kRz, 2, false) ==
          0x80000000u);
}

TEST(fp_f64_rounding) {
    // FP64: 1.0 + 2^-53 tie under RN stays 1.0, RP -> 1+2^-52.
    const std::uint64_t one = 0x3ff0000000000000ULL;
    const std::uint64_t half_ulp = 0x3ca0000000000000ULL;  // 2^-53
    const std::uint64_t rn = fadd64(one, half_ulp, Rnd::kRn, false);
    const std::uint64_t up = fadd64(one, half_ulp, Rnd::kRp, false);
    CHECK(rn == one);
    CHECK(up == 0x3ff0000000000001ULL);
}

TEST(fp_rounding_guard_restores_fenv) {
    // RoundingGuard must restore the host rounding mode on scope exit.
    std::fesetround(FE_DOWNWARD);
    {
        RoundingGuard rg(Rnd::kRn);
        CHECK(std::fegetround() == FE_TONEAREST);
    }
    CHECK(std::fegetround() == FE_DOWNWARD);
    std::fesetround(FE_TONEAREST);
}

// F64 -> F16/F32/BF16 direct rounding (no FP32 intermediate).  These are the
// values verified against the GPU in tools/diff_phase5.py.
TEST(fp_f64_to_narrow_direct) {
    using semu::fp::f64_to_f32;
    using semu::fp::f64_to_f16;
    using semu::fp::f64_to_bf16;
    // Double-rounding trap: F64 value where an FP32 intermediate would round
    // the F16 result differently than direct F64->F16 rounding.
    // 0x3ff0020008000000 = 1 + 2^-11 + tiny (F16 half-ULP above 1.0).
    // Direct F16 RN -> 0x3c01; via FP32 intermediate -> 0x3c00.
    CHECK(f64_to_f16(0x3ff0020008000000ULL, Rnd::kRn, false, false) == 0x3c01);
    // Directed rounding on the same value: RM/RZ -> 0x3c00, RP -> 0x3c01.
    CHECK(f64_to_f16(0x3ff0020008000000ULL, Rnd::kRm, false, false) == 0x3c00);
    CHECK(f64_to_f16(0x3ff0020008000000ULL, Rnd::kRz, false, false) == 0x3c00);
    CHECK(f64_to_f16(0x3ff0020008000000ULL, Rnd::kRp, false, false) == 0x3c01);
    // F64 0.5 -> F16 0x3800.
    CHECK(f64_to_f16(0x3fe0000000000000ULL, Rnd::kRn, false, false) == 0x3800);
    // F64 1.0 -> F16 0x3c00, F32 0x3f800000, BF16 0x3f80.
    CHECK(f64_to_f16(0x3ff0000000000000ULL, Rnd::kRn, false, false) == 0x3c00);
    CHECK(f64_to_f32(0x3ff0000000000000ULL, Rnd::kRn, false, false) == 0x3f800000);
    CHECK(f64_to_bf16(0x3ff0000000000000ULL, Rnd::kRn, false, false) == 0x3f80);
    // F64 -> F32 NaN preserves the F64 payload (quiet bit + top 23 bits).
    CHECK(f64_to_f32(0x7ff123456789abcdULL, Rnd::kRn, false, false) == 0x7fc91a2b);
    // F64 inf/NaN, +-0, subnormal, overflow.
    CHECK(f64_to_f16(0x7ff0000000000000ULL, Rnd::kRn, false, false) == 0x7c00);
    CHECK(f64_to_f16(0xfff0000000000000ULL, Rnd::kRn, false, false) == 0xfc00);
    CHECK(f64_to_f16(0x7ff8000000000000ULL, Rnd::kRn, false, false) == 0x7e00);
    CHECK(f64_to_f16(0x0000000000000000ULL, Rnd::kRn, false, false) == 0x0000);
    CHECK(f64_to_f16(0x8000000000000000ULL, Rnd::kRn, false, false) == 0x8000);
    // 2^-127 rounds to F16 zero (well below the 2^-24 subnormal unit).
    CHECK(f64_to_f16(0x3800000000000000ULL, Rnd::kRn, false, false) == 0x0000);
    // F64 max finite -> F16 overflow to inf (RN), BF16 max finite.
    CHECK(f64_to_f16(0x7fefffffffffffffULL, Rnd::kRn, false, false) == 0x7c00);
    CHECK(f64_to_bf16(0x47efffffe0000000ULL, Rnd::kRn, false, false) == 0x7f80);
}

TEST(fp_sat_special_values) {
    // SAT clamps to [0,1] (verified sm120): NaN -> +0, +inf -> 1.0,
    // -inf/-1 -> +0, >1 -> 1.0, 0.5/1.0 pass, -0 -> +0.
    using semu::fp::sat_f32;
    CHECK(sat_f32(0x7fc00000u) == 0x00000000u);  // NaN -> +0
    CHECK(sat_f32(0xffc00000u) == 0x00000000u);  // -NaN -> +0
    CHECK(sat_f32(0x7f800000u) == 0x3f800000u);  // +inf -> 1.0
    CHECK(sat_f32(0xff800000u) == 0x00000000u);  // -inf -> +0
    CHECK(sat_f32(0xbf800000u) == 0x00000000u);  // -1 -> +0
    CHECK(sat_f32(0x3f000000u) == 0x3f000000u);  // 0.5 unchanged
    CHECK(sat_f32(0x3f800000u) == 0x3f800000u);  // 1.0 unchanged
    CHECK(sat_f32(0x3f800001u) == 0x3f800000u);  // 1+ulp -> 1.0
    CHECK(sat_f32(0x40000000u) == 0x3f800000u);  // 2.0 -> 1.0
    CHECK(sat_f32(0x80000000u) == 0x00000000u);  // -0 -> +0
    CHECK(sat_f32(0x00000000u) == 0x00000000u);  // +0 unchanged
    // sat_f64 NaN/-0 normalization.
    using semu::fp::sat_f64;
    CHECK(sat_f64(0x7ff8000000000000ULL) == 0);
    CHECK(sat_f64(0x8000000000000000ULL) == 0);
}

TEST(fp_f64_to_f32_sat_finalize) {
    // SAT must apply on EVERY finite exit of f64_down_round, including the
    // paths that previously bypassed the clamp: zero, mantissa-carry
    // rounding to 2.0, and subnormal -> smallest-normal carry.
    using semu::fp::f64_to_f32;
    // -0.0 under SAT normalizes to +0.
    CHECK(f64_to_f32(0x8000000000000000ULL, Rnd::kRn, false, true) == 0x00000000);
    // Largest F64 below 2.0 rounds to F32 2.0 without SAT, but clamps to 1.0
    // with SAT (mantissa-carry path).
    CHECK(f64_to_f32(0x3fffffffffffffffULL, Rnd::kRn, false, false) == 0x40000000);
    CHECK(f64_to_f32(0x3fffffffffffffffULL, Rnd::kRn, false, true) == 0x3f800000);
    // 1.0 under SAT stays 1.0; -1.0 clamps to +0.
    CHECK(f64_to_f32(0x3ff0000000000000ULL, Rnd::kRn, false, true) == 0x3f800000);
    CHECK(f64_to_f32(0xbff0000000000000ULL, Rnd::kRn, false, true) == 0x00000000);
    // +inf -> 1.0, -inf -> +0, NaN -> +0, +0 -> +0 under SAT.
    CHECK(f64_to_f32(0x7ff0000000000000ULL, Rnd::kRn, false, true) == 0x3f800000);
    CHECK(f64_to_f32(0xfff0000000000000ULL, Rnd::kRn, false, true) == 0x00000000);
    CHECK(f64_to_f32(0x7ff8000000000000ULL, Rnd::kRn, false, true) == 0x00000000);
    CHECK(f64_to_f32(0x0000000000000000ULL, Rnd::kRn, false, true) == 0x00000000);
    // 0.5 under SAT stays 0.5.
    CHECK(f64_to_f32(0x3fe0000000000000ULL, Rnd::kRn, false, true) == 0x3f000000);
}

// ---------------------------------------------------------------------------
// Phase 5.5 fast path (fast_fp.hpp / fast_fp.cpp)
// ---------------------------------------------------------------------------

// Fast leaves must be bit-identical to the precise helpers for finite, RN,
// no-flush, no-SAT inputs.  Sweep a deterministic grid of values.
TEST(fast_fp_finite_rn_matches_precise) {
    // Deterministic finite test values: powers of 2, ±1.5, ±0.5, ulp-adjacent
    // pairs around 1, and a subnormal near the low end (exercises the
    // exceptional classification path).
    const std::uint32_t vals[] = {
        0x00000000u, 0x00000001u, 0x007fffffu, 0x00800000u,
        0x3f000000u, 0x3f800000u, 0x3f800001u, 0x3f7fffffu,
        0x3fc00000u, 0x40000000u, 0x40400000u, 0x7f7fffffu,
        0x80000000u, 0xbf800000u, 0xc0000000u, 0xff7fffffu,
    };
    int n = 0;
    for (std::uint32_t a : vals) {
        for (std::uint32_t b : vals) {
            const std::uint32_t p_add = fadd(a, b, Rnd::kRn, false, false);
            const std::uint32_t f_add = semu::fp::fast_fadd(a, b, 0, false, false);
            CHECK(f_add == p_add);
            const std::uint32_t p_mul = fmul(a, b, Rnd::kRn, false, false);
            const std::uint32_t f_mul = semu::fp::fast_fmul(a, b, 0, false, false);
            CHECK(f_mul == p_mul);
            for (std::uint32_t c : vals) {
                const std::uint32_t p_fma = ffma(a, b, c, Rnd::kRn, 0, false);
                const std::uint32_t f_fma = semu::fp::fast_ffma(a, b, c, 0, false, false);
                CHECK(f_fma == p_fma);
                ++n;
            }
        }
    }
    // FP64: exact binary inputs (1.5, 2.25, 0.75, 3.375, denormals).
    const std::uint64_t dvals[] = {
        0x3ff8000000000000ULL,  // 1.5
        0x4002000000000000ULL,  // 2.25
        0x3fe8000000000000ULL,  // 0.75
        0x400b000000000000ULL,  // 3.375
        0x0000000000000001ULL,  // smallest denormal
        0x8000000000000000ULL,  // -0
    };
    for (std::uint64_t a : dvals) {
        for (std::uint64_t b : dvals) {
            CHECK(semu::fp::fast_fadd64(a, b, 0, false) ==
                  fadd64(a, b, Rnd::kRn, false));
            CHECK(semu::fp::fast_fmul64(a, b, 0, false) ==
                  fmul64(a, b, Rnd::kRn, false));
            for (std::uint64_t c : dvals) {
                CHECK(semu::fp::fast_fma64(a, b, c, 0, false) ==
                      fma64(a, b, c, Rnd::kRn, false));
            }
        }
    }
    (void)n;
}

// Fast SAT clamps match the precise SAT results for the boundary set.
TEST(fast_fp_sat_matches_precise) {
    const std::uint32_t vals[] = {
        0x00000000u, 0x3f000000u, 0x3f800000u, 0x3f800001u,
        0x40000000u, 0x7f800000u, 0x7fc00000u, 0x80000000u,
        0xbf800000u, 0xff800000u, 0xffc00000u,
    };
    for (std::uint32_t v : vals) {
        CHECK(semu::fp::fast_sat32(v) == ::semu::fp::sat_f32(v));
    }
}

// F2I fast path: in-range values produce the same bits as the precise
// saturating conversion; out-of-range / NaN / Inf return false (fallback).
TEST(fast_f2i_checked_range) {
    using semu::fp::fast_f2i;
    std::uint32_t out = 0;
    // 3.0 -> S32 3, U32 3.
    CHECK(fast_f2i(0x40400000u, 4, 0, false, &out) && out == 3u);
    CHECK(fast_f2i(0x40400000u, 5, 0, false, &out) && out == 3u);
    // -1.5 truncates toward zero -> S32 -1 (mode 3 = RZ).
    CHECK(fast_f2i(0xbfc00000u, 5, 3, false, &out) && out == 0xffffffffu);
    // -1.5 under RN ties-to-even -> S32 -2.
    CHECK(fast_f2i(0xbfc00000u, 5, 0, false, &out) && out == 0xfffffffeu);
    // +Inf, NaN, and out-of-range U32 2^31 must fall back.
    CHECK(!fast_f2i(0x7f800000u, 4, 0, false, &out));
    CHECK(!fast_f2i(0x7fc00000u, 4, 0, false, &out));
    CHECK(!fast_f2i(0x7f800000u, 5, 0, false, &out));
    // 2^31 (0x4f000000) is representable as U32 but not S32.
    CHECK(fast_f2i(0x4f000000u, 4, 0, false, &out) && out == 0x80000000u);
    CHECK(!fast_f2i(0x4f000000u, 5, 0, false, &out));
    // Directed rounding toward -inf of -1.5 -> -2 (S32 0xfffffffe).
    CHECK(fast_f2i(0xbfc00000u, 5, 1, false, &out) && out == 0xfffffffeu);
    // Directed rounding toward +inf of -1.5 -> -1.
    CHECK(fast_f2i(0xbfc00000u, 5, 2, false, &out) && out == 0xffffffffu);
}

// Fast F2F conversions must match the precise helpers on the handled
// (dstfmt,srcfmt) pairs for ordinary finite RN inputs.
TEST(fast_f2f_matches_precise) {
    using semu::fp::fast_f2f;
    std::uint32_t out = 0, outhi = 0;
    // F32 -> F16 (dstfmt 0, srcfmt 1).
    CHECK(fast_f2f(0x3fc00000u, 0, 0, 1, &out, &outhi));   // 1.5
    CHECK(out == 0x3e00u);
    CHECK(fast_f2f(0x40000000u, 0, 0, 1, &out, &outhi));   // 2.0
    CHECK(out == 0x4000u);
    // F32 -> BF16 (dstfmt 3, srcfmt 1): round-to-nearest-even to 8-bit frac,
    // result in the LOW 16 bits (precise/sm120 contract: f32_to_bf16(1.0f)
    // == 0x00003f80).
    CHECK(fast_f2f(0x3f800000u, 0, 3, 1, &out, &outhi));   // 1.0
    CHECK(out == 0x3f80u);
    // Must match the precise helper directly.
    CHECK(out == semu::fp::f32_to_bf16(0x3f800000u, Rnd::kRn, false));
    // F16 -> F32 (dstfmt 1, srcfmt 0): exact.
    CHECK(fast_f2f(0x3e00u, 0, 1, 0, &out, &outhi));
    CHECK(out == 0x3fc00000u);
    // BF16 -> F32 (dstfmt 1, srcfmt 3): BF16 read from the LOW 16 bits,
    // zero-extended into the high half (precise: 0xBF80 -> 0xBF800000).
    CHECK(fast_f2f(0x0000bf80u, 0, 1, 3, &out, &outhi));
    CHECK(out == 0xbf800000u);
    CHECK(out == semu::fp::f2f(0x0000bf80u, 1 /*F32*/, 3 /*BF16*/, Rnd::kRn,
                               false, false));
    // F32 -> F64 (dstfmt 2, srcfmt 1): exact.
    CHECK(fast_f2f(0x3fc00000u, 0, 2, 1, &out, &outhi));   // 1.5
    CHECK(out == 0x00000000u && outhi == 0x3ff80000u);
    // F64 -> F32 (dstfmt 1, srcfmt 2): 1.5 down.
    CHECK(fast_f2f(0x00000000u, 0x3ff80000u, 1, 2, &out, &outhi));
    CHECK(out == 0x3fc00000u);
    // Unsupported pairs return false (caller falls back).
    CHECK(!fast_f2f(0x3fc00000u, 0, 0, 2, &out, &outhi));   // F16.F64 not native
    CHECK(!fast_f2f(0x3fc00000u, 0, 2, 0, &out, &outhi));   // F64.F16 not native
}

// Fast I2F: F32/F64 destinations match precise; F16/BF16 fall back.
// srcfmt uses the interpreter/I2F encoding convention (U8=0 S8=1 U16=2
// S16=3 U32=4 S32=5) — signed sources must sign-extend before converting.
TEST(fast_i2f_matches_precise) {
    using semu::fp::fast_i2f;
    std::uint32_t out = 0, outhi = 0;
    // U32 -> F64: exact.
    CHECK(fast_i2f(7u, 2, 4, &out, &outhi));
    CHECK(out == 0x00000000u && outhi == 0x401c0000u);   // 7.0 double
    // U32 -> F32: exact for 7.
    CHECK(fast_i2f(7u, 1, 4, &out, &outhi));
    CHECK(out == 0x40e00000u);   // 7.0 float
    // S32 -1 (0xFFFFFFFF) must become -1.0, NOT 4294967295.0 (Blocker-1).
    CHECK(fast_i2f(0xffffffffu, 1, 5, &out, &outhi));
    CHECK(out == 0xbf800000u);   // -1.0 float
    CHECK(fast_i2f(0xffffffffu, 2, 5, &out, &outhi));
    CHECK(out == 0x00000000u && outhi == 0xbff00000u);   // -1.0 double
    // S32 INT32_MIN -> -2147483648.0 exactly (fits in both F32/F64).
    CHECK(fast_i2f(0x80000000u, 1, 5, &out, &outhi));
    CHECK(out == 0xcf000000u);   // -2^31 float
    // S16/S8 sign-extension.
    CHECK(fast_i2f(0xffffu, 1, 3, &out, &outhi));        // S16 -1
    CHECK(out == 0xbf800000u);
    CHECK(fast_i2f(0xffu, 1, 1, &out, &outhi));          // S8 -1
    CHECK(out == 0xbf800000u);
    // U16/U8 unsigned.
    CHECK(fast_i2f(0xffffu, 1, 2, &out, &outhi));        // U16 65535
    CHECK(out == 0x477fff00u);
    // F16/BF16 destinations (dstfmt 0 / 3) not native.
    CHECK(!fast_i2f(7u, 0, 4, &out, &outhi));
    CHECK(!fast_i2f(7u, 3, 4, &out, &outhi));
}

}  // namespace

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-fp");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu fp tests\n");
    }
    return failures == 0 ? 0 : 1;
}
