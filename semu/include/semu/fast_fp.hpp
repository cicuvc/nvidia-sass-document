#pragma once

#include <cstdint>

#include <semu/execution.hpp>

// Fast FP leaf semantics for the fast interpreter execution mode
// (SIM_PLAN Phase 5.5).  These replace the precise bit-exact helpers of
// fp.cpp with native host float/double/std::fma under a run-scope
// round-to-nearest fenv.  They are NOT bit-exact vs sm_120; the precise
// path remains the only one the Phase 5 GPU differential validates.
//
// Callers route individual FP leaf operations here; the policy decides per
// lane (after operands are read) whether to fall back to the precise helper.
// Counters live in the interpreter's FastExecutionStats.

namespace semu::fp {

// Rounding mode indices shared with fp.hpp (RN=0, RM=1, RP=2, RZ=3).
constexpr int kFastRn = 0;
constexpr int kFastRm = 1;
constexpr int kFastRp = 2;
constexpr int kFastRz = 3;

// Apply the .SAT clamp to an FP32 result bit pattern: NaN/-0/negative -> +0,
// >1/+Inf -> 1.0, in-range unchanged.  Cheap and fenv-independent.
std::uint32_t fast_sat32(std::uint32_t bits);

// FP32 arithmetic.  Each returns the raw 32-bit bit pattern of the native
// host result.  `rnd` / `ftz` / `fmz` / `sat` are passed for policy
// bookkeeping; the fast path itself uses RN and only honors SAT.
std::uint32_t fast_fadd(std::uint32_t a, std::uint32_t b, int rnd,
                        bool ftz, bool sat);
std::uint32_t fast_fmul(std::uint32_t a, std::uint32_t b, int rnd,
                        bool ftz, bool sat);
std::uint32_t fast_ffma(std::uint32_t a, std::uint32_t b, std::uint32_t c,
                        int rnd, bool fmz, bool sat);

// FP64 arithmetic (raw 64-bit patterns).
std::uint64_t fast_fadd64(std::uint64_t a, std::uint64_t b, int rnd,
                          bool sat);
std::uint64_t fast_fmul64(std::uint64_t a, std::uint64_t b, int rnd,
                          bool sat);
std::uint64_t fast_fma64(std::uint64_t a, std::uint64_t b, std::uint64_t c,
                         int rnd, bool sat);

// F2I conversion with a checked range (never an unguarded cast): the fast
// path returns nullopt when the input is NaN/Inf or outside the destination
// range, so the caller must fall back to the precise saturating helper.
// Returns the raw U32/S32 pattern when representable.
bool fast_f2i(std::uint32_t src_bits, int dstfmt, int rnd, bool ftz,
              std::uint32_t* out);

// F2F conversions on the hot paths (RN, no FTZ/FMZ).  Returns false when the
// requested (dstfmt,srcfmt) pair is not handled natively, so the caller falls
// back to the precise helper.  `src_hi` carries the high half of a 64-bit
// source (F64); `out_hi` mirrors the interpreter's dstfmt==2 (F64) write pair.
bool fast_f2f(std::uint32_t src, std::uint32_t src_hi, int dstfmt, int srcfmt,
              std::uint32_t* out, std::uint32_t* out_hi);

// I2F conversion for F32/F64 destinations (RN; SAT via cheap clamp).  F16/
// BF16 destinations are not handled natively (return false -> precise).
bool fast_i2f(std::uint32_t val, int dstfmt, int srcfmt, std::uint32_t* out,
              std::uint32_t* out_hi);

}  // namespace semu::fp
