#pragma once

#include <cstdint>
#include <span>
#include <string>
#include <vector>

// Execution mode and run configuration (SIM_PLAN Phase 5.5 + Phase 6).
//
// Phase 5.5 adds a performance-first compute semantics mode to the single CPU
// interpreter.  The decoder, thread state, scheduler, control flow, faults,
// instruction limit and step/debugger state are shared unchanged; only the FP
// /conversion leaf computations are replaced by an FpSemantics policy
// selected once at launch.
//
// Precise mode is the default and the only mode that claims sm_120 bit
// exactness (it is what the Phase 5 GPU differential validates).  Fast mode
// uses host float/double/std::fma under a run-scope round-to-nearest fenv and
// may differ in FP results (NaN payloads, signed zero, subnormals, directed
// rounding, FTZ/FMZ details, double-rounding) — see fast_fp.hpp.

namespace semu {

enum class ExecutionMode {
    kPrecise,  // bit-exact sm_120 semantics via fp.cpp (default)
    kFast,     // host-float fast path via fast_fp.cpp
};

// When to route a single FP leaf operation to the precise helper inside a
// fast run.  The decision is made per lane after its operands are read; it
// never restarts the whole launch.
enum class FastFpFallback {
    kNone,             // never fall back (fastest; for --fast perf measurement)
    kExceptional,      // fall back when an operand / result is NaN/Inf/subnormal
                       // or the instruction requests non-RN / FTZ / FMZ
                       // (suggested library default)
    kStrictModifiers,  // fall back only for non-RN / FTZ / FMZ / exact-NaN
                       // payload needs; ordinary exceptional values stay native
};

// Fast-mode execution counters surfaced on Result.
struct FastExecutionStats {
    std::uint64_t fast_fp_ops = 0;        // FP leaves computed natively
    std::uint64_t precise_fallback_ops = 0;  // routed to the precise helper
    std::uint64_t ignored_modifier_ops = 0;  // RN executed a non-RN / FTZ / FMZ
    bool any_fast_fp = false;             // true once any fast FP leaf ran
};

// Phase 6 memory configuration for a run.  The buffers are referenced (not
// owned) for the duration of run_result: `global` is the device global
// buffer, `params` the packed kernel parameter bytes (constant0 0x380+), and
// `shared`/`local` per-CTA/per-warp window sizes.  Empty/default = no memory
// (pure compute, matching pre-Phase-6 behavior).
struct MemoryConfig {
    std::vector<std::uint8_t>* global = nullptr;  // global buffer backing
    std::vector<std::uint8_t>* params = nullptr;  // kernel params (constant0)
    std::uint64_t shared_size = 0;                // per-CTA shared window
    std::uint64_t local_size = 0;                 // per-warp local window
    bool enabled() const { return global != nullptr || params != nullptr; }
};

// Phase 6 Step 2B: L1TEX performance-estimation mode.  These are TRACE-ONLY
// toggles: they never change functional memory values, scoreboard completion,
// atomic linearization, or happens-before edges.  The UnifiedV1 estimator is
// only applied to explicit coupled L1-read -> shared-write transfers
// (LDGSTS / cp.async); ordinary LDG/STG/LDS/STS/atomic/constant paths never
// feed it.
enum class L1TexMode {
    kOff,             // no estimator events (default)
    kTraceOnly,       // emit model-versioned prediction events; no timing
};

// Phase 6 Step 2C: L2 event mode.  Functional value is always decoupled from
// L2 event scheduling; these toggles only control whether trace events are
// produced.
enum class L2Mode {
    kOff,            // no L2 trace events (default)
    kFunctionalEvents,  // emit L2 request/completion events (trace-only)
};

// Phase 6 Step 2D: data-race detection mode.
enum class RaceMode {
    kOff,     // no shadow allocation, no reports (default)
    kReport,  // detect and report data races (trace-only; no functional effect)
};

// Phase 6 Step 2B memory-model options (separate from a vague `timing=true`).
struct MemoryModelOptions {
    L1TexMode l1tex = L1TexMode::kOff;
    L2Mode l2 = L2Mode::kOff;
    RaceMode race = RaceMode::kOff;
    std::string l1tex_model = "unified-v1";
    std::uint32_t simulated_sm_count = 1;
    std::uint64_t deterministic_seed = 0;
};

// Run configuration for Interpreter::run_result & friends.
struct RunOptions {
    ExecutionMode mode = ExecutionMode::kPrecise;
    FastFpFallback fast_fp_fallback = FastFpFallback::kExceptional;
    std::uint64_t instruction_limit = 1000000;
    bool report_trace = false;
    // Phase 6 memory setup (defaults to compute-only).
    MemoryConfig memory;
    // Phase 6 Step 2: worker count.  1 (default) = deterministic single
    // worker (all CTAs interleaved on one thread); >1 = throughput mode with
    // a CPU worker pool, each CTA pinned to one worker.  Race-free kernels
    // must produce identical results for any worker count.
    int worker_count = 1;
    // Phase 6 Step 2B: performance-estimation mode (trace-only).
    MemoryModelOptions model;

    // True when the run is allowed to produce FP results that differ from the
    // sm_120 bit-exact model (i.e. fast mode with at least one fast FP leaf).
    bool approximate() const { return mode == ExecutionMode::kFast; }
};

}  // namespace semu
