// L0 unit tests: bit-accurate tensor-core math engine (SIM_PLAN Phase 9).
//
// Tests semu::tensor against the hardware-verified vectors of the Python
// reference (tools/hmma_model.py selftest) plus boundary/edge inputs.  The
// interpreter and the Python differential harness use the same code, so these
// vectors pin the engine to the model bit-for-bit.

#include <semu/tensor/tensor.hpp>

#include <cstdint>
#include <cstdio>

#include "test_framework.hpp"

using semu::tensor::Format;
using semu::tensor::Shape;

namespace {

std::uint32_t fiv(float v) {
    std::uint32_t x;
    __builtin_memcpy(&x, &v, sizeof(x));
    return x;
}

}  // namespace

// ---------------------------------------------------------------------------
// FDA core: hardware-verified vectors (tools/hmma_model.py selftest)
// ---------------------------------------------------------------------------

TEST(tensor_fda_selftest_vectors) {
    const std::uint32_t ONE_B = 0x3F80, ONE_F = 0x3C00, B3340 = 0x3340;
    std::uint32_t a1b[4] = {ONE_B, ONE_B, ONE_B, ONE_B};
    std::uint32_t b3340[4] = {B3340, B3340, B3340, B3340};
    std::uint32_t ones[4] = {ONE_B, ONE_B, ONE_B, ONE_B};

    CHECK(semu::tensor::fda(0x3F800000, a1b, b3340, 4, Format::kBf16) ==
           0x3F800001);  // RZ -> 1 ulp
    CHECK(semu::tensor::fda(0xBF800000, a1b, b3340, 4, Format::kBf16) ==
           0xBF7FFFFE);
    CHECK(semu::tensor::fda(0, a1b, b3340, 4, Format::kBf16) == 0x34400000);
    {
        std::uint32_t p8[4] = {0x4000, 0x4000, 0x4000, 0x4000};
        CHECK(semu::tensor::fda(0x49800000, a1b, p8, 4, Format::kBf16) ==
               0x49800040);
    }
    CHECK(semu::tensor::fda(0x7FC00000, a1b, b3340, 4, Format::kBf16) ==
           0x7FFFFFFF);  // c NaN -> canonical
    {
        std::uint32_t an[4] = {0x7FC0, ONE_B, ONE_B, ONE_B};
        CHECK(semu::tensor::fda(0, an, b3340, 4, Format::kBf16) ==
               0x7FFFFFFF);
    }
    {
        std::uint32_t z[4] = {0, 0, 0, 0};
        std::uint32_t inf[4] = {0x7F80, 0x7F80, 0x7F80, 0x7F80};
        CHECK(semu::tensor::fda(0, z, inf, 4, Format::kBf16) == 0x7FFFFFFF);
    }
    {
        std::uint32_t a[4] = {0x7F80, ONE_B, ONE_B, ONE_B};
        std::uint32_t b[4] = {0xFF80, 0, 0, 0};
        CHECK(semu::tensor::fda(0, a, b, 4, Format::kBf16) == 0xFF800000);
    }
    {
        std::uint32_t a[4] = {0x7F80, 0x7F80, 0, 0};
        std::uint32_t b[4] = {0x7F80, 0xFF80, 0, 0};
        CHECK(semu::tensor::fda(0, a, b, 4, Format::kBf16) == 0x7FFFFFFF);
    }
    CHECK(semu::tensor::fda(0x7F800000, a1b, b3340, 4, Format::kBf16) ==
           0x7F800000);
    CHECK(semu::tensor::fda(0xFF800000, a1b, b3340, 4, Format::kBf16) ==
           0xFF800000);
    {
        // c=-inf joins the product-sign mix: c=-inf + product +inf -> NaN.
        std::uint32_t a[4] = {0x7F80, 0x7F80, 0x7F80, 0x7F80};
        std::uint32_t b[4] = {0x7F80, 0x7F80, 0x7F80, 0x7F80};
        CHECK(semu::tensor::fda(0xFF800000, a, b, 4, Format::kBf16) ==
               0x7FFFFFFF);
    }
    {
        std::uint32_t a[4] = {0xBF80, ONE_B, ONE_B, ONE_B};
        std::uint32_t b[4] = {0x7F80, 0, 0, 0};
        CHECK(semu::tensor::fda(0, a, b, 4, Format::kBf16) == 0xFF800000);
    }
    // f16
    {
        std::uint32_t a[4] = {ONE_F, ONE_F, ONE_F, ONE_F};
        std::uint32_t b[4] = {0x0003, 0x0003, 0x0003, 0x0003};
        CHECK(semu::tensor::fda(0x3F800000, a, b, 4, Format::kF16) ==
               0x3F800006);
    }
    {
        std::uint32_t a[4] = {0x7F80, 0x7F80, 0x7F80, 0x7F80};
        std::uint32_t b[4] = {0x7F80, 0x7F80, 0x7F80, 0x7F80};
        CHECK(semu::tensor::fda(0, a, b, 4, Format::kBf16) == 0x7F800000);
    }
    {
        std::uint32_t a[4] = {ONE_F, ONE_F, ONE_F, ONE_F};
        std::uint32_t b[4] = {0x0001, 0x0001, 0x0001, 0x0001};
        CHECK(semu::tensor::fda(0, a, b, 4, Format::kF16) == 0x34800000);
    }
    (void)ones;
}

// ---------------------------------------------------------------------------
// QMMA fp8: hardware-verified m16n8k32 e4m3 fragment (test_qmma.py)
// ---------------------------------------------------------------------------

TEST(tensor_qmma_k32_hardware_vector) {
    std::uint32_t a[4] = {0x38383838, 0x38383838, 0x38383838, 0x38383838};
    std::uint32_t b[2] = {0x38383838, 0x38383838};
    std::uint32_t c[4] = {fiv(10), fiv(11), fiv(12), fiv(13)};
    std::uint32_t out[4];
    semu::tensor::qmma_k32(a, b, c, Format::kFp8E4M3, out);
    CHECK(out[0] == fiv(42) && out[1] == fiv(43));
    CHECK(out[2] == fiv(44) && out[3] == fiv(45));
}

// ---------------------------------------------------------------------------
// OMMA MXFP4: hardware-verified m16n8k64 e2m1 fragment (test_omma.py)
// ---------------------------------------------------------------------------

TEST(tensor_omma_k64_hardware_vector) {
    std::uint32_t a[4] = {0x22222222, 0x22222222, 0x22222222, 0x22222222};
    std::uint32_t b[2] = {0x22222222, 0x22222222};
    std::uint32_t c[4] = {0, 0, 0, 0};
    std::uint32_t out[4];
    semu::tensor::omma_k64(a, b, c, 0x7F7F7F7F, 0x7F7F7F7F, 0, out);
    CHECK(out[0] == fiv(64) && out[1] == fiv(64));
    CHECK(out[2] == fiv(64) && out[3] == fiv(64));
    // 2X scale on k0..31 only: 32*2 + 32*1 = 96.
    semu::tensor::omma_k64(a, b, c, 0x017F7F80, 0x7F7F7F7F, 0, out);
    CHECK(out[0] == fiv(96) && out[1] == fiv(96));
    CHECK(out[2] == fiv(96) && out[3] == fiv(96));
    // NaN scale -> canonical NaN.
    semu::tensor::omma_k64(a, b, c, 0xFFFFFFFF, 0x7F7F7F7F, 0, out);
    CHECK(out[0] == 0x7FFFFFFF && out[1] == 0x7FFFFFFF);
}

// ---------------------------------------------------------------------------
// Shape resolution
// ---------------------------------------------------------------------------

TEST(tensor_shapes) {
    Shape s;
    CHECK(semu::tensor::hmma_shape(1, 1, &s) && s.regs_a == 4 &&
           s.regs_b == 2 && s.regs_c == 4 && s.k == 16);
    CHECK(semu::tensor::hmma_shape(0, 0, &s) && s.regs_a == 2 &&
           s.regs_b == 1 && s.regs_c == 4 && s.k == 8);
    CHECK(!semu::tensor::hmma_shape(2, 0, &s));  // 1684 TF32 only
    CHECK(!semu::tensor::hmma_shape(1, 2, &s));  // TF32 source
    CHECK(semu::tensor::qmma_shape(1, &s) && s.regs_a == 4 &&
           s.regs_b == 2 && s.regs_c == 4 && s.k == 32);
    CHECK(semu::tensor::qmma_shape(0, &s) && s.regs_a == 2 &&
           s.regs_b == 1 && s.regs_c == 4 && s.k == 16);
    CHECK(!semu::tensor::qmma_shape(2, &s));
    CHECK(semu::tensor::omma_shape(&s) && s.regs_a == 4 && s.regs_b == 2 &&
           s.regs_c == 4 && s.k == 64);
}

// ---------------------------------------------------------------------------
// E8M0 exponent
// ---------------------------------------------------------------------------

TEST(tensor_e8m0) {
    CHECK(semu::tensor::e8m0_exp(0x7F) == 0);
    CHECK(semu::tensor::e8m0_exp(0x80) == 1);
    CHECK(semu::tensor::e8m0_exp(0x7E) == -1);
    CHECK(semu::tensor::e8m0_exp(0x00) == -127);
    CHECK(semu::tensor::e8m0_exp(0xFF) == -128);  // NaN sentinel
}

// ---------------------------------------------------------------------------
// Boundary / edge inputs: NaN/Inf/denormal/tie through the fragment entry
// points (mirrors the selftest + precision notes).
// ---------------------------------------------------------------------------

TEST(tensor_boundary_specials) {
    std::uint32_t a[4] = {0, 0, 0, 0}, b[2] = {0, 0}, c[4] = {0, 0, 0, 0};
    std::uint32_t out[4];
    // c NaN propagates canonical NaN through every fragment entry.
    c[0] = c[1] = c[2] = c[3] = 0x7FC00000;
    semu::tensor::hmma_k16(a, b, c, Format::kBf16, out);
    CHECK(out[0] == 0x7FFFFFFF && out[1] == 0x7FFFFFFF);
    CHECK(out[2] == 0x7FFFFFFF && out[3] == 0x7FFFFFFF);
    c[0] = c[1] = c[2] = c[3] = 0;
    // bf16 NaN input -> canonical.
    a[0] = 0x7FC0;
    semu::tensor::hmma_k8(a, b, c, Format::kBf16, out);
    CHECK(out[0] == 0x7FFFFFFF);
    a[0] = 0;
    // fp8 NaN (0x7F / 0xFF all-ones) -> canonical; exp-max mant<7 ordinary.
    std::uint32_t qa[4] = {0x7F, 0, 0, 0}, qb[2] = {0x38, 0};
    semu::tensor::qmma_k32(qa, qb, c, Format::kFp8E4M3, out);
    CHECK(out[0] == 0x7FFFFFFF);
    std::uint32_t qa2[4] = {0x7C, 0, 0, 0};
    semu::tensor::qmma_k32(qa2, qb, c, Format::kFp8E4M3, out);
    // The single (0x7C,0x38) pair folds 4x: 384 * 4 = 1536 = 0x44C00000
    // (matches the Python selftest's 0x44C00000 expectation).
    CHECK(out[0] == 0x44C00000);
    // subnormal f16 input honored.
    std::uint32_t fa[4] = {0x00010001, 0x00010001, 0x00010001, 0x00010001};
    std::uint32_t fb[2] = {0x3C003C00, 0x3C003C00};
    semu::tensor::hmma_k16(fa, fb, c, Format::kF16, out);
    // 16 products of 2^-24 * 1.0 = 2^-20 = 0x35800000.
    CHECK(out[0] == 0x35800000 && out[1] == 0x35800000);
    // RZ tie: c = 1.0 + 3*2^-24 truncates (not rounds) to 1 ulp.
    std::uint32_t oneb[4] = {0x3F80, 0x3F80, 0x3F80, 0x3F80};
    std::uint32_t small[4] = {0x3340, 0x3340, 0x3340, 0x3340};
    CHECK(semu::tensor::fda(0x3F800000, oneb, small, 4, Format::kBf16) ==
           0x3F800001);
    // Accumulator inf: c=-inf returns -inf from the fp8 path.
    c[0] = c[1] = c[2] = c[3] = 0xFF800000;
    semu::tensor::qmma_k16(a, b, c, Format::kFp8E4M3, out);
    CHECK(out[0] == 0xFF800000 && out[3] == 0xFF800000);
}

int main() {
    return semu_test::run_all("tensor");
}
