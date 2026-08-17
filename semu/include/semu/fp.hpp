#pragma once

#include <cstdint>

// Bit-exact FP semantics for sm120 (SIM_PLAN Phase 5).
//
// The host x86-64 is IEEE-754 with correctly-rounded single/double ops; by
// mapping SASS rounding modes onto fenv and handling FTZ/FMZ flushes and
// SAT explicitly, we reproduce the GPU's FP results bit-for-bit.
//
// Compile contract for fenv: the translation unit that computes FP results
// under a dynamic rounding mode must (a) declare `#pragma STDC FENV_ACCESS
// ON` (fp.cpp does) and (b) be built with `-frounding-math` (see
// semu/src/CMakeLists.txt) so the compiler cannot constant-fold or
// reassociate away the rounding-mode dependence of +,-,*,/ and fmaf.
//
// MUFU (RCP/SQRT/EX2/LG2/SIN/COS/RSQ) uses hardware lookup tables that are
// NOT bit-exact on the host, so those instructions fault at the interpreter
// (see interpreter do_mufu); FCHK (division) is likewise not modeled.

namespace semu::fp {

// NVIDIA canonical NaN for FP32/FP64 arithmetic results (empirically
// 0x7fffffff / 0x7fffffffffffffff on sm120: every NaN result from
// FADD/FMUL/FFMA is the positive quiet NaN with an all-ones payload).
constexpr std::uint32_t kCanonicalNan32 = 0x7fffffff;
constexpr std::uint64_t kCanonicalNan64 = 0x7fffffffffffffffULL;

// SASS rounding modes (Round1/Round3 enum values in the ISA).
enum class Rnd : std::uint8_t {
    kRn = 0,  // round-to-nearest-even (default / ROUND)
    kRm = 1,  // toward -inf (FLOOR)
    kRp = 2,  // toward +inf (CEIL)
    kRz = 3,  // toward zero (TRUNC)
};

// Apply a rounding mode to the fenv for a single operation.  Returns the
// previous mode; caller restores it after.
int push_rounding(Rnd rnd);

// Restore the fenv rounding mode saved by push_rounding.
void pop_rounding(int saved);

// RAII rounding-mode guard: sets the fenv rounding mode for the scope and
// restores the previous mode on any exit (including exceptions / early
// return).  This is the safe way to bracket a FP computation that must run
// under a specific rounding mode.
class RoundingGuard {
public:
    explicit RoundingGuard(Rnd rnd) : saved_(push_rounding(rnd)) {}
    ~RoundingGuard() { pop_rounding(saved_); }
    RoundingGuard(const RoundingGuard&) = delete;
    RoundingGuard& operator=(const RoundingGuard&) = delete;

private:
    int saved_;
};

// --- FP32 helpers ---------------------------------------------------------
// Each returns the raw bit pattern of the result.  `flush` applies FTZ/FMZ
// (subnormal inputs flushed to signed zero).  sat clamps to [0,1] after.
std::uint32_t fadd(std::uint32_t a, std::uint32_t b, Rnd rnd, bool flush,
                   bool sat);
std::uint32_t fmul(std::uint32_t a, std::uint32_t b, Rnd rnd, bool flush,
                   bool sat);
std::uint32_t ffma(std::uint32_t a, std::uint32_t b, std::uint32_t c,
                   Rnd rnd, bool fmz, bool sat);

// --- FP64 helpers ---------------------------------------------------------
std::uint64_t fadd64(std::uint64_t a, std::uint64_t b, Rnd rnd, bool sat);
std::uint64_t fmul64(std::uint64_t a, std::uint64_t b, Rnd rnd, bool sat);
std::uint64_t fma64(std::uint64_t a, std::uint64_t b, std::uint64_t c,
                    Rnd rnd, bool sat);

// --- Conversions ----------------------------------------------------------
// dst_format / src_format are the F2F/F2I/I2F `dstfmt`/`srcfmt` enum values
// (FP16=0, FP32=1, FP64=2, BF16=3, U32=4, S32=5, U16=6, S16=7, U8=8, S8=9).
// Returns the destination bit pattern (or the raw result for int dst).
std::uint32_t f2f(std::uint32_t src_bits, int dstfmt, int srcfmt, Rnd rnd,
                  bool ftz, bool sat);
std::uint64_t f2f64(std::uint32_t src_bits, int dstfmt, int srcfmt, Rnd rnd,
                    bool ftz, bool sat);
std::uint64_t i2f(std::uint64_t src, int dstfmt, int srcfmt, Rnd rnd,
                  bool sat);
std::uint64_t f2i(std::uint32_t src_bits, int dstfmt, int srcfmt, Rnd rnd,
                  bool ftz, bool ntz);

// Flush subnormal fp32/64 to zero (FTZ/FMZ input flush).
std::uint32_t flush_f32(std::uint32_t bits);
std::uint64_t flush_f64(std::uint64_t bits);

// fp16 <-> fp32 raw bit conversions.
std::uint32_t f16_to_f32(std::uint16_t half);
std::uint16_t f32_to_f16(std::uint32_t bits, Rnd rnd, bool ftz);
std::uint32_t f32_to_bf16(std::uint32_t bits, Rnd rnd, bool ftz);

// FP64 -> narrow float conversions (F64.F32 / F64.F16 / F64.BF16).
//
// These round DIRECTLY from the FP64 sign / exponent / 53-bit significand to
// the target precision.  They must NOT go through an FP32 intermediate
// (which would double-round and lose directed-rounding fidelity).  Each
// returns the raw 32-bit register pattern: F32 in bits[31:0], F16/BF16 in
// bits[15:0] (high half zero).  `sat` clamps to [0,1] for the F32 target.
std::uint32_t f64_to_f32(std::uint64_t bits, Rnd rnd, bool ftz, bool sat);
std::uint32_t f64_to_f16(std::uint64_t bits, Rnd rnd, bool ftz, bool sat);
std::uint32_t f64_to_bf16(std::uint64_t bits, Rnd rnd, bool ftz, bool sat);

// Clamp a float to [0,1] (SAT); returns raw bits.
std::uint32_t sat_f32(std::uint32_t bits);
std::uint64_t sat_f64(std::uint64_t bits);

}  // namespace semu::fp
