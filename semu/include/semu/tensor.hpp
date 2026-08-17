#pragma once

// Bit-accurate tensor-core math engine (SIM_PLAN Phase 9).
//
// C++ port of the repo's verified reference model `tools/hmma_model.py`
// (FDA = Fused-Dot-Add after MMA-Sim arXiv:2511.10909, Hopper/Blackwell
// column; GDFS = group-of-16 block-scaled MXFP4 path).  The engine is what the
// interpreter uses to execute HMMA / QMMA / OMMA functionally; it is also the
// single source the C++ unit tests and the Python differential harness compare
// against (so interpreter results equal the Python model bit-for-bit by
// construction).
//
// Scope (Phase 9):
//   - HMMA.1688/16816.F32 (f16 / bf16 sources, FP32 accumulator)  -- verified
//   - QMMA.16816/16832.F32 (fp8 e4m3/e5m2/e3m4/e2m3/e3m2/e2m1)     -- verified
//     for e4m3; the other fp8 formats follow the identical FDA structure
//   - OMMA.SF.16864.F32.E2M1.E2M1.E8 (MXFP4 block scale, GDFS F=35) -- verified
//
// Fragment mapping is the probed per-lane model of tools/hmma_model.py: each
// lane's D0..D3 are a function of that lane's own A/B/C register words, with
// each (a,b) slot pair folded 4x (k16/k32) or 2x/4x (k8).  This is the only
// hardware-verified fragment behaviour (identical-fragment kernels); arbitrary
// per-lane layouts are unverified on SM120 (GPU differential suspended) and
// the engine deliberately preserves the verified model rather than guessing a
// different coupling.

#include <cstdint>
#include <cstddef>

namespace semu::tensor {

// Source element formats the math engine understands.
enum class Format : std::uint8_t {
    kF16,        // IEEE fp16 (10b mantissa, 5b exp, bias 15)
    kBf16,       // BFloat16 (7b mantissa, 8b exp, bias 127)
    kFp8E4M3,    // 4-bit exp / 3-bit mantissa, bias 7
    kFp8E5M2,    // 5-bit exp / 2-bit mantissa, bias 15
    kFp8E3M4,    // 3-bit exp / 4-bit mantissa, bias 3
    kFp8E2M3,    // 2-bit exp / 3-bit mantissa, bias 1
    kFp8E3M2,    // 3-bit exp / 2-bit mantissa, bias 3
    kFp8E2M1,    // 2-bit exp / 1-bit mantissa, bias 1  (fp8 width)
    kMxfp4E2M1,  // 4-bit MXFP4 e2m1 (sign bit 3, exp 2:1 bias 1, mantissa bit 0)
};

// Same as fp8 fp8 formats but distinguished from the 4-bit MXFP4 packing.
constexpr bool is_fp8(Format f) {
    return f >= Format::kFp8E4M3 && f <= Format::kFp8E2M1;
}

// One output element: d = f(c, a_0..k-1, b_0..k-1) per the FDA model.
// `a_vals`/`b_vals` hold the raw element bits (16-bit for f16/bf16, 8-bit for
// fp8, 4-bit for mxfp4) in the low bits of each entry; both must be the same
// length (the k products).  `c` is the FP32 accumulator bit pattern.  Returns
// the FP32 result bit pattern.
std::uint32_t fda(std::uint32_t c, const std::uint32_t* a_vals,
                  const std::uint32_t* b_vals, std::size_t k, Format fmt);

// OMMA GDFS path (MXFP4 e2m1, group-of-16, F=35 fractional bits, E8M0 scale).
// `a_vals`/`b_vals` are 4-bit e2m1 elements (k each); `a_scale_exp` /
// `b_scale_exp` are the *unbiased* exponents of the E8M0 scale columns (as
// returned by e8m0_exp: a NaN scale is the sentinel -128), one per K/32 block
// (K=64 -> 2 entries).
std::uint32_t gdfs(std::uint32_t c, const std::uint8_t* a_vals,
                   const std::uint8_t* b_vals, std::size_t k,
                   const std::int8_t* a_scale_exp,
                   const std::int8_t* b_scale_exp, std::size_t n_scales);

// E8M0 scale exponent (unbiased): 2^(b-127).  The NaN byte 0xFF maps to the
// sentinel -128 (INT8_MIN), which no valid exponent (-127..127) can hit.
std::int8_t e8m0_exp(std::uint8_t byte);

// Fragment shape descriptor (register counts per lane for the F32-accumulator
// variants the engine implements).
struct Shape {
    int regs_a = 0;    // A fragment register count (32-bit words per lane)
    int regs_b = 0;    // B fragment register count
    int regs_c = 4;    // C/D accumulator register count (F32: always 4)
    int k = 0;         // reduction depth
};

// Shape resolution helpers ----------------------------------------------------
// HMMA (m16n8k8 / m16n8k16): A/B reg count depends on size + srcfmt.
//   size: 0 = 1688 (k8), 1 = 16816 (k16), 2 = 1684 (k4, TF32 only).
//   srcfmt: 0=F16 1=BF16 2=TF32 3=E6M9.  TF32/E6M9 are decode-only (the engine
//   only implements f16/bf16); returns false for them.
bool hmma_shape(int size, int srcfmt, Shape* out);

// QMMA (m16n8k16 / m16n8k32): size 0 = 16816, 1 = 16832.  F32 accumulator.
bool qmma_shape(int size, Shape* out);

// OMMA.SF: only 16864 (k64, mxfp4 e2m1, 2X block scale).
bool omma_shape(Shape* out);

// Per-lane fragment evaluation -------------------------------------------------
// These mirror tools/hmma_model.py's frag_* functions: given a lane's register
// words they compute that lane's D0..D3 (FP32 bits).  Each register word is 32
// bits; elements are packed little-endian (half-lo/half-hi, byte i, nibble n).
//
// HMMA m16n8k16:  a[4] b[2] c[4]  (8 f16/bf16 A elems, 4 B elems, 4 f32 C)
// HMMA m16n8k8 :  a[2] b[1] c[4]  (4 A elems, 2 B elems)
// QMMA m16n8k32:  a[4] b[2] c[4]  (16 fp8 A elems, 8 B elems)
// QMMA m16n8k16:  a[2] b[1] c[4]  (8 fp8 A elems, 4 B elems)
// OMMA m16n8k64:  a[4] b[2] c[4]  + Re/Rh (E8M0 scale words) + byte-id sel
void hmma_k16(const std::uint32_t a[4], const std::uint32_t b[2],
              const std::uint32_t c[4], Format fmt, std::uint32_t out[4]);
void hmma_k8(const std::uint32_t a[2], const std::uint32_t b[1],
             const std::uint32_t c[4], Format fmt, std::uint32_t out[4]);
void qmma_k32(const std::uint32_t a[4], const std::uint32_t b[2],
              const std::uint32_t c[4], Format fmt, std::uint32_t out[4]);
void qmma_k16(const std::uint32_t a[2], const std::uint32_t b[1],
              const std::uint32_t c[4], Format fmt, std::uint32_t out[4]);
// OMMA: scale words `re`/`rh` (32-bit: byte0 scales k 0..31, byte1 k 32..63),
// `sel` = byte-id selector (only 0 verified legal).
void omma_k64(const std::uint32_t a[4], const std::uint32_t b[2],
              const std::uint32_t c[4], std::uint32_t re, std::uint32_t rh,
              std::uint32_t sel, std::uint32_t out[4]);

}  // namespace semu::tensor