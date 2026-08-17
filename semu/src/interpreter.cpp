// Interpreter execution core and control flow (SIM_PLAN Phase 4).
//
// Per-lane independent thread scheduling: each thread keeps its own GPR /
// predicate / lane PC / exit state; a warp executes one dynamic warp
// instruction for the set of active lanes sharing the same PC.

#include <semu/interpreter.hpp>

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <thread>

#include <semu/fast_fp.hpp>
#include <semu/fp.hpp>
#include <semu/l1tex_model.hpp>

namespace semu {
namespace {

using semu::fp::Rnd;

// Field lookup helper: find a raw field value by name.
std::optional<std::uint64_t> field_value(const DecodedInstruction& inst,
                                         const char* name) {
    for (const auto& [n, v] : inst.raw_fields) {
        if (n == name) return v;
    }
    return std::nullopt;
}

// RZ (255) reads as 0.
constexpr int kRegRz = 255;

// SpecialRegister hardware encoding values (verified empirically:
// SR_LANEID=0, SR_TID.X=33, SR_CTAID.X=37 in real sm120 cubins; the rest
// follow the CUDA S2R register convention).
constexpr std::uint64_t kSrLaneid = 0;
constexpr std::uint64_t kSrClock = 1;
constexpr std::uint64_t kSrTidX = 33, kSrTidY = 34, kSrTidZ = 35;
constexpr std::uint64_t kSrCtaidX = 37, kSrCtaidY = 38, kSrCtaidZ = 39;
constexpr std::uint64_t kSrNtid = 40;
constexpr std::uint64_t kSrWarpId = 41, kSrWarpSize = 42;
constexpr std::uint64_t kSrNctaidX = 43, kSrNctaidY = 44, kSrNctaidZ = 45;
constexpr std::uint64_t kSrSmId = 46, kSrSmemBase = 47;

// Named barrier opcodes (from sm120.json BAR variants).
constexpr std::uint16_t kOpBarSync = 0xb1d;

// Phase 6 Step 2D: replay a buffered race-event log into a RaceDetector in a
// deterministic order (sorted by (cta_id, ordinal)), independent of host
// scheduling and worker count.  Sorting groups every CTA's events together in
// the order that CTA's interpreter appended them, so the per-CTA program
// order, barrier releases and happens-before chain are preserved.  The log is
// cleared after replay.  No-op when the detector is disabled or the log empty.
void replay_race_log(RaceDetector* d, std::vector<RaceEvent>& log) {
    if (!d || !d->enabled() || log.empty()) return;
    std::sort(log.begin(), log.end(),
              [](const RaceEvent& a, const RaceEvent& b) {
                  if (a.cta != b.cta) return a.cta < b.cta;
                  return a.ordinal < b.ordinal;
              });
    for (const auto& ev : log) {
        if (ev.kind == RaceEvent::kObserve) {
            d->observe(ev.access);
        } else if (ev.kind == RaceEvent::kAtomic) {
            d->atomic_rmw(ev.access);
        } else if (ev.kind == RaceEvent::kCtaBarrier) {
            d->cta_barrier(ev.cta, ev.sm, ev.warps);
        } else if (ev.kind == RaceEvent::kFence) {
            d->fence(ev.cta, ev.sm, ev.warp, ev.scope);
        }
    }
    log.clear();
}
// True when a 32-bit FP pattern is NaN/Inf/subnormal (drives the fast-mode
// exceptional fallback classification).
bool exceptional_f32(std::uint32_t bits) {
    const float f = std::bit_cast<float>(bits);
    return std::isnan(f) || std::isinf(f) ||
           std::fpclassify(f) == FP_SUBNORMAL;
}
// True when a 64-bit FP pattern is NaN/Inf/subnormal.
bool exceptional_f64(std::uint64_t bits) {
    const double d = std::bit_cast<double>(bits);
    return std::isnan(d) || std::isinf(d) ||
           std::fpclassify(d) == FP_SUBNORMAL;
}

// Normalize a merged memory-event stream's ids: the L1 issue events use a
// per-interpreter counter and the L2 engine keeps its own event counter, so
// the two ranges collide (both start at 0).  Renumber every event globally
// (deterministic order preserved) and remap parent references.  Applies to
// BOTH the single-worker and merged parallel streams so event ids are always
// globally unique.
void normalize_memory_event_ids(std::vector<MemoryEvent>& events) {
    std::map<std::uint64_t, std::uint64_t> remap;
    std::uint64_t next_id = 0;
    for (auto& ev : events) {
        auto pit = remap.find(ev.parent_event_id);
        if (pit != remap.end()) ev.parent_event_id = pit->second;
        const std::uint64_t old = ev.event_id;
        ev.event_id = ++next_id;
        remap[old] = ev.event_id;
    }
}

// Classify an F2F result pattern according to its DESTINATION format
// (fp.hpp constants: F16=0, F32=1, F64=2, BF16=3).  The raw 16-bit F16/BF16
// results must NOT be reinterpreted as f32 — a finite half like 0x3c00 would
// look like a subnormal f32 and wrongly trigger an exceptional fallback.
bool exceptional_f2f_result(int dstfmt, std::uint32_t fout,
                            std::uint32_t fouthi) {
    if (dstfmt == 2) {  // F64 (register pair).
        return exceptional_f64((static_cast<std::uint64_t>(fouthi) << 32) |
                               fout);
    }
    if (dstfmt == 0 || dstfmt == 3) {  // F16 / BF16 in the low 16 bits.
        const std::uint16_t h = static_cast<std::uint16_t>(fout & 0xffffu);
        // exp field all-ones -> NaN/Inf; exp zero + nonzero frac -> subnormal.
        if (dstfmt == 0) {
            const unsigned exp = (h >> 10) & 0x1F;
            if (exp == 0x1F) return true;                      // NaN / Inf
            return exp == 0 && (h & 0x3FF) != 0;               // subnormal
        }
        const unsigned exp = (h >> 7) & 0xFF;
        if (exp == 0xFF) return true;                          // NaN / Inf
        return exp == 0 && (h & 0x7F) != 0;                    // subnormal
    }
    return exceptional_f32(fout);                              // F32
}

// Classify an F2F SOURCE pattern according to its SOURCE format.  A BF16
// source lives in the low 16 bits of the register; the raw 32-bit register
// value must not be read as an f32 (0x0000bf80 is a finite BF16 -1.0, not an
// f32 subnormal).
bool exceptional_f2f_source(int srcfmt, std::uint32_t src,
                            std::uint32_t src_hi) {
    if (srcfmt == 2) {  // F64 source (register pair).
        return exceptional_f64((static_cast<std::uint64_t>(src_hi) << 32) |
                               src);
    }
    if (srcfmt == 0 || srcfmt == 3) {  // F16 / BF16 in the low 16 bits.
        const std::uint16_t h = static_cast<std::uint16_t>(src & 0xffffu);
        if (srcfmt == 0) {
            const unsigned exp = (h >> 10) & 0x1F;
            if (exp == 0x1F) return true;                      // NaN / Inf
            return exp == 0 && (h & 0x3FF) != 0;               // subnormal
        }
        const unsigned exp = (h >> 7) & 0xFF;
        if (exp == 0xFF) return true;                          // NaN / Inf
        return exp == 0 && (h & 0x7F) != 0;                    // subnormal
    }
    return exceptional_f32(src);                               // F32
}

// Run-scope fenv guard (Phase 5.5 fast mode): the fast path relies on host
// round-to-nearest for all arithmetic; pin it once for the whole run / step
// sequence and restore the caller's mode afterwards (never per-instruction).
//
// The guard is MOVE-ONLY and is constructed directly via arm() on the final
// owning object (e.g. inside an std::optional) so no copy exists whose
// destructor could restore the caller's rounding mode before execution — that
// would leave the fast kernel running under the caller's mode (e.g. FE_UPWARD)
// instead of the pinned RN.
struct FenvGuard {
    int saved = FE_TONEAREST;
    bool armed = false;  // owns the "RN is set" obligation
    FenvGuard() = default;
    FenvGuard(const FenvGuard&) = delete;
    FenvGuard& operator=(const FenvGuard&) = delete;
    FenvGuard(FenvGuard&& o) noexcept
        : saved(o.saved), armed(o.armed) {
        o.armed = false;  // moved-from no longer restores
    }
    FenvGuard& operator=(FenvGuard&& o) noexcept {
        if (this != &o) {
            saved = o.saved;
            armed = o.armed;
            o.armed = false;
        }
        return *this;
    }
    // Save the caller's mode and pin RN.  Returns false (and leaves the mode
    // untouched) on any failure.
    bool arm() {
        saved = std::fegetround();
        if (saved == -1) return false;
        if (std::fesetround(FE_TONEAREST) != 0) return false;
        armed = true;
        return true;
    }
    ~FenvGuard() {
        if (armed) {
            if (std::fesetround(saved) != 0) {
                // Cannot report from a destructor; make it observable in
                // debug/test output so a lost restore is never silent.
                std::fprintf(stderr,
                             "semu: fast-mode fenv restore to mode %d "
                             "failed\n", saved);
            }
        }
    }
};

}  // namespace

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

Interpreter::Interpreter(const Kernel& kernel, const LaunchEnv& env,
                         std::uint64_t limit, const RunOptions& options)
    : Interpreter(kernel, env, limit, options, nullptr, 0, 1, nullptr) {}

// Worker-subset constructor: builds CTAs where cta_id % worker_count ==
// worker_id.  When `shared_memory` is null the instance owns a fresh
// MemoryService; otherwise it shares the caller's (parallel workers see one
// global buffer).  When `shared_detector` is null the instance owns a fresh
// RaceDetector; otherwise it shares the caller's (parallel workers submit
// their race-event logs to one detector merged in deterministic order).
// When `shared_l2` is null the instance owns a fresh L2EventEngine;
// otherwise it shares the caller's (parallel workers get globally unique
// L2 request/completion/event ids).
Interpreter::Interpreter(const Kernel& kernel, const LaunchEnv& env,
                         std::uint64_t limit, const RunOptions& options,
                         MemoryService* shared_memory, int worker_id,
                         int worker_count, RaceDetector* shared_detector,
                         L2EventEngine* shared_l2)
    : kernel_(kernel), env_(env), limit_(limit), options_(options) {
    // Phase 6: set up the memory service (shared or owned).
    std::vector<std::uint8_t> params;
    if (options_.memory.params) {
        params = *options_.memory.params;
    } else {
        params.resize(kernel.meta.cbank_param_size, 0);
    }
    if (shared_memory) {
        // Share the caller's service with a no-op deleter.
        memory_ = std::shared_ptr<MemoryService>(shared_memory,
                                                 [](MemoryService*) {});
    } else {
        memory_ = std::make_shared<MemoryService>(params);
        if (options_.memory.global && !options_.memory.global->empty()) {
            auto g = memory_->setup_global(options_.memory.global->size(),
                                           kernel.symbol_name);
            if (g.ok()) {
                memory_->set_global_backing(options_.memory.global);
            }
        }
    }
    // Phase 6 Step 2C: trace-only L2 engine (per run; simulated_sm_count from
    // model options).  Parallel workers share ONE engine so request/
    // completion/event ids are globally unique (High-3); a single worker
    // owns a fresh engine.
    if (shared_l2) {
        l2_engine_ = std::shared_ptr<L2EventEngine>(
            shared_l2, [](L2EventEngine*) {});
        l2_engine_shared_ = true;
    } else {
        l2_engine_ = std::make_shared<L2EventEngine>(
            options_.model.simulated_sm_count > 0
                ? options_.model.simulated_sm_count
                : 1,
            options_.model.deterministic_seed);
    }
    l2_engine_enabled_ = options_.model.l2 == L2Mode::kFunctionalEvents;
    // Phase 9 subset: build the cluster topology when the launch declares
    // cluster dimensions (DSMEM / cross-CTA shared + mbarrier RED arrive).
    if (env_.cluster[0] > 1 || env_.cluster[1] > 1 || env_.cluster[2] > 1) {
        auto topo = ClusterTopology::build(env_.cluster, env_.grid[0],
                                           env_.grid[1], env_.grid[2]);
        if (topo.ok()) cluster_topology_ = topo.value();
    }
    // Phase 6 Step 2D: trace-only race detector (enabled only in kReport).
    // Parallel workers share one detector so cross-CTA/global accesses are
    // observed together; each worker only buffers events (race_log_) and the
    // run result replays them in deterministic order after all workers join.
    if (shared_detector) {
        // Shared across parallel workers: enable/disable is decided ONCE by
        // run_result_parallel before the threads are spawned (calling
        // set_enabled here from each worker thread would be a host data race).
        race_detector_ = std::shared_ptr<RaceDetector>(
            shared_detector, [](RaceDetector*) {});
    } else {
        race_detector_ = std::make_shared<RaceDetector>();
        race_detector_->set_enabled(options_.model.race == RaceMode::kReport);
    }
    // Phase 6 Step 2: build this instance's CTAs from the grid dimensions.
    // Worker 0 (or a single worker) owns every CTA; worker w > 0 owns CTAs
    // with cta_id % worker_count == w, so each CTA stays on one worker.
    const std::uint64_t nthreads = static_cast<std::uint64_t>(env_.block[0]) *
                                   env_.block[1] * env_.block[2];
    const int nwarps = static_cast<int>((nthreads + kLanesPerWarp - 1) /
                                        kLanesPerWarp);
    const std::uint64_t nctas = static_cast<std::uint64_t>(env_.grid[0]) *
                                env_.grid[1] * env_.grid[2];
    for (std::uint64_t cta_id = 0; cta_id < nctas; ++cta_id) {
        if (cta_id % static_cast<std::uint64_t>(worker_count) !=
            static_cast<std::uint64_t>(worker_id)) {
            continue;
        }
        CtaState cta;
        cta.cta_id = static_cast<int>(cta_id);
        const std::uint64_t sh_size =
            options_.memory.shared_size > 0
                ? options_.memory.shared_size
                : kernel.meta.static_shared;
        if (sh_size > 0) {
            auto sh = memory_->register_cta_shared(sh_size, cta_id);
            if (sh.ok()) {
                cta.shared.resize(sh_size, 0);
                cta.shared_base = sh.value();
            }
        }
        for (int w = 0; w < nwarps; ++w) {
            WarpState ws;
            ws.warp_id = w;
            ws.cta_id = static_cast<int>(cta_id);
            ws.local_cta_id = static_cast<int>(ctas_.size());
            const std::uint64_t local_size = options_.memory.local_size > 0
                ? options_.memory.local_size
                : 4096;
            ws.local.resize(local_size, 0);
            for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                const int tid = w * kLanesPerWarp + lane;
                if (tid < static_cast<int>(nthreads)) {
                    ws.threads[lane].pc = 0;
                    ws.threads[lane].active = true;
                    ws.active_lanes |= (1u << lane);
                } else {
                    ws.threads[lane].active = false;
                    ws.threads[lane].exited = true;
                }
            }
            cta.warps.push_back(std::move(ws));
        }
        ctas_.push_back(std::move(cta));
    }
}

// ---------------------------------------------------------------------------
// Phase 5.5 fast FP
// ---------------------------------------------------------------------------

Interpreter::Fp32Plan Interpreter::plan_fp32(int op, int rnd,
                                              bool flush) const {
    (void)op;
    Fp32Plan p;
    if (!fast_mode()) return p;
    const bool modifiers_ok = rnd == 0 && !flush;
    switch (options_.fast_fp_fallback) {
        case FastFpFallback::kNone:
            // Fastest: never fall back.  Non-RN/FTZ/FMZ run as RN and are
            // counted as ignored modifiers (per lane).
            p.use_fast = true;
            p.ignored_modifier = !modifiers_ok;
            break;
        case FastFpFallback::kStrictModifiers:
            // Fall back only for non-RN / FTZ / FMZ / exact-NaN needs.
            p.use_fast = modifiers_ok;
            break;
        case FastFpFallback::kExceptional:
        default:
            if (modifiers_ok) {
                p.use_fast = true;
                p.need_exceptional = true;  // classify inputs per lane
            } else {
                p.use_fast = false;
            }
            break;
    }
    return p;
}

Interpreter::Fp64Plan Interpreter::plan_fp64(int op, int rnd) const {
    (void)op;
    Fp64Plan p;
    if (!fast_mode()) return p;
    const bool modifiers_ok = rnd == 0;
    switch (options_.fast_fp_fallback) {
        case FastFpFallback::kNone:
            p.use_fast = true;
            p.ignored_modifier = !modifiers_ok;
            break;
        case FastFpFallback::kStrictModifiers:
            p.use_fast = modifiers_ok;
            break;
        case FastFpFallback::kExceptional:
        default:
            if (modifiers_ok) {
                p.use_fast = true;
                p.need_exceptional = true;
            } else {
                p.use_fast = false;
            }
            break;
    }
    return p;
}

// High-4: uniform FP-leaf accounting — implemented inline in interpreter.hpp
// (per-lane hot path).
// ---------------------------------------------------------------------------
// Public entry points
// ---------------------------------------------------------------------------

std::optional<Fault> Interpreter::run(const Kernel& kernel,
                                      const LaunchEnv& env,
                                      std::uint64_t limit,
                                      bool report_trace) {
    return run_result(kernel, env, limit, report_trace).fault;
}

std::optional<Fault> Interpreter::run(const Kernel& kernel,
                                      const LaunchEnv& env,
                                      const RunOptions& options) {
    return run_result(kernel, env, options).fault;
}

std::optional<Fault> Interpreter::run_shared(
    const Kernel& kernel, const LaunchEnv& env,
    std::vector<std::uint8_t>* shared_out, std::uint64_t limit) {
    Result r = run_result(kernel, env, limit, false);
    if (shared_out && !r.ctas.empty()) {
        *shared_out = r.ctas[0].shared;
    }
    return r.fault;
}

// Execute exactly one dynamic warp instruction (step mode); returns true
// if a step was taken.  Exposes internal state for the step-vs-continuous
// consistency test.  Delegate to the Phase 7 step_group primitive.
bool Interpreter::step_once(std::vector<CtaState>* state_out,
                            std::uint64_t* executed_out,
                            std::optional<Fault>* fault_out) {
    StepGroupFrame frame;
    if (!step_group(&frame, state_out, executed_out, nullptr, nullptr)) {
        return false;
    }
    if (frame.fault && fault_out) *fault_out = std::move(frame.fault);
    return true;
}

// Phase 7: one-step execution with an optional schedule filter and an
// optional pre-exec veto (see StepGroupFrame / PreExecFilter in the header).
bool Interpreter::step_group(StepGroupFrame* frame,
                             std::vector<CtaState>* state_out,
                             std::uint64_t* executed_out,
                             const ScheduleFilter* eligible,
                             const PreExecFilter* pre_exec) {
    if (frame) *frame = StepGroupFrame{};
    int cta = 0;
    int warp = 0;
    std::uint64_t pc = 0;
    std::uint32_t mask = 0;
    bool eligible_blocked = false;
    if (!next_group(&cta, &warp, &pc, &mask, eligible, &eligible_blocked)) {
        // No runnable group.  Two distinct cases (Blocker, Phase 7 re-review):
        //   - the launch is truly done / deadlocked (eligible_blocked false);
        //   - the launch still has runnable warps but the `eligible` focus
        //     filter excluded every one of them (eligible_blocked true).  The
        //     latter is NOT launch done: the caller must keep the session
        //     alive so clearing focus can continue.
        if (frame) frame->focus_blocked = eligible_blocked;
        return false;
    }
    if (frame) {
        frame->runnable = true;
        frame->cta = static_cast<std::uint32_t>(cta);
        frame->warp = static_cast<std::uint32_t>(warp);
        frame->pc = pc;
        frame->mask = mask;
    }
    if (executed_ >= limit_) {
        Fault f(FaultKind::kInstructionLimit,
                "dynamic instruction limit reached");
        f.set_warp(static_cast<std::uint32_t>(warp)).set_pc(pc);
        if (frame) {
            frame->limit_hit = true;
            frame->fault = std::move(f);
        }
        if (state_out) *state_out = ctas_;
        if (executed_out) *executed_out = executed_;
        return true;
    }
    // Pre-exec veto: decide BEFORE any state changes so a breakpoint /
    // unsupported-instruction stop leaves the group untouched.
    if (pre_exec) {
        const std::uint64_t idx = pc / 16;
        if (idx < kernel_.predecoded.size() &&
            kernel_.predecoded[idx].unique) {
            const DecodedInstruction& inst = kernel_.predecoded[idx].inst;
            if (!(*pre_exec)(static_cast<std::uint32_t>(cta),
                             static_cast<std::uint32_t>(warp), pc, mask,
                             inst)) {
                if (frame) frame->stopped = true;
                if (state_out) *state_out = ctas_;
                if (executed_out) *executed_out = executed_;
                return true;
            }
        }
    }
    // Execute the group with the debug-access capture enabled.
    std::optional<Fault> fault;
    std::uint32_t exec_mask = 0;
    debug_capture_ = true;
    debug_step_accesses_.clear();
    Status st = execute_group(cta, warp, pc, mask, &fault, &exec_mask);
    debug_capture_ = false;
    if (frame) frame->mask = exec_mask;
    if (st.failed()) {
        if (frame) {
            if (fault) {
                frame->fault = std::move(fault);
            } else {
                Fault f(FaultKind::kInternal, st.take_error().message());
                f.set_warp(static_cast<std::uint32_t>(warp)).set_pc(pc);
                frame->fault = std::move(f);
            }
        }
        if (state_out) *state_out = ctas_;
        if (executed_out) *executed_out = executed_;
        return true;
    }
    ++executed_;
    if (frame) {
        frame->executed = true;
        frame->accesses = std::move(debug_step_accesses_);
    }
    if (state_out) *state_out = ctas_;
    if (executed_out) *executed_out = executed_;
    return true;
}

// Step-by-step consistency (Phase 4 exit criterion): run the kernel one
// group at a time and verify the final CTA state matches a continuous run.
bool Interpreter::step_consistent(const Kernel& kernel, const LaunchEnv& env,
                                  std::uint64_t limit,
                                  std::vector<CtaState>* final_state) {
    RunOptions opts;
    opts.instruction_limit = limit;
    return step_consistent(kernel, env, opts, final_state);
}

bool Interpreter::step_consistent(const Kernel& kernel, const LaunchEnv& env,
                                  const RunOptions& options,
                                  std::vector<CtaState>* final_state) {
    // Continuous run.
    Result cont = run_result(kernel, env, options);
    if (cont.fault) return false;
    // Step run (same mode as the continuous run).  Pin RN for the whole step
    // sequence in fast mode so the stepped fast leaves see the same rounding
    // mode as the continuous baseline.
    std::optional<FenvGuard> guard;
    if (options.mode == ExecutionMode::kFast) {
        guard.emplace();
        if (!guard->arm()) return false;
    }
    RunOptions opts = options;
    Interpreter st(kernel, env, opts.instruction_limit, opts);
    std::vector<CtaState> stepped;
    while (st.step_once(&stepped, nullptr, nullptr)) {
    }
    if (!final_state) return false;
    if (stepped.size() != cont.ctas.size()) return false;
    // Compare GPRs + predicates + exited state of every thread.
    for (std::size_t c = 0; c < stepped.size(); ++c) {
        if (stepped[c].warps.size() != cont.ctas[c].warps.size()) return false;
        for (std::size_t w = 0; w < stepped[c].warps.size(); ++w) {
            const auto& a = stepped[c].warps[w];
            const auto& b = cont.ctas[c].warps[w];
            for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                if (a.threads[lane].exited != b.threads[lane].exited)
                    return false;
                for (int r = 0; r < kNumGprs; ++r) {
                    if (a.threads[lane].gpr[r] != b.threads[lane].gpr[r])
                        return false;
                }
            }
        }
    }
    *final_state = std::move(stepped);
    return true;
}

Interpreter::Result Interpreter::run_result(const Kernel& kernel,
                                            const LaunchEnv& env,
                                            std::uint64_t limit,
                                            bool report_trace) {
    RunOptions opts;
    opts.instruction_limit = limit;
    opts.report_trace = report_trace;
    return run_result(kernel, env, opts);
}

Interpreter::Result Interpreter::run_result(const Kernel& kernel,
                                            const LaunchEnv& env,
                                            const RunOptions& options) {
    // Run-scope fenv guard: the fast path relies on host round-to-nearest
    // for all its arithmetic; pin it once for the whole run and restore the
    // caller's mode afterwards (never per-instruction).  Only created in fast
    // mode; fegetround/fesetround failures are detected (they are required
    // for correctness of the fast path).  Constructed directly in the optional
    // (no copy) so the RN pin survives until the interpreter finishes.
    std::optional<FenvGuard> guard;
    if (options.mode == ExecutionMode::kFast) {
        guard.emplace();
        if (!guard->arm()) {
            // fenv control unavailable: refuse to run fast (result would not
            // be under the pinned RN the fast path depends on).
            guard.reset();
            Fault f(FaultKind::kInternal,
                    "fast mode requires host rounding-mode control "
                    "(fegetround/fesetround failed)");
            f.set_kernel(kernel.symbol_name);
            Result r;
            r.fault = std::move(f);
            r.execution_mode = options.mode;
            return r;
        }
    }
    if (options.worker_count <= 1) {
        // Deterministic single worker: one interpreter, all CTAs interleaved
        // by the round-robin scheduler on the calling thread.
        Interpreter it(kernel, env, options.instruction_limit, options);
        it.report_trace_ = options.report_trace;
        Result r = it.run_owned();
        // Phase 6 Step 2D: replay the buffered race-event log (sorted by
        // (cta_id, ordinal)) into the detector so the report order is the
        // same deterministic (cta, ordinal) order the parallel path uses.
        replay_race_log(it.race_detector_.get(), it.race_log_);
        r.race_reports = it.race_detector_ ? it.race_detector_->reports()
                                           : std::vector<RaceReport>{};
        // High-3: L1-issue and L2-engine event ids both start at 0; renumber
        // globally so the stream has unique ids (same as the parallel path).
        normalize_memory_event_ids(r.memory_events);
        return r;
    }
    return run_result_parallel(kernel, env, options);
}

// Phase 6 Step 2A: parallel worker pool.  Each worker owns a fixed subset of
// CTAs (cta_id % worker_count == worker_id) and runs them on its own thread;
// all workers share one MemoryService so they observe a single global buffer.
// Race-free workloads must produce byte-identical results for any worker
// count.  Fault selection is deterministic: the worker with the smallest
// (cta_id, dynamic-instruction) fault wins.
Interpreter::Result Interpreter::run_result_parallel(
    const Kernel& kernel, const LaunchEnv& env, const RunOptions& options) {
    const int nworkers = options.worker_count;
    // Shared MemoryService: params + global backing set up once.
    auto memory = std::make_shared<MemoryService>(
        options.memory.params ? *options.memory.params
                              : std::vector<std::uint8_t>(
                                    kernel.meta.cbank_param_size, 0));
    if (options.memory.global && !options.memory.global->empty()) {
        auto g = memory->setup_global(options.memory.global->size(),
                                      kernel.symbol_name);
        if (g.ok()) memory->set_global_backing(options.memory.global);
    }
    // Shared RaceDetector: every worker buffers its race events into a
    // per-worker log (race_log_) instead of observing live; after all workers
    // join, run_result_parallel merges the logs and replays them into this one
    // detector sorted by (cta_id, ordinal).  This is thread-safe (replay is
    // single-threaded after join) and deterministic: cross-CTA/global races
    // are always observed together and the report JSON is byte-for-byte
    // identical for any worker count.
    auto shared_detector = std::make_shared<RaceDetector>();
    shared_detector->set_enabled(options.model.race == RaceMode::kReport);

    // High-3: ONE launch-level L2 event engine shared by every worker, so
    // request/completion/event ids are globally unique (per-worker engines
    // collided).  It is mutex-guarded for the parallel issue path.
    auto shared_l2 = std::make_shared<L2EventEngine>(
        options.model.simulated_sm_count > 0 ? options.model.simulated_sm_count
                                             : 1,
        options.model.deterministic_seed);

    struct WorkerResult {
        Interpreter::Result r;
        int worker_id = 0;
    };
    std::vector<WorkerResult> results(nworkers);
    std::vector<std::vector<RaceEvent>> worker_logs(nworkers);
    std::vector<std::vector<L2RequestDescriptor>> worker_l2_logs(nworkers);
    std::vector<std::thread> threads;
    threads.reserve(nworkers);
    for (int w = 0; w < nworkers; ++w) {
        threads.emplace_back([&, w]() {
            // Each worker runs its CTA subset; the memory service, race
            // detector and L2 engine are shared.
            // Fast mode pins RN on this worker thread for the whole subset run
            // (per-worker fenv guard — fenv is thread-local on the host).
            std::optional<FenvGuard> wguard;
            if (options.mode == ExecutionMode::kFast) {
                wguard.emplace();
                if (!wguard->arm()) {
                    // Medium: consistent with the single-worker path, a fast
                    // run that cannot pin RN must fail with a structured fault
                    // instead of silently running without the pinned mode.
                    wguard.reset();
                    Result r;
                    r.fault = Fault(FaultKind::kInternal,
                                    "fast mode requires host rounding-mode "
                                    "control (fegetround/fesetround failed)");
                    r.execution_mode = options.mode;
                    results[w] = {std::move(r), w};
                    return;
                }
            }
            Interpreter it(kernel, env, options.instruction_limit, options,
                           memory.get(), w, nworkers, shared_detector.get(),
                           shared_l2.get());
            it.report_trace_ = options.report_trace;
            results[w] = {it.run_owned(), w};
            worker_logs[w] = std::move(it.race_log_);
            worker_l2_logs[w] = std::move(it.l2_log_);
        });
    }
    for (auto& th : threads) th.join();

    // Deterministic race-event merge: concatenate all workers' logs and replay
    // them sorted by (cta_id, ordinal) into the single shared detector.  Each
    // CTA lives on exactly one worker, so (cta_id, ordinal) is unique and the
    // merged order equals the single-worker (deterministic) replay order.
    std::vector<RaceEvent> merged_log;
    for (auto& l : worker_logs) {
        merged_log.insert(merged_log.end(), l.begin(), l.end());
    }
    replay_race_log(shared_detector.get(), merged_log);
    std::vector<RaceReport> race_reports = shared_detector->reports();
    // Merge: collect every CTA, ordered by cta_id.  If any worker faulted,
    // select the deterministic minimum (cta_id, dynamic instruction count).
    Result merged;
    bool have_fault = false;
    Result* winning = nullptr;
    for (auto& wr : results) {
        if (wr.r.fault) {
            if (!have_fault) {
                have_fault = true;
                winning = &wr.r;
            } else if (wr.r.fault->cta().value_or(0) <
                           winning->fault->cta().value_or(0) ||
                       (wr.r.fault->cta().value_or(0) ==
                            winning->fault->cta().value_or(0) &&
                        wr.r.dynamic_instructions <
                            winning->dynamic_instructions)) {
                winning = &wr.r;
            }
        }
    }
    if (have_fault) {
        merged.fault = std::move(winning->fault);
        merged.dynamic_instructions = winning->dynamic_instructions;
        merged.ctas = std::move(winning->ctas);
        merged.trace = std::move(winning->trace);
        merged.memory_events = std::move(winning->memory_events);
        merged.race_reports = std::move(race_reports);
        merged.execution_mode = options.mode;
        merged.fast_stats = winning->fast_stats;
        merged.approximate = options.mode == ExecutionMode::kFast &&
                             winning->fast_stats.any_fast_fp;
        return merged;
    }
    merged.dynamic_instructions = 0;
    for (auto& wr : results) {
        merged.dynamic_instructions += wr.r.dynamic_instructions;
        for (auto& cta : wr.r.ctas) merged.ctas.push_back(std::move(cta));
        for (auto& ev : wr.r.memory_events) {
            merged.memory_events.push_back(std::move(ev));
        }
    }
    merged.race_reports = std::move(race_reports);
    std::sort(merged.ctas.begin(), merged.ctas.end(),
              [](const CtaState& a, const CtaState& b) {
                  return a.cta_id < b.cta_id;
              });
    // High-2: the L2 trace must be byte-for-byte deterministic and independent
    // of host thread scheduling.  Workers only BUFFERED request descriptors
    // (never touched the shared engine during execution — mutex acquisition
    // order is not deterministic).  Merge every worker's descriptors, sort by
    // (cta, per-CTA ordinal, lane) — the same deterministic order a single
    // worker produces — and drive the launch-level engine SINGLE-THREADED so
    // request/completion/event ids and the seed schedule are stable.  Then
    // drain once and append the L2 events.
    if (options.model.l2 == L2Mode::kFunctionalEvents) {
        std::vector<L2RequestDescriptor> l2_log;
        for (auto& l : worker_l2_logs) {
            l2_log.insert(l2_log.end(), l.begin(), l.end());
        }
        std::stable_sort(l2_log.begin(), l2_log.end(),
                         [](const L2RequestDescriptor& a,
                            const L2RequestDescriptor& b) {
                             if (a.cta != b.cta) return a.cta < b.cta;
                             if (a.ordinal != b.ordinal)
                                 return a.ordinal < b.ordinal;
                             return a.lane < b.lane;
                         });
        for (const auto& d : l2_log) {
            shared_l2->issue_global(d.sm, d.subcore, d.cta, d.warp, d.pc,
                                    d.ordinal, 0, d.mnemonic, d.request_kind,
                                    d.addr, d.len);
        }
        shared_l2->drain_completions();
        std::vector<MemoryEvent> l2_events = shared_l2->events();
        shared_l2->events().clear();
        for (auto& ev : l2_events) {
            merged.memory_events.push_back(std::move(ev));
        }
    }
    // High-3: the L1 issue event ids are worker-local (each worker's
    // l1tex_state_ starts at 0), so after the merge they collide across
    // workers (and with the L2 engine's own counter).  Renumber every event
    // globally (deterministic for a fixed worker count) and remap parent
    // references so the merged L1/L2 streams carry globally stable, unique
    // ids — identical to the single-worker normalization.
    normalize_memory_event_ids(merged.memory_events);
    merged.execution_mode = options.mode;
    for (auto& wr : results) {
        merged.fast_stats.fast_fp_ops += wr.r.fast_stats.fast_fp_ops;
        merged.fast_stats.precise_fallback_ops +=
            wr.r.fast_stats.precise_fallback_ops;
        merged.fast_stats.ignored_modifier_ops +=
            wr.r.fast_stats.ignored_modifier_ops;
        merged.fast_stats.any_fast_fp =
            merged.fast_stats.any_fast_fp || wr.r.fast_stats.any_fast_fp;
    }
    merged.approximate = options.mode == ExecutionMode::kFast &&
                         merged.fast_stats.any_fast_fp;
    return merged;
}

// Run the CTAs owned by this interpreter instance (either the full grid for a
// single worker, or a worker's subset in parallel mode).  Returns the result
// with this instance's CTAs; parallel mode merges per-worker results.
Interpreter::Result Interpreter::run_owned() {
    int cta = 0;
    int warp = 0;
    std::uint64_t pc = 0;
    std::uint32_t mask = 0;
    while (next_group(&cta, &warp, &pc, &mask)) {

        // Dynamic instruction limit.
        if (executed_ >= limit_) {
            Fault f(FaultKind::kInstructionLimit,
                    "dynamic instruction limit " + std::to_string(limit_) +
                        " reached");
            f.set_kernel(kernel_.symbol_name).set_pc(pc).set_warp(
                static_cast<std::uint32_t>(warp));
            Result r;
            r.fault = std::move(f);
            r.limit_reached = true;
            r.dynamic_instructions = executed_;
            r.ctas = std::move(ctas_);
            flush_l2_events();
    r.memory_events = std::move(memory_events_);
            r.trace = std::move(trace_);
            r.execution_mode = options_.mode;
            r.fast_stats = fast_stats_;
            r.approximate = options_.mode == ExecutionMode::kFast &&
                            fast_stats_.any_fast_fp;
            return r;
        }
        std::optional<Fault> fault;
        Status st = execute_group(cta, warp, pc, mask, &fault);
        if (st.failed()) {
            // Fault with locality: kernel / PC / warp / active lanes.
            Result r;
            Fault f = fault ? std::move(*fault)
                            : Fault(FaultKind::kInternal,
                                    st.take_error().message(),
                                    st.take_error());
            if (!f.kernel()) f.set_kernel(kernel_.symbol_name);
            if (!f.pc()) f.set_pc(pc);
            if (!f.warp()) f.set_warp(static_cast<std::uint32_t>(warp));
            if (!f.active_mask()) f.set_active_mask(mask);
            r.fault = std::move(f);
            r.dynamic_instructions = executed_;
            r.ctas = std::move(ctas_);
            flush_l2_events();
    r.memory_events = std::move(memory_events_);
            r.trace = std::move(trace_);
            r.execution_mode = options_.mode;
            r.fast_stats = fast_stats_;
            r.approximate = options_.mode == ExecutionMode::kFast &&
                            fast_stats_.any_fast_fp;
            return r;
        }
        ++executed_;
        if (report_trace_) {
            char line[192];
            std::snprintf(line, sizeof(line),
                          "w%d pc=0x%llx mask=0x%08x %s",
                          warp, static_cast<unsigned long long>(pc), mask,
                          /* the decoded mnemonic */ "");
            // Append mnemonic from a fresh decode.
            auto dr = Decoder::instance().decode(
                kernel_.predecoded[pc / 16].lo, kernel_.predecoded[pc / 16].hi);
            if (dr.is_unique()) {
                std::snprintf(line, sizeof(line),
                              "w%d pc=0x%llx mask=0x%08x %s",
                              warp, static_cast<unsigned long long>(pc),
                              mask, dr.instruction().disasm.c_str());
            }
            trace_.push_back(line);
        }
    }

    // Terminal-state classification (Phase 7 re-review round 2, Blocker-2):
    // a stuck launch is a FAULT, never a clean completion.  The barrier
    // deadlock scan used to live only on this path; the debugger reuses the
    // same classification via terminal_state()/barrier_deadlock_fault().
    switch (terminal_state()) {
        case ExecutionTerminalState::kBarrierDeadlock: {
            Result r;
            r.fault = barrier_deadlock_fault();
            r.dynamic_instructions = executed_;
            r.ctas = std::move(ctas_);
            flush_l2_events();
            r.memory_events = std::move(memory_events_);
            r.trace = std::move(trace_);
            r.execution_mode = options_.mode;
            r.fast_stats = fast_stats_;
            r.approximate = options_.mode == ExecutionMode::kFast &&
                            fast_stats_.any_fast_fp;
            return r;
        }
        case ExecutionTerminalState::kNoProgress: {
            Fault f(FaultKind::kNoProgress,
                    "launch has no runnable group and no barrier waiter "
                    "(stalled); not a clean completion");
            f.set_kernel(kernel_.symbol_name);
            Result r;
            r.fault = std::move(f);
            r.dynamic_instructions = executed_;
            r.ctas = std::move(ctas_);
            flush_l2_events();
            r.memory_events = std::move(memory_events_);
            r.trace = std::move(trace_);
            r.execution_mode = options_.mode;
            r.fast_stats = fast_stats_;
            r.approximate = options_.mode == ExecutionMode::kFast &&
                            fast_stats_.any_fast_fp;
            return r;
        }
        default:
            break;  // kDone: clean completion below.
    }
    Result r;
    r.dynamic_instructions = executed_;
    r.ctas = std::move(ctas_);
    flush_l2_events();
    r.memory_events = std::move(memory_events_);
    r.trace = std::move(trace_);
    r.execution_mode = options_.mode;
    r.fast_stats = fast_stats_;
    r.approximate = options_.mode == ExecutionMode::kFast &&
                    fast_stats_.any_fast_fp;
    return r;
}

// ---------------------------------------------------------------------------
// Scheduler: pick the next (warp, pc, lane-group).
// ---------------------------------------------------------------------------

// One scheduler scan over every (cta, warp, pc-group).  Shared by next_group
// (which picks a group) and terminal_state (which classifies why none was
// pickable).  See ScheduleScan in the header.
Interpreter::ScheduleScan Interpreter::scan_schedule(
    const ScheduleFilter* eligible) {
    ScheduleScan scan;
    for (std::size_t ci = 0; ci < ctas_.size(); ++ci) {
        auto& cta = ctas_[ci];
        for (std::size_t wi = 0; wi < cta.warps.size(); ++wi) {
            auto& ws = cta.warps[wi];
            if (ws.done) continue;
            // Phase 7: schedule filter (warp step) — skip ineligible warps.
            // Whether a warp passes the filter must not change the launch-
            // done determination below, so the runnable test is done
            // unconditionally.
            const bool passes_filter =
                !eligible ||
                (*eligible)(static_cast<std::uint32_t>(cta.cta_id),
                            static_cast<std::uint32_t>(ws.warp_id));
            // Build the set of active lanes at each distinct PC.
            std::map<std::uint64_t, std::uint32_t> by_pc;
            bool any_live = false;
            for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                if (ws.threads[lane].active && !ws.threads[lane].exited) {
                    any_live = true;
                    by_pc[ws.threads[lane].pc] |= (1u << lane);
                }
            }
            if (!any_live) {
                // A warp with live lanes is never done; sync-wait lanes are
                // active=false but not exited, so any_live stays true for
                // them via the !exited test above.  A warp whose lanes are
                // all either exited or suspended at a named barrier or a
                // sync-wait waits for the release; only truly all-exited
                // warps become done.
                if (ws.waiting_barrier < 0) {
                    bool any_sync_wait = false;
                    for (const auto& e : ws.sync_stack) {
                        if (e.pending_lanes != 0 || e.arrived_lanes != 0) {
                            any_sync_wait = true;
                            break;
                        }
                    }
                    if (!any_sync_wait) {
                        bool all_exited = true;
                        for (int l = 0; l < kLanesPerWarp; ++l) {
                            if (!ws.threads[l].exited) {
                                all_exited = false;
                                break;
                            }
                        }
                        if (all_exited) ws.done = true;
                    } else {
                        // A warp stuck in a sync-wait with no live lanes
                        // (its participants exited or never arrive) is a
                        // no-progress launch, never a clean completion.
                        scan.any_stalled = true;
                    }
                } else {
                    scan.any_barrier_wait = true;
                }
                continue;
            }
            // This warp has live runnable lanes: the launch is NOT done (the
            // flag is set before the filter so a filtered-out focus warp still
            // proves there is runnable work elsewhere).
            scan.any_runnable = true;
            if (!passes_filter) continue;
            for (const auto& [pc, mask] : by_pc) {
                scan.groups.push_back(ScheduleScan::Group{ci, wi, pc, mask});
            }
        }
    }
    return scan;
}

bool Interpreter::next_group(int* cta_out, int* warp_out,
                             std::uint64_t* pc_out,
                             std::uint32_t* mask_out,
                             const ScheduleFilter* eligible,
                             bool* eligible_blocked) {
    // High-1: true round-robin.  Flatten every runnable (cta, warp,
    // pc-group) into a list, start at the cursor, and pick the first
    // runnable group.  After selection the cursor advances past it, so no
    // warp or pc-group can starve another.
    const ScheduleScan scan = scan_schedule(eligible);
    if (scan.groups.empty()) {
        // No group passed the filter.  Distinguish "focus excluded a live
        // launch" (Blocker, Phase 7 re-review) from "launch truly done":
        // `any_runnable` is true exactly when some runnable group exists that
        // the filter vetoed, i.e. clearing the filter would make progress.
        if (eligible_blocked) *eligible_blocked = scan.any_runnable;
        return false;
    }
    // Round-robin: start at rr_ % groups.size().
    const std::uint64_t start = rr_ % scan.groups.size();
    const ScheduleScan::Group& g = scan.groups[start];
    rr_ = (start + 1) % scan.groups.size();
    *cta_out = static_cast<int>(g.cta);
    *warp_out = static_cast<int>(g.warp);
    *pc_out = g.pc;
    *mask_out = g.mask;
    return true;
}

// Phase 7 re-review (round 2, Blocker-2): classify why no group is runnable.
ExecutionTerminalState Interpreter::terminal_state(
    const ScheduleFilter* eligible) {
    const ScheduleScan scan = scan_schedule(eligible);
    if (!scan.groups.empty())
        return ExecutionTerminalState::kRunning;
    if (scan.any_runnable)
        return ExecutionTerminalState::kFocusBlocked;
    if (scan.any_barrier_wait)
        return ExecutionTerminalState::kBarrierDeadlock;
    if (scan.any_stalled)
        return ExecutionTerminalState::kNoProgress;
    return ExecutionTerminalState::kDone;
}

// The descriptive barrier-deadlock fault (first stuck CTA/barrier), shared by
// the normal runner and the debugger so both report the identical message.
std::optional<Fault> Interpreter::barrier_deadlock_fault() const {
    for (const auto& cta : ctas_) {
        // Collect waiting warps per barrier id within this CTA.
        std::map<int, std::vector<int>> waiting_by_bar;
        for (const auto& ws : cta.warps) {
            if (ws.waiting_barrier >= 0)
                waiting_by_bar[ws.waiting_barrier].push_back(ws.warp_id);
        }
        if (waiting_by_bar.empty()) continue;
        const int nwarps = static_cast<int>(cta.warps.size());
        for (const auto& [bid, warps] : waiting_by_bar) {
            // Participants expected = all warps that did NOT exit early.
            std::vector<int> exited_warps;
            for (int w = 0; w < nwarps; ++w) {
                bool any_live = false;
                for (const auto& t : cta.warps[w].threads) {
                    if (!t.exited) { any_live = true; break; }
                }
                if (!any_live) exited_warps.push_back(w);
            }
            std::string msg =
                "barrier deadlock in CTA " + std::to_string(cta.cta_id) +
                " at barrier " + std::to_string(bid) + ": " +
                std::to_string(warps.size()) + "/" +
                std::to_string(nwarps) + " warps arrived/waiting (ids: ";
            for (std::size_t i = 0; i < warps.size(); ++i) {
                if (i) msg += ",";
                msg += std::to_string(warps[i]);
            }
            msg += "); exited without arriving: ";
            for (std::size_t i = 0; i < exited_warps.size(); ++i) {
                if (i) msg += ",";
                msg += std::to_string(exited_warps[i]);
            }
            msg += "; expected participants " + std::to_string(nwarps);
            Fault f(FaultKind::kBarrierDeadlock, msg);
            f.set_kernel(kernel_.symbol_name)
                .set_warp(static_cast<std::uint32_t>(warps[0]));
            return f;
        }
    }
    return std::nullopt;
}

Status Interpreter::execute_group(int cta_idx, int warp, std::uint64_t pc,
                                  std::uint32_t mask,
                                  std::optional<Fault>* fault,
                                  std::uint32_t* exec_mask_out) {
    const std::uint64_t idx = pc / 16;
    if (idx >= kernel_.predecoded.size()) {

        Fault f(FaultKind::kInvalidInstruction,
                "pc 0x" + std::to_string(pc) + " outside kernel text");
        f.set_warp(static_cast<std::uint32_t>(warp)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    const PredecodedWord& w = kernel_.predecoded[idx];
    if (!w.unique) {
        Fault f(FaultKind::kInvalidInstruction,
                "word at pc 0x" + std::to_string(pc) + ": " + w.reason);
        f.set_warp(static_cast<std::uint32_t>(warp)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    const DecodedInstruction& inst = w.inst;

    // Advance every active lane's PC past this instruction first; branch
    // handlers overwrite per-lane PCs as needed.
    CtaState& cta = ctas_[static_cast<std::size_t>(cta_idx)];
    for (auto& ws : cta.warps) {
        if (ws.warp_id != warp) continue;
            for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                if (ws.threads[lane].active &&
                    ws.threads[lane].pc == pc) {
                    ws.threads[lane].pc = pc + 16;
                }
            }
            // High-2: per-lane guard filtering.  Every lane at this PC
            // already advanced past the instruction; only lanes whose guard
            // predicate is true actually execute it.
            std::uint32_t exec_mask = mask;
            if (inst.guard_pred != 7) {
                exec_mask = 0;
                for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                    if (!(mask & (1u << lane))) continue;
                    const bool pv = ws.threads[lane].pred[inst.guard_pred];
                    const bool take = inst.guard_not ? !pv : pv;
                    if (take) exec_mask |= (1u << lane);
                }
                if (exec_mask == 0) {
                    if (exec_mask_out) *exec_mask_out = 0;
                    return Status::success();  // all lanes skipped
                }
            }
            if (exec_mask_out) *exec_mask_out = exec_mask;
            const std::uint16_t op = semu::opcode_of(inst.word.lo, inst.word.hi);
            switch (op) {
                case 0x947: return do_bra(ws, exec_mask, inst, pc, fault);   // BRA
                case 0x949: return do_bra(ws, exec_mask, inst, pc, fault); // BRX
                case 0x94a: return do_bra(ws, exec_mask, inst, pc, fault); // JMP
                case 0x94c: return do_bra(ws, exec_mask, inst, pc, fault); // JMX
                case 0x945: return do_bssy(ws, inst, pc, exec_mask, fault); // BSSY
                case 0x941: return do_bsync(ws, inst, pc, exec_mask, fault); // BSYNC
                case 0x94d: return do_exit(ws, inst, mask, pc);         // EXIT
                case 0x919: return do_s2r(ws, inst, exec_mask, pc, fault); // S2R
                case 0x9c3: return do_s2ur(ws, inst, pc, fault);        // S2UR
                case kOpBarSync: return do_bar(ws, inst, exec_mask, pc, fault); // BAR.SYNC
                case 0x918: return Status::success();                    // NOP
                default:
                    if (op == 0x202 || op == 0x402 || op == 0x802 ||
                        op == 0x1c02) {  // MOV / MOV64 / MOV imm / MOV UR
                        return do_mov(ws, exec_mask, inst, pc);
                    }
                    // Phase 9 subset: uniform-register ALU (needed to build
                    // mbarrier init words / TMA coordinate blocks).
                    if (op == 0x882 || op == 0x1c82 || op == 0x1482) {  // UMOV
                        return do_umov(ws, inst, pc);
                    }
                    if (op == 0x1890 || op == 0x1290) {  // UIADD3
                        return do_uiadd3(ws, inst, pc);
                    }
                    if (op == 0x1899 || op == 0x1499 || op == 0x1299) {  // USHF
                        return do_ushf(ws, inst, pc);
                    }
                    if (op == 0x810 || op == 0x210 || op == 0x1c10) {  // IADD3
                        return do_iadd3(ws, exec_mask, inst, pc);
                    }
                    if (op == 0x20c || op == 0x80c || op == 0x1c0c) {  // ISETP
                        return do_isetp(ws, exec_mask, inst, pc);
                    }
                    if (op == 0x224 || op == 0x824 || op == 0x424 ||
                        op == 0x1c24 || op == 0x1e24 ||
                        op == 0x225 || op == 0x825 || op == 0x425 ||
                        op == 0x1c25 || op == 0x1e25 ||
                        op == 0x227 || op == 0x827 || op == 0x427 ||
                        op == 0x1c27 || op == 0x1e27) {  // IMAD/IMAD.WIDE/IMAD.HI
                        return do_imad(ws, exec_mask, inst, pc, fault);
                    }
                    // ---- Phase 6 memory / sync ----------------------------
                    if (op == 0x381 || op == 0x1981 || op == 0x197e) {  // LDG
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x386 || op == 0x1986 || op == 0x197f) {  // STG
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x384 || op == 0x984 || op == 0x1984) {  // LDS
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x388 || op == 0x988 || op == 0x1988) {  // STS
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x382 || op == 0xb82 || op == 0x1582 ||
                        op == 0x1d82 || op == 0x13ac || op == 0x15ac ||
                        op == 0x17ac || op == 0x19ac || op == 0x1bac ||
                        op == 0x1dac) {
                        return do_memory(ws, exec_mask, inst, pc, fault);  // LDC / LDCU
                    }
                    if (op == 0x383 || op == 0x983 || op == 0x1983) {  // LDL
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x387 || op == 0x987 || op == 0x1987) {  // STL
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x38a || op == 0x38b || op == 0x3a2 ||
                        op == 0x198a || op == 0x19a2 || op == 0x1f8a ||
                        op == 0x38c || op == 0x38d || op == 0x198c ||
                        op == 0x1f8c || op == 0x58d ||
                        op == 0x3a8 || op == 0x19a8 || op == 0x3a3 ||
                        op == 0x19a3 || op == 0x3a9 ||
                        op == 0x9a6 || op == 0x19a6) {  // ATOM/ATOMS/RED/REDS + ATOMG/REDG
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x992 || op == 0x3c6) {  // MEMBAR / FENCE
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x9ab || op == 0x5ab || op == 0x98f ||
                        op == 0x1d8f) {  // ERRBAR / CGAERRBAR / CCTL
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x91a || op == 0x1d1a || op == 0x9af) {
                        return do_memory(ws, exec_mask, inst, pc, fault);  // DEPBAR / LDGDEPBAR
                    }
                    if (op == 0x1fae || op == 0x1dae) {  // LDGSTS (cp.async)
                        return do_memory(ws, exec_mask, inst, pc, fault);
                    }
                    // ---- Phase 9 subset: mbarrier / TMA families ----------
                    if (op == 0x19a7 || op == 0x15a7 || op == 0x19b1 ||
                        op == 0x9b1 || op == 0x15b1 || op == 0x15b2 ||
                        op == 0x13b2 || op == 0x19b2 || op == 0x3a7) {  // SYNCS
                        return do_syncs(ws, exec_mask, inst, pc, fault);
                    }
                    if (op == 0x19b0) {  // ARRIVES (cp.async.mbarrier.arrive)
                        return do_arrives(ws, inst, pc, fault);
                    }
                    if (op == 0x15b4 || op == 0x13b4 || op == 0x13b5 ||
                        op == 0x13b6 || op == 0x9b7 || op == 0x19b9 ||
                        op == 0x9b9) {  // UTMALDG / UTMASTG / UTMAREDG /
                                        // UTMACMDFLUSH / UTMACCTL
                        return do_tma(ws, inst, pc, fault);
                    }
                    // ---- Phase 9 tensor core ------------------------------
                    if (op == 0x23c || op == 0x27a || op == 0x47f) {
                        // HMMA / QMMA / OMMA (dense F32-accumulator shapes).
                        return do_tensor(ws, exec_mask, inst, pc, fault);
                    }
                    return do_compute(ws, exec_mask, inst, pc, fault);
            }
        }
    return Status::success();
}

std::uint32_t& Interpreter::reg(ThreadState& t, int n) {
    static std::uint32_t kRz = 0;
    if (n == kRegRz) return kRz;
    return t.gpr[static_cast<std::size_t>(n)];
}

std::uint32_t Interpreter::read_reg(ThreadState& t, int n) const {
    if (n == kRegRz) return 0;
    return t.gpr[static_cast<std::size_t>(n)];
}

bool Interpreter::resolve_guard(const WarpState& w,
                                const DecodedInstruction& inst) {
    (void)w;
    // Guard is warp-uniform for uniform ops; for per-lane guards the
    // handler applies per-lane.  Phase 4: BRA/etc. apply the guard per
    // lane inside the handler.  Here return true when the guard is PT or
    // the predicate is set warp-uniformly (used for non-branch ops).
    if (inst.guard_pred == 7) return true;
    // Per-lane predicates are checked inside branch handlers; return true
    // so control-flow handlers apply per-lane logic.
    return true;
}

// Checked 64-bit multiply/add (High-2): no signed overflow UB.
namespace {
bool checked_mul4(std::int64_t a, std::int64_t* out) {
    // a * 4 with overflow check.
    if (a > INT64_MAX / 4 || a < INT64_MIN / 4) return false;
    *out = a * 4;
    return true;
}
bool checked_add(std::int64_t a, std::int64_t b, std::int64_t* out) {
    if ((b > 0 && a > INT64_MAX - b) || (b < 0 && a < INT64_MIN - b))
        return false;
    *out = a + b;
    return true;
}
// Checked `unsigned base + signed offset` (memory addresses; never wraps).
bool checked_add(std::uint64_t base, std::int64_t offset,
                 std::uint64_t* out) {
    if (offset >= 0) {
        const std::uint64_t d = static_cast<std::uint64_t>(offset);
        if (base > UINT64_MAX - d) return false;
        *out = base + d;
    } else {
        const std::uint64_t mag =
            static_cast<std::uint64_t>(-(offset + 1)) + 1;
        if (base < mag) return false;
        *out = base - mag;
    }
    return true;
}
// Checked unsigned + unsigned (never wraps).  Used to combine a GPR base with
// a uniform base where the sum could exceed 2^64 (High-2); silent wrap would
// fabricate a wrong (usually low) address.
bool checked_uadd(std::uint64_t a, std::uint64_t b, std::uint64_t* out) {
    if (a > UINT64_MAX - b) return false;
    *out = a + b;
    return true;
}
}  // namespace

std::optional<std::uint64_t> Interpreter::branch_target(
    const DecodedInstruction& inst, std::uint64_t pc,
    ThreadState& t) const {
    const std::string& m = inst.mnemonic;
    std::int64_t target_s = 0;
    if (m == "BRA" || m == "JMP") {
        auto imm = field_value(inst, "sImm");
        if (!imm) imm = field_value(inst, "Sa");
        if (!imm) imm = field_value(inst, "Sb");
        if (!imm) return std::nullopt;
        if (m == "BRA") {
            // sImm is a 56-bit two's-complement field (verified via the
            // assembler's backward BRA: raw 72057594037927924 == -12).
            const std::int64_t disp = sign_extend(*imm, 56);
            std::int64_t scaled;
            if (!checked_mul4(disp, &scaled)) return std::nullopt;
            // pc + 16 + scaled (checked).
            std::int64_t base;
            if (!checked_add(static_cast<std::int64_t>(pc), 16, &base))
                return std::nullopt;
            if (!checked_add(base, scaled, &target_s)) return std::nullopt;
        } else {
            // JMP absolute: Sa*4 (55-bit field, SCALE 4).
            std::int64_t sa;
            if (*imm > static_cast<std::uint64_t>(INT64_MAX)) return std::nullopt;
            sa = static_cast<std::int64_t>(*imm);
            if (!checked_mul4(sa, &target_s)) return std::nullopt;
        }
    } else if (m == "BRX" || m == "JMX") {
        // BRX/JMX use a 64-bit register pair Ra:R(a+1) (verified:
        // test_brx target = next_pc + sign-extended(Ra:R(a+1)) + off*4).
        auto ra = field_value(inst, "Ra");
        if (!ra) return std::nullopt;
        const int rlo = static_cast<int>(*ra);
        const std::uint64_t low = (rlo == kRegRz) ? 0 : read_reg(t, rlo);
        const std::uint64_t high =
            (rlo == kRegRz || rlo + 1 > kNumGprs - 1) ? 0
            : read_reg(t, rlo + 1);
        const std::uint64_t pair = low | (high << 32);
        // pair is the raw 64-bit displacement (two's complement).
        const std::int64_t disp = static_cast<std::int64_t>(pair);
        auto off = field_value(inst, "Ra_offset");
        const std::int64_t off_v = off ? sign_extend(*off, 58) : 0;
        std::int64_t scaled;
        if (!checked_mul4(off_v, &scaled)) return std::nullopt;
        std::int64_t base = (m == "BRX")
            ? static_cast<std::int64_t>(pc) + 16
            : static_cast<std::int64_t>(pc);
        if (!checked_add(base, disp, &base)) return std::nullopt;
        if (!checked_add(base, scaled, &target_s)) return std::nullopt;
    } else if (m == "BSSY") {
        // BSSY target is Sa*4 absolute (30-bit field, no PC add).
        auto sa = field_value(inst, "Sa");
        if (!sa) return std::nullopt;
        std::int64_t sav;
        if (*sa > static_cast<std::uint64_t>(INT64_MAX)) return std::nullopt;
        sav = static_cast<std::int64_t>(*sa);
        if (!checked_mul4(sav, &target_s)) return std::nullopt;
    } else {
        return std::nullopt;
    }
    // Medium-1: targets must be inside kernel text and 16-byte aligned.
    if (target_s < 0) return std::nullopt;
    const std::uint64_t target = static_cast<std::uint64_t>(target_s);
    if (target % 16 != 0 || target / 16 >= kernel_.predecoded.size())
        return std::nullopt;
    return target;
}

std::optional<std::uint64_t> Interpreter::probe_branch_target(
    const std::string& mnemonic, std::uint64_t pc, std::uint64_t pair,
    std::int64_t off, std::uint64_t text_size) {
    if (mnemonic != "BRX" && mnemonic != "JMX") return std::nullopt;
    const std::int64_t disp = static_cast<std::int64_t>(pair);
    std::int64_t scaled;
    if (!checked_mul4(off, &scaled)) return std::nullopt;
    std::int64_t base = (mnemonic == "BRX")
        ? static_cast<std::int64_t>(pc) + 16
        : static_cast<std::int64_t>(pc);
    if (!checked_add(base, disp, &base)) return std::nullopt;
    if (!checked_add(base, scaled, &base)) return std::nullopt;
    if (base < 0) return std::nullopt;
    const std::uint64_t target = static_cast<std::uint64_t>(base);
    if (target % 16 != 0 || target / 16 >= text_size / 16) return std::nullopt;
    return target;
}

std::optional<std::uint64_t> Interpreter::validate_control_target(
    std::uint64_t target) const {
    if (target % 16 != 0 || target / 16 >= kernel_.predecoded.size()) {
        return std::nullopt;
    }
    return target;
}

std::optional<SpecialReg> Interpreter::special_reg(
    const DecodedInstruction& inst) const {
    // S2R/S2UR encode the special register in the `imm8` raw field.
    auto v = field_value(inst, "imm8");
    if (!v) return std::nullopt;
    switch (*v) {
        case kSrLaneid: return SpecialReg::kLaneid;
        case kSrClock: return SpecialReg::kClock;
        case kSrTidX: return SpecialReg::kTidX;
        case kSrTidY: return SpecialReg::kTidY;
        case kSrTidZ: return SpecialReg::kTidZ;
        case kSrCtaidX: return SpecialReg::kCtaidX;
        case kSrCtaidY: return SpecialReg::kCtaidY;
        case kSrCtaidZ: return SpecialReg::kCtaidZ;
        case kSrNtid: return SpecialReg::kNtidX;
        case kSrWarpId: return SpecialReg::kWarpId;
        case kSrWarpSize: return SpecialReg::kWarpSize;
        case kSrNctaidX: return SpecialReg::kNctaidX;
        case kSrNctaidY: return SpecialReg::kNctaidY;
        case kSrNctaidZ: return SpecialReg::kNctaidZ;
        case kSrSmId: return SpecialReg::kSmId;
        case kSrSmemBase: return SpecialReg::kSmemBase;
        default: return SpecialReg::kUndefined;
    }
}

// Resolve a special register value for a lane.
namespace {
std::uint32_t resolve_sr(SpecialReg sr, int lane, int warp_id, int cta_id,
                         const LaunchEnv& env) {
    (void)cta_id;
    const int tid = warp_id * kLanesPerWarp + lane;
    switch (sr) {
        case SpecialReg::kLaneid: return static_cast<std::uint32_t>(lane);
        case SpecialReg::kTidX:
            return static_cast<std::uint32_t>(tid % env.block[0]);
        case SpecialReg::kTidY:
            return static_cast<std::uint32_t>((tid / env.block[0]) %
                                              env.block[1]);
        case SpecialReg::kTidZ:
            return static_cast<std::uint32_t>(tid / (env.block[0] *
                                                     env.block[1]));
        case SpecialReg::kCtaidX: return static_cast<std::uint32_t>(cta_id % env.grid[0]);
        case SpecialReg::kCtaidY: return static_cast<std::uint32_t>((cta_id / env.grid[0]) % env.grid[1]);
        case SpecialReg::kCtaidZ: return static_cast<std::uint32_t>(cta_id / (env.grid[0] * env.grid[1]));
        case SpecialReg::kNtidX: return env.block[0];
        case SpecialReg::kNtidY: return env.block[1];
        case SpecialReg::kNtidZ: return env.block[2];
        case SpecialReg::kNctaidX: return env.grid[0];
        case SpecialReg::kNctaidY: return env.grid[1];
        case SpecialReg::kNctaidZ: return env.grid[2];
        case SpecialReg::kClock: return 0;
        case SpecialReg::kWarpId: return static_cast<std::uint32_t>(warp_id);
        case SpecialReg::kWarpSize: return kLanesPerWarp;
        case SpecialReg::kSmemBase: return 0;
        case SpecialReg::kSmId: return static_cast<std::uint32_t>(env.sm_id);
        default: return 0;
    }
}
}  // namespace

// ---------------------------------------------------------------------------
// Opcode handlers
// ---------------------------------------------------------------------------

Status Interpreter::do_bra(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    // Per-lane guard: lanes whose predicate is false keep the advanced PC
    // (already pc+16); taken lanes jump to the target.
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        // Resolve the guard for this lane.
        bool take = true;
        if (inst.guard_pred != 7) {
            const bool pv = t.pred[inst.guard_pred];
            take = inst.guard_not ? !pv : pv;
        }
        if (take) {
            auto target = branch_target(inst, pc, t);
            if (!target) {
                Fault f(FaultKind::kInvalidInstruction,
                        "cannot resolve branch target at pc 0x" +
                            std::to_string(pc) + " (overflow/underflow)");
                f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
                if (fault) *fault = std::move(f);
                return Status::failure(Error::internal("branch fault"));
            }
            // Medium-1: shared control-target validation.
            auto v = validate_control_target(*target);
            if (!v) {
                Fault f(FaultKind::kInvalidInstruction,
                        "branch target 0x" + std::to_string(*target) +
                            " from pc 0x" + std::to_string(pc) +
                            " is not a valid instruction boundary");
                f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
                if (fault) *fault = std::move(f);
                return Status::failure(Error::internal("branch fault"));
            }
            t.pc = *v;
        }
    }
    return Status::success();
}

Status Interpreter::do_bssy(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc, std::uint32_t mask,
                            std::optional<Fault>* fault) {
    // Push {return_pc = pc+16, reconverge_target = Sa} for the active lanes
    // and continue linearly.  Per-lane guard: only lanes with the predicate
    // set push (others already advanced past).
    auto target = branch_target(inst, pc, w.threads[0]);
    if (!target) {
        // branch_target returns nullopt for out-of-range/overflow targets;
        // treat as a control-flow fault (Medium-1), not "unsupported".
        Fault f(FaultKind::kInvalidInstruction,
                "BSSY join target from pc 0x" + std::to_string(pc) +
                    " is out of range or misaligned");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("bssy fault"));
    }
    // Medium-1: BSSY join target must be a valid instruction boundary.
    auto v = validate_control_target(*target);
    if (!v) {
        Fault f(FaultKind::kInvalidInstruction,
                "BSSY join target 0x" + std::to_string(*target) +
                    " from pc 0x" + std::to_string(pc) +
                    " is not a valid instruction boundary");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("bssy fault"));
    }
    // Barrier register (Bn) from the `barReg` field; BSYNC must match it.
    auto barreg = field_value(inst, "barReg").value_or(0);
    std::uint32_t push_lanes = 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        bool push = true;
        if (inst.guard_pred != 7) {
            const bool pv = t.pred[inst.guard_pred];
            push = inst.guard_not ? !pv : pv;
        }
        if (push) push_lanes |= (1u << lane);
    }
    if (push_lanes != 0) {
        WarpState::SyncEntry e;
        e.return_pc = pc + 16;
        e.reconverge_pc = *v;
        e.barrier_register = static_cast<std::uint32_t>(barreg);
        e.participating_lanes = push_lanes;
        e.pending_lanes = push_lanes;
        e.arrived_lanes = 0;
        w.sync_stack.push_back(e);
    }
    return Status::success();
}

void Interpreter::converge_completed_sync(WarpState& w) {
    // Collect indices of completed entries (pending == 0).
    std::vector<std::size_t> done;
    for (std::size_t i = 0; i < w.sync_stack.size(); ++i) {
        if (w.sync_stack[i].pending_lanes == 0) done.push_back(i);
    }
    if (done.empty()) return;
    // Converge each completed entry's participating lanes to the join.
    for (const std::size_t i : done) {
        WarpState::SyncEntry& e = w.sync_stack[i];
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(e.participating_lanes & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (t.exited) continue;
            t.active = true;
            t.pc = e.reconverge_pc + 16;  // continue after the join
        }
    }
    // Erase from largest index to smallest so earlier indices stay valid.
    std::sort(done.begin(), done.end(), std::greater<std::size_t>());
    for (const std::size_t i : done) {
        if (i < w.sync_stack.size()) {
            w.sync_stack.erase(w.sync_stack.begin() +
                               static_cast<std::ptrdiff_t>(i));
        }
    }
}

Status Interpreter::do_bsync(WarpState& w, const DecodedInstruction& inst,
                             std::uint64_t pc, std::uint32_t mask,
                             std::optional<Fault>* fault) {
    (void)fault;
    // Find the top sync entry matching this BSYNC's barrier register.
    auto barreg = field_value(inst, "barReg").value_or(0);
    auto it = std::find_if(w.sync_stack.rbegin(), w.sync_stack.rend(),
                           [&](const WarpState::SyncEntry& e) {
                               return e.barrier_register == barreg;
                           });
    if (it == w.sync_stack.rend()) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "BSYNC B" + std::to_string(barreg) + " at pc 0x" +
                    std::to_string(pc) + " with no matching BSSY entry");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    WarpState::SyncEntry& entry = *it;
    // Only lanes currently executing the BSYNC (mask) that are still
    // pending participants actually arrive here.
    std::uint32_t arriving = mask & entry.pending_lanes;
    entry.pending_lanes &= ~arriving;
    entry.arrived_lanes |= arriving;
    // Suspend the arrived lanes (sync-wait): they stop being runnable until
    // every participating lane arrives.
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (arriving & (1u << lane)) {
            w.threads[lane].active = false;  // sync-wait
        }
    }
    // When all participating lanes have arrived (or exited), converge:
    // resume every participating lane at the join PC and erase the entry
    // (safe index-based helper, no iterator invalidation).
    converge_completed_sync(w);
    return Status::success();
}

Status Interpreter::do_exit(WarpState& w, const DecodedInstruction& inst,
                            std::uint32_t mask, std::uint64_t pc) {
    (void)pc;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        bool take = true;
        if (inst.guard_pred != 7) {
            const bool pv = t.pred[inst.guard_pred];
            take = inst.guard_not ? !pv : pv;
        }
        if (take) {
            t.exited = true;
            t.active = false;
            // Step 5: remove this lane from any sync entry's pending set —
            // an exited lane no longer needs to reach the BSYNC join point.
            for (auto& e : w.sync_stack) {
                const std::uint32_t bit = (1u << lane);
                if (e.participating_lanes & bit) {
                    e.pending_lanes &= ~bit;
                    // If the lane was already waiting (arrived), it never
                    // will; drop it so completion can still trigger.
                    e.arrived_lanes &= ~bit;
                }
            }
            // If removing this lane completes any sync entry, converge
            // them safely (helper handles multiple completions).
            converge_completed_sync(w);
        }
    }
    return Status::success();
}

Status Interpreter::do_s2r(WarpState& w, const DecodedInstruction& inst,
                           std::uint32_t mask, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    auto sr = special_reg(inst);
    if (!sr) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "S2R with unsupported special register at pc 0x" +
                    std::to_string(pc));
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    auto rd = field_value(inst, "Rd");
    if (!rd) {
        Fault f(FaultKind::kInternal, "S2R missing Rd field");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        t.gpr[static_cast<std::size_t>(*rd)] =
            resolve_sr(*sr, lane, w.warp_id, w.cta_id, env_);
    }
    return Status::success();
}

Status Interpreter::do_s2ur(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc,
                            std::optional<Fault>* fault) {
    (void)inst; (void)fault;
    auto sr = special_reg(inst);
    if (!sr) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "S2UR with unsupported special register at pc 0x" +
                    std::to_string(pc));
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    auto urd = field_value(inst, "URd");
    if (!urd) {
        // S2UR renders URd as Rd in the field table.
        urd = field_value(inst, "Rd");
    }
    if (!urd) {
        Fault f(FaultKind::kInternal, "S2UR missing URd field");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    // Uniform value: lane 0's view (warp-uniform).
    w.ur[static_cast<std::size_t>(*urd)] =
        resolve_sr(*sr, 0, w.warp_id, w.cta_id, env_);
    return Status::success();
}

Status Interpreter::do_bar(WarpState& w, const DecodedInstruction& inst,
                           std::uint32_t mask, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    (void)mask;
    // BAR.SYNC n: all participating warps arrive at barrier n; the warp
    // waits (suspended) until every warp in the CTA has arrived.
    auto bid = field_value(inst, "barname");
    if (!bid) {
        Fault f(FaultKind::kInternal, "BAR.SYNC missing barname");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    CtaState& cta = ctas_[w.local_cta_id];
    auto& bar = cta.barriers[*bid];
    if (std::find(bar.arrived.begin(), bar.arrived.end(), w.warp_id) ==
        bar.arrived.end()) {
        bar.arrived.push_back(w.warp_id);
    }
    const std::uint64_t total_threads = static_cast<std::uint64_t>(
        env_.block[0]) * env_.block[1] * env_.block[2];
    const int nwarps = static_cast<int>((total_threads + kLanesPerWarp - 1) /
                                        kLanesPerWarp);
    if (static_cast<int>(bar.arrived.size()) >= nwarps) {
        // All warps arrived: release every warp suspended at this barrier.
        // Phase 6 Step 2D: the barrier establishes happens-before across all
        // participating warps (race detector merges their clocks).  Buffered
        // as a race event so it is replayed in deterministic order.
        if (race_detector_ && race_detector_->enabled()) {
            std::vector<std::uint32_t> warps;
            for (int wi = 0; wi < nwarps; ++wi) warps.push_back(
                static_cast<std::uint32_t>(wi));
            RaceEvent ev;
            ev.kind = RaceEvent::kCtaBarrier;
            ev.cta = static_cast<std::uint32_t>(cta.cta_id);
            ev.sm = sm_of_cta(static_cast<std::uint32_t>(cta.cta_id));
            ev.ordinal = race_ordinal_[ev.cta]++;
            ev.warps = std::move(warps);
            race_log_.push_back(std::move(ev));
        }
        bar.arrived.clear();
        for (auto& ws : cta.warps) {
            if (ws.waiting_barrier == static_cast<int>(*bid)) {
                for (auto& t : ws.threads) {
                    if (t.exited) continue;
                    t.active = true;  // resume
                }
                ws.waiting_barrier = -1;
            }
        }
        return Status::success();
    }
    // Suspend this warp at the barrier: its active lanes stop being
    // runnable until released by the last arrival.
    w.waiting_barrier = static_cast<int>(*bid);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (w.threads[lane].active && !w.threads[lane].exited) {
            w.threads[lane].active = false;  // suspended at barrier
        }
    }
    return Status::success();
}

// ---------------------------------------------------------------------------
// Minimal ALU (needed to run control-flow kernels).
// ---------------------------------------------------------------------------

namespace {

// Read a register operand (Ra/Rb/Rc/Ra_URc) with RZ=0.
std::uint32_t read_op(const ThreadState& t, const DecodedInstruction& inst,
                      const char* field) {
    auto v = field_value(inst, field);
    if (!v) return 0;
    const std::uint64_t val = *v;
    if (val == 255) return 0;  // RZ
    if (val >= 256) return 0;
    return t.gpr[static_cast<std::size_t>(val)];
}

// Look up a decoded operand by slot name.
const Operand* find_op(const DecodedInstruction& inst, const char* name) {
    for (const auto& o : inst.operands) {
        if (o.slot == name) return &o;
    }
    return nullptr;
}

// Look up a FORMAT slot value by slot name (modifiers included).
std::optional<std::uint64_t> slot_value(const DecodedInstruction& inst,
                                        const char* name) {
    for (const auto& [n, v] : inst.slot_values) {
        if (n == name) return v;
    }
    return std::nullopt;
}

// Read a register-valued operand with RZ=0 + negate/absolute applied.
std::uint32_t read_reg_val(const ThreadState& t, const Operand& op) {
    std::uint32_t v = 0;
    if (op.kind == "Register" || op.kind == "ZeroRegister" ||
        op.kind == "NonZeroRegister") {
        const std::uint64_t r = static_cast<std::uint64_t>(op.value);
        if (r != 255 && r < kNumGprs) v = t.gpr[r];
    }
    if (op.absolute) v &= 0x7fffffff;
    if (op.negated) v = ~v + 1;
    return v;
}

// M5 pre-binding: extract a register operand's index once per instruction
// (-1 when absent / RZ / not a plain register) so the per-lane hot loop
// avoids string compares.  Applies the same RZ==0 + range rule as
// read_reg_val.
int bind_reg_index(const Operand* op) {
    if (!op || (op->kind != "Register" && op->kind != "ZeroRegister" &&
                op->kind != "NonZeroRegister"))
        return -1;
    const std::uint64_t r = static_cast<std::uint64_t>(op->value);
    if (r == 255 || r >= kNumGprs) return -1;
    return static_cast<int>(r);
}

// Per-lane register read from a pre-bound index (negate/absolute applied).
std::uint32_t read_bound(const ThreadState& t, int idx, bool absolute,
                         bool negated) {
    std::uint32_t v = idx >= 0 ? t.gpr[idx] : 0;
    if (absolute) v &= 0x7fffffff;
    if (negated) v = ~v + 1;
    return v;
}

// Read a uniform-register operand from warp state (URZ = 255 -> 0).
std::uint32_t read_ur_val(const WarpState& w, const Operand& op) {
    if (op.kind == "UniformRegister" || op.kind == "NonZeroUniformRegister" ||
        op.kind == "ZeroUniformRegister") {
        const std::uint64_t r = static_cast<std::uint64_t>(op.value);
        if (r == 255) return 0;  // URZ
        if (r < kNumUrs) return w.ur[r];
    }
    return 0;
}

// Read a 64-bit uniform-register PAIR (URc | UR(c+1) << 32) with URZ=0
// (High-1).  LDGSTS's uniform base / descriptor UR operand is a 64-bit pair:
// the CONDITIONS pin it to `URc <= MAX_UNIFORM_REG_COUNT-2` with an even
// alignment, so reading only the low 32 bits (read_ur_val) silently drops the
// high word whenever UR(c+1) is nonzero — the caller must use this helper.
std::uint64_t read_ur_pair(const WarpState& w, const Operand& op) {
    if (op.kind != "UniformRegister" &&
        op.kind != "NonZeroUniformRegister" &&
        op.kind != "ZeroUniformRegister") {
        return 0;
    }
    const std::uint64_t r = static_cast<std::uint64_t>(op.value);
    if (r == 255) return 0;  // URZ
    if (r >= kNumUrs - 1) return 0;  // no room for the high word
    return static_cast<std::uint64_t>(w.ur[r]) |
           (static_cast<std::uint64_t>(w.ur[r + 1]) << 32);
}

// Extract a predicate operand's value per-lane (Pp, Pu, Pv, Pq).  Returns
// false when the operand is absent.  `not` flag inverts.
bool read_pred(const ThreadState& t, const Operand& op, bool* out) {
    if (op.kind != "Predicate") return false;
    const std::uint64_t p = static_cast<std::uint64_t>(op.value);
    if (p == 7) {  // PT
        *out = !op.pred_not;
        return true;
    }
    if (p < 7) {
        bool v = t.pred[p];
        if (op.pred_not) v = !v;
        *out = v;
        return true;
    }
    return false;
}

// Write a predicate destination (Pu/Pv/Pq) per-lane.
void write_pred(ThreadState& t, const Operand& op, bool v) {
    if (op.kind != "Predicate") return;
    const std::uint64_t p = static_cast<std::uint64_t>(op.value);
    if (p < 7) t.pred[p] = v;
}

}  // namespace

Status Interpreter::do_mov(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc) {
    (void)pc;
    auto rd = field_value(inst, "Rd");
    if (!rd) {
        Fault f(FaultKind::kInternal, "MOV missing Rd");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id));
        return Status::failure(Error::internal("MOV missing Rd"));
    }
    // MOV Rd, Rb (reg), MOV Rd, URb (uniform), or MOV Rd, imm (Ra_offset).
    auto rb = field_value(inst, "Rb");
    const Operand* urb = find_op(inst, "URb");
    std::uint32_t src = 0;
    if (urb) {
        src = read_ur_val(w, *urb);
    } else if (rb) {
        src = read_op(w.threads[0], inst, "Rb");
    } else {
        auto imm = field_value(inst, "Ra_offset");
        if (imm) src = static_cast<std::uint32_t>(*imm);

    }
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        // Per-lane source for reg form; uniform source is warp-wide.
        std::uint32_t s = (urb || !rb) ? src : read_op(t, inst, "Rb");
        t.gpr[static_cast<std::size_t>(*rd)] = s;
    }
    return Status::success();
}

// UMOV (uniform move): URd = imm (0x882) / URd = URb (0x1c82) /
// URd:URd+1 = 64-bit imm (0x1482).
Status Interpreter::do_umov(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc) {
    (void)pc;
    const Operand* urd = find_op(inst, "URd");
    if (!urd || urd->kind != "UniformRegister") return Status::success();
    const std::uint64_t u = static_cast<std::uint64_t>(urd->value);
    if (u == 255 || u >= kNumUrs) return Status::success();
    const Operand* urb = find_op(inst, "URb");
    const Operand* sb = find_op(inst, "Sb");
    std::uint32_t val = 0;
    if (urb) {
        val = read_ur_val(w, *urb);
    } else if (sb) {
        val = static_cast<std::uint32_t>(sb->value);
    }
    w.ur[static_cast<std::size_t>(u)] = val;
    // imm64 form writes the 64-bit immediate to URd:URd+1.
    if (inst.variant_class.find("imm64") != std::string::npos && sb &&
        u + 1 < kNumUrs) {
        w.ur[static_cast<std::size_t>(u + 1)] =
            static_cast<std::uint32_t>(static_cast<std::uint64_t>(sb->value) >>
                                       32);
    }
    return Status::success();
}

// UIADD3 (uniform): URd = URa + URb + URc (with optional negate / RIR imm).
// URc == 255 (UZ, the encoder's "no third reg" pin) means the addend comes
// from the Sb immediate instead (Phase 9 subset: building mbarrier init
// words as "UR12 = 0x100000 - 1").
Status Interpreter::do_uiadd3(WarpState& w, const DecodedInstruction& inst,
                              std::uint64_t pc) {
    (void)pc;
    const Operand* urd = find_op(inst, "URd");
    if (!urd || urd->kind != "UniformRegister") return Status::success();
    const std::uint64_t u = static_cast<std::uint64_t>(urd->value);
    if (u == 255 || u >= kNumUrs) return Status::success();
    const Operand* ura = find_op(inst, "URa");
    const Operand* urb = find_op(inst, "URb");
    const Operand* urc = find_op(inst, "URc");
    const Operand* sb = find_op(inst, "Sb");  // RIR immediate addend
    std::uint32_t a = 0;
    if (ura && ura->value != 255) {
        a = read_ur_val(w, *ura);
        if (ura->negated) a = ~a + 1;
    }
    std::uint32_t b = 0;
    if (urb && urb->value != 255) b = read_ur_val(w, *urb);
    std::uint32_t c = 0;
    if (urc && urc->value != 255) {
        c = read_ur_val(w, *urc);
        if (urc->negated) c = ~c + 1;
    } else if (sb) {
        c = static_cast<std::uint32_t>(sb->value);
        if (sb->negated) c = ~c + 1;
    }
    w.ur[static_cast<std::size_t>(u)] = a + b + c;
    return Status::success();
}

// USHF (uniform shift): URd = URa << Sb (or >> for the R form).  The shift
// amount lives in the Sb immediate slot (bits[63:32]) and the direction in
// the SDIR modifier, encoded at bit76 (memdesc): L = 0, R = 1.
Status Interpreter::do_ushf(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc) {
    (void)pc;
    const Operand* urd = find_op(inst, "URd");
    if (!urd || urd->kind != "UniformRegister") return Status::success();
    const std::uint64_t u = static_cast<std::uint64_t>(urd->value);
    if (u == 255 || u >= kNumUrs) return Status::success();
    const Operand* ura = find_op(inst, "URa");
    const Operand* sb = find_op(inst, "Sb");
    if (!ura) return Status::success();
    std::uint32_t a = read_ur_val(w, *ura);
    const std::uint32_t s = sb ? static_cast<std::uint32_t>(sb->value) : 0;
    // SDIR: L=0 / R=1 at bit76 of the 128-bit word.
    const bool shift_right = ((inst.word.hi >> 12) & 1) != 0;
    w.ur[static_cast<std::size_t>(u)] =
        shift_right ? (a >> (s & 31)) : (a << (s & 31));
    return Status::success();
}

Status Interpreter::do_iadd3(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst,
                             std::uint64_t pc) {
    (void)pc;
    auto rd = field_value(inst, "Rd");
    if (!rd) {
        Fault f(FaultKind::kInternal, "IADD3 missing Rd");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id));
        return Status::failure(Error::internal("IADD3 missing Rd"));
    }
    const Operand* ra_op = find_op(inst, "Ra");
    const Operand* rb_op = find_op(inst, "Rb");
    const Operand* rc_op = find_op(inst, "Rc");
    const bool ra_neg = ra_op ? ra_op->negated
        : field_value(inst, "e").value_or(0) != 0;
    const bool rc_neg = rc_op ? rc_op->negated
        : field_value(inst, "sz").value_or(0) != 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = ra_op ? read_reg_val(t, *ra_op) : 0;
        std::uint32_t b = 0;
        if (rb_op) {
            b = read_reg_val(t, *rb_op);
        } else if (auto imm = field_value(inst, "Ra_offset")) {
            b = static_cast<std::uint32_t>(sign_extend(*imm, 32));
        }
        std::uint32_t c = rc_op ? read_reg_val(t, *rc_op) : 0;
        (void)ra_neg;
        (void)rc_neg;
        // read_reg_val already applies the operand negate/absolute flags.
        t.gpr[static_cast<std::size_t>(*rd)] = a + b + c;
    }
    return Status::success();
}

Status Interpreter::do_isetp(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst,
                             std::uint64_t pc) {
    (void)pc;
    auto pd = field_value(inst, "Pu");  // destination predicate
    if (!pd) {
        Fault f(FaultKind::kInternal, "ISETP missing Pu");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id));
        return Status::failure(Error::internal("ISETP missing Pu"));
    }
    // Comparison from the icmp (ICmpAll) field: F=0 LT=1 EQ=2 LE=3
    // GT=4 NE=5 GE=6 T=7.
    const std::uint64_t cmp = [&]() -> std::uint64_t {
        if (auto v = slot_value(inst, "icmp")) return *v;
        if (auto v = field_value(inst, "dstfmt")) return *v;
        return 1;
    }();
    const std::uint64_t bop = slot_value(inst, "bop").value_or(0);
    const Operand* pv = find_op(inst, "Pv");
    const Operand* pp = find_op(inst, "Pp");
    const int pnum = static_cast<int>(*pd);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_op(t, inst, "Ra");
        std::uint32_t b = 0;
        if (auto imm = field_value(inst, "Ra_offset")) {
            b = static_cast<std::uint32_t>(*imm);
        } else {
            b = read_op(t, inst, "Rb");
        }
        bool r = false;
        switch (cmp) {
            case 0: r = false; break;  // F
            case 1: r = a < b; break;
            case 2: r = a == b; break;
            case 3: r = a <= b; break;
            case 4: r = a > b; break;
            case 5: r = a != b; break;
            case 6: r = a >= b; break;
            case 7: r = true; break;   // T
            default: r = false; break;
        }
        // Bop combines the comparison with Pp (AND/OR/XOR).
        bool ppv = true;
        if (pp) read_pred(t, *pp, &ppv);
        switch (bop) {
            case 0: r = r && ppv; break;
            case 1: r = r || ppv; break;
            case 2: r = r != ppv; break;
            default: break;
        }
        if (pnum < 7) t.pred[static_cast<std::size_t>(pnum)] = r;
        if (pv && pv->value < 7) t.pred[pv->value] = !r;
    }
    return Status::success();
}

Status Interpreter::do_imad(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst,
                            std::uint64_t pc,
                            std::optional<Fault>* fault) {
    (void)pc;
    auto rd = field_value(inst, "Rd");
    if (!rd) {
        Fault f(FaultKind::kInternal, "IMAD missing Rd");
        f.set_warp(static_cast<std::uint32_t>(w.warp_id));
        return Status::failure(Error::internal("IMAD missing Rd"));
    }
    // IMAD Rd, Ra, Rb, Rc (also used as MOV via IMAD.MOV).
    const Operand* ra_op = find_op(inst, "Ra");
    const Operand* rb_op = find_op(inst, "Rb");
    const Operand* rc_op = find_op(inst, "Rc");
    // The decoder reports every IMAD width variant under mnemonic "IMAD";
    // the WIDE/HI distinction lives in the variant class.
    const bool is_wide = inst.variant_class.find("wide") != std::string::npos ||
                         inst.variant_class.find("hi") != std::string::npos;
    const bool is_hi = inst.variant_class.find("hi") != std::string::npos;
    // The X-extended forms (IMAD.X / IMAD.WIDE.X / IMAD.HI.X) add carry-in
    // (from the [!]Pp predicate) and carry-out (to Pu) semantics that Phase 5
    // does not implement or verify.  Degrade them explicitly to unsupported
    // instead of silently computing a carry-less result.
    const bool is_x = inst.variant_class.find("_x") != std::string::npos;
    if (is_x) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "instruction '" + inst.mnemonic + "' (" + inst.variant_class +
                    ") X carry form is not implemented at pc " +
                    std::to_string(pc));
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc)
            .set_active_mask(mask).set_instruction(inst.word);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        if (is_wide) {
            // 64-bit multiply-accumulate.
            //   IMAD.WIDE: {Rd+1,Rd} = Ra*Rb + {Rc,Rc+1}  (full 64-bit)
            //   IMAD.HI:   Rd = high32(Ra*Rb + {Rc,Rc+1})
            // Ra/Rb are 32-bit; Rc is a full 64-bit register pair that is
            // used verbatim (its high half is already the 64-bit value; we
            // must NOT re-sign-extend from the low half's bit 31).
            const std::uint32_t au = ra_op ? read_reg_val(t, *ra_op) : 0;
            const std::uint32_t bu = rb_op ? read_reg_val(t, *rb_op) : 0;
            const bool sign = slot_value(inst, "fmt").value_or(1) != 0;
            // 32x32 -> 64-bit product bit pattern.  Signed mode sign-extends
            // the two 32-bit inputs to int64; |int32|^2 <= 2^62 so the int64
            // product never overflows.  Unsigned mode uses uint64 widths.
            std::uint64_t prod;
            if (sign) {
                const std::int64_t as = static_cast<std::int32_t>(au);
                const std::int64_t bs = static_cast<std::int32_t>(bu);
                prod = static_cast<std::uint64_t>(as * bs);
            } else {
                prod = static_cast<std::uint64_t>(au) *
                       static_cast<std::uint64_t>(bu);
            }
            std::uint64_t c = 0;
            if (rc_op && rc_op->kind == "Register") {
                const std::uint64_t r = static_cast<std::uint64_t>(rc_op->value);
                if (r != 255 && r < kNumGprs - 1) {
                    c = t.gpr[r] |
                        (static_cast<std::uint64_t>(t.gpr[r + 1]) << 32);
                }
            }
            // Modular 64-bit addition (no signed-overflow UB).
            const std::uint64_t out = prod + c;
            const std::uint64_t r = *rd;
            if (r == 255 || r >= kNumGprs) continue;
            if (is_hi) {
                t.gpr[r] = static_cast<std::uint32_t>(out >> 32);
            } else {  // IMAD.WIDE / IMAD.WIDE.X
                if (r + 1 >= kNumGprs) continue;
                t.gpr[r] = static_cast<std::uint32_t>(out & 0xffffffffu);
                t.gpr[r + 1] = static_cast<std::uint32_t>(out >> 32);
            }
            continue;
        }
        std::uint32_t a = ra_op ? read_reg_val(t, *ra_op) : 0;
        std::uint32_t b = rb_op ? read_reg_val(t, *rb_op) : 0;
        std::uint32_t c = rc_op ? read_reg_val(t, *rc_op) : 0;
        // IMAD.MOV: Ra=RZ -> just move c.
        if (ra_op && ra_op->value == 255) {
            t.gpr[static_cast<std::size_t>(*rd)] = c;
        } else {
            t.gpr[static_cast<std::size_t>(*rd)] = a * b + c;
        }
    }
    return Status::success();
}

// ---------------------------------------------------------------------------
// Phase 5 compute handlers (integer/bit, FP, conversions, compares,
// collectives).  Dispatch is keyed on the decoded mnemonic because several
// encodings share an opcode (LOP3/LOP, ISCADD/LEA).
// ---------------------------------------------------------------------------

namespace {

// Destination write helper: write a value to Rd.  For 64-bit destinations
// (`hi` != the low half and the destination is a register pair), writes Rd+1
// as well.  Handles Rd=RZ (discard).
void write_rd(WarpState& w, ThreadState& t, const DecodedInstruction& inst,
              const Operand* rd, std::uint32_t lo, std::uint32_t hi,
              bool write_hi = false) {
    (void)w;
    (void)inst;
    if (!rd || rd->kind != "Register") return;
    const std::uint64_t r = static_cast<std::uint64_t>(rd->value);
    if (r == 255 || r >= kNumGprs) return;  // RZ dest: discard
    t.gpr[r] = lo;
    if (write_hi && r + 1 < kNumGprs) {
        t.gpr[r + 1] = hi;
    }
}

}  // namespace

// ---------------------------------------------------------------------------
// Phase 6 memory + sync
// ---------------------------------------------------------------------------

// Decode the `sz` slot for LDS (LDSSIZE enum) and LDG/STS/LDC/LDL/STL
// (SZ_U8_S8_U16_S16_32_64_128).  Returns the MemWidthInfo.
namespace {

MemWidthInfo mem_sz(const DecodedInstruction& inst) {
    auto sz = slot_value(inst, "sz").value_or(4);
    return mem_width_info(sz);
}

// Read a 64-bit address operand (register pair {Ra,Ra+1}) for LDG/STG.
// Accepts every register operand kind (Register / NonZeroRegister /
// ZeroRegister — RZ reads as 0).
std::uint64_t read_addr_pair(const ThreadState& t, const Operand* ra) {
    if (!ra || (ra->kind != "Register" && ra->kind != "NonZeroRegister" &&
                ra->kind != "ZeroRegister")) {
        return 0;
    }
    const std::uint64_t r = static_cast<std::uint64_t>(ra->value);
    if (r == 255 || r >= kNumGprs - 1) return 0;
    return static_cast<std::uint64_t>(t.gpr[r]) |
           (static_cast<std::uint64_t>(t.gpr[r + 1]) << 32);
}

// Blocker-4: decode the ATOMS `op` slot (AtomsOp /
// OP_ADD_MIN_MAX_INC_DEC_AND_OR_XOR_EXCH_SAFEADD) into the MemoryService
// AtomicOp, honoring the integer size (S32/S64 -> SIGNED min/max; INC/DEC are
// U32-only per the spec's CONDITIONS).  Returns nullopt for FP atomic ops
// (ATOMICFPOPS), SAFEADD, INVALID op values and illegal width/op combos — the
// caller MUST fault and must NEVER downgrade to ADD.  CAS is decoded
// separately by the presence of the Rc compare operand.
std::optional<AtomicOp> decode_atomic_op(const DecodedInstruction& inst) {
    if (inst.variant_class.find("_fp") != std::string::npos) {
        return std::nullopt;  // ATOM.FADD / ATOM.FMIN / ... unimplemented
    }
    const std::uint64_t opv = slot_value(inst, "op").value_or(0);
    const std::uint64_t szv = slot_value(inst, "sz").value_or(0);
    const bool signed_size = (szv == 1 || szv == 3);  // S32 / S64
    switch (opv) {
        case 0: return AtomicOp::kAdd;
        case 1: return signed_size ? AtomicOp::kMinSigned : AtomicOp::kMin;
        case 2: return signed_size ? AtomicOp::kMaxSigned : AtomicOp::kMax;
        case 3: return szv == 0 ? std::optional<AtomicOp>(AtomicOp::kInc)
                                : std::nullopt;  // INC (U32 only)
        case 4: return szv == 0 ? std::optional<AtomicOp>(AtomicOp::kDec)
                                : std::nullopt;  // DEC (U32 only)
        case 5: return AtomicOp::kAnd;
        case 6: return AtomicOp::kOr;
        case 7: return AtomicOp::kXor;
        case 8: return AtomicOp::kExch;
        case 9: return std::nullopt;  // SAFEADD (ATOMG/REDG) unimplemented
        default: return std::nullopt;  // INVALID*
    }
}

// Read a signed/unsigned immediate OFFSET operand's value (e.g. Ra_offset /
// Rb_offset).  The decoder stores SImm operand values SIGN-EXTENDED (matching
// render_imm), so a negative displacement (STS [R1-0x20]) reads as -0x20, not
// +0xFFFFE0.  Falls back to the raw slot value when the operand is absent.
std::int64_t offset_value(const DecodedInstruction& inst, const char* slot) {
    if (const Operand* op = find_op(inst, slot)) return op->value;
    return static_cast<std::int64_t>(slot_value(inst, slot).value_or(0));
}

}  // namespace

Status Interpreter::resolve_mem_addr(const DecodedInstruction& inst,
                                     const ThreadState& t,
                                     const WarpState& w,
                                     std::uint64_t* addr_out,
                                     std::int64_t* off_out,
                                     std::uint64_t* width_out,
                                     AddressSpace* space_out,
                                     std::optional<Fault>* fault) {
    (void)w;
    (void)fault;
    const std::string& m = inst.mnemonic;
    MemWidthInfo wi = mem_sz(inst);
    *width_out = wi.bytes;
    *off_out = offset_value(inst, "Ra_offset");

    if (m == "LDG" || m == "STG" || m == "LDL" || m == "STL") {
        // Global/local: descriptor + Ra(64) + signed offset.
        const Operand* ra = find_op(inst, "Ra");
        const std::uint64_t ra_val = read_addr_pair(t, ra);
        // The descriptor's Ra_URb / Ra_URc provides the descriptor UR pair;
        // step 1 uses a single global buffer, so the address = Ra + offset.
        *addr_out = ra_val;
        *space_out = (m == "LDL" || m == "STL") ? AddressSpace::kLocal
                                                : AddressSpace::kGlobal;
        return Status::success();
    }
    if (m == "LDS" || m == "STS" || m == "ATOMS" || m == "REDS") {
        // Shared: 32-bit Ra + offset.
        const Operand* ra = find_op(inst, "Ra");
        *addr_out = ra ? read_reg_val(t, *ra) : 0;
        *space_out = AddressSpace::kShared;
        return Status::success();
    }
    if (m == "LDC" || m == "LDCU") {
        // Constant: bank (Sa_bank) + offset (Ra_offset).  The address is the
        // constant-bank window offset; bank n spans [n*64K, (n+1)*64K).
        const auto bank = slot_value(inst, "Sa_bank").value_or(0);
        // For the RaRZ form the offset is in Ra_offset; for RaNonRZ it may be
        // Ra + Ra_offset.  c[0x0][0x380] -> bank 0, Ra=RZ, offset 0x380.
        const Operand* ra = find_op(inst, "Ra");
        const std::uint64_t ra_val = ra ? read_reg_val(t, *ra) : 0;
        const std::int64_t roff = offset_value(inst, "Ra_offset");
        *addr_out = bank * 0x10000 + ra_val +
                    static_cast<std::uint64_t>(roff);
        *space_out = AddressSpace::kConstant;
        return Status::success();
    }
    if (m == "ATOMG" || m == "REDG") {
        // Global atomic: descriptor + Ra(64) + signed offset.
        const Operand* ra = find_op(inst, "Ra");
        const std::uint64_t ra_val = read_addr_pair(t, ra);
        *addr_out = ra_val;
        *space_out = AddressSpace::kGlobal;
        return Status::success();
    }
    if (m == "ATOM" || m == "RED") {
        const Operand* ra = find_op(inst, "Ra");
        *addr_out = ra ? read_reg_val(t, *ra) : 0;
        *space_out = AddressSpace::kGlobal;
        return Status::success();
    }
    return Status::failure(Error(ErrorCode::kUnimplemented,
                                 "memory address resolve for '" + m + "'"));
}

Status Interpreter::do_memory(WarpState& w, std::uint32_t mask,
                              const DecodedInstruction& inst,
                              std::uint64_t pc,
                              std::optional<Fault>* fault) {
    const std::string& m = inst.mnemonic;

    // Barriers / fences / depbar: functional no-ops (single-writer model) but
    // keep the scoreboard bookkeeping consistent.  MEMBAR/FENCE also feed the
    // race detector (recorded fence: no standalone HB; combined with a
    // matching release/acquire atomic).
    if (m == "MEMBAR" || m == "FENCE") {
        memory_->membar();
        if (race_detector_ && race_detector_->enabled()) {
            std::string scope = "gpu";
            if (m == "MEMBAR") {
                const auto scov = slot_value(inst, "sco").value_or(2);
                if (scov == 0) scope = "cta";
                else if (scov == 1) scope = "sm";
                else if (scov == 3) scope = "sys";
                else if (scov == 5) scope = "vc";
                else scope = "gpu";
            } else {
                scope = "gpu";  // FENCE (fence.g / fence.membar.gl)
            }
            RaceEvent ev;
            ev.kind = RaceEvent::kFence;
            ev.cta = static_cast<std::uint32_t>(w.cta_id);
            ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
            ev.ordinal = race_ordinal_[ev.cta]++;
            ev.warp = static_cast<std::uint32_t>(w.warp_id);
            ev.scope = std::move(scope);
            race_log_.push_back(std::move(ev));
        }
        return Status::success();
    }
    if (m == "ERRBAR" || m == "CGAERRBAR" || m == "CCTL") {
        // Cache/error-reporting barriers emitted around MEMBAR (IVALL / WBALL
        // etc.).  Functional no-ops in the single-writer model.
        return Status::success();
    }
    if (m == "DEPBAR" || m == "LDGDEPBAR") {
        if (m == "LDGDEPBAR") {
            // cp.async.commit_group: seal the open LDGSTS group and count it
            // on the target scoreboard (wr).
            do_ldgdepbar(w, inst, pc);
        } else {
            // DEPBAR.LE SBn, cnt / DEPBAR {S} / DEPBAR.ALL: drain the group
            // tally.  Step 1 memory is synchronous so every copy already
            // landed; the bookkeeping is observable for the profiler/debugger.
            do_depbar(w, inst, pc);
        }
        return Status::success();
    }
    if (m == "BAR") {
        return do_bar(w, inst, mask, pc, fault);
    }

    // LDGSTS / cp.async (coupled L1-read -> shared-write).  Functional copy
    // (global -> shared per lane) plus the trace-only UnifiedV1 prediction.
    if (m == "LDGSTS") {
        return do_ldgsts(w, mask, inst, pc, fault);
    }

    // Loads / stores / atomics: resolve once per lane.
    const Operand* rd = find_op(inst, "Rd");
    const Operand* rb = find_op(inst, "Rb");
    const bool is_load = (m == "LDG" || m == "LDS" || m == "LDC" ||
                          m == "LDCU" || m == "LDL");
    const bool is_atom = (m == "ATOM" || m == "ATOMS" || m == "RED" ||
                          m == "REDS" || m == "ATOMG" || m == "REDG");

    // Phase 6 Step 2B: trace-only subcore issue event for this memory op.
    // Never changes the functional path below.  Phase 8: the raw per-lane
    // byte ranges of the COMMITTED access are collected inside the per-lane
    // loop and the event is emitted afterwards (committed-access semantics —
    // a lane that faults never appears in the profiler stream, matching the
    // race detector / L2 trace).
    std::vector<LaneByteRange> prof_lanes(kLanesPerWarp);
    std::uint32_t prof_committed = 0;
    AddressSpace prof_space = AddressSpace::kGlobal;
    std::uint32_t prof_width = 0;  // last committed lane width (atomics use
                                   // ATOMICINTSIZES, not the load/store enum)
    bool prof_is_write = is_atom || !is_load;

    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;

        std::uint64_t addr = 0;
        std::int64_t off = 0;
        std::uint64_t w_ = 0;
        AddressSpace space = AddressSpace::kGlobal;
        Status rs = resolve_mem_addr(inst, t, w, &addr, &off, &w_, &space,
                                     fault);
        if (rs.failed()) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               rs.error().message())
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }
        MemWidthInfo wi = mem_sz(inst);
        wi.bytes = w_;
        if (!wi.valid) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "invalid memory width slot")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }
        if (is_atom) {
            // ATOM/ATOMS use ATOMICINTSIZES (U32=0, S32=1, U64=2, S64=3,
            // 128=4) — not the SZ_U8_... load/store enum.
            const auto szv = slot_value(inst, "sz").value_or(0);
            if (szv == 2 || szv == 3) wi.bytes = 8;
            else if (szv == 4) wi.bytes = 16;
            else wi.bytes = 4;
        }

        // Blocker-3: compute the overflow-safe EFFECTIVE address ONCE and use
        // it for the functional MemoryService call, the race detector and the
        // L2 sector trace alike.  Previously the functional path applied
        // addr+off internally while record_race_access/record_l2_access got
        // the bare `addr`, so two accesses with the same base but different
        // displacements were misjudged overlapping, different base+disp pairs
        // landing on the same byte were missed, and L2 sector/coalesce traces
        // were wrong.  Constant addresses already fold the offset in during
        // resolve_mem_addr, so no second add there.
        std::uint64_t effective = 0;
        if (space == AddressSpace::kConstant) {
            effective = addr;
        } else if (!checked_add(addr, off, &effective)) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "memory address overflow")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }

        if (is_load) {
            // Phase 6 Step 2C: trace-only L2 event for global loads.
            if (space == AddressSpace::kGlobal) {
                record_l2_access(w, inst, pc, mask, "load", space, effective,
                                 wi.bytes, static_cast<std::uint32_t>(lane));
            }
            // Phase 6 Step 2D: race detector (shared/global only).
            if (space == AddressSpace::kShared ||
                space == AddressSpace::kGlobal) {
                record_race_access(w, inst, pc, lane, space, effective,
                                   wi.bytes, false, false, "", "");
            }
            MemValue val{};
            Status st = Status::success();
            if (space == AddressSpace::kGlobal) {
                st = memory_->ldg(DevicePtr{0}, effective, 0, wi, val);
            } else if (space == AddressSpace::kShared) {
                st = MemoryService::lds(ctas_[w.local_cta_id].shared, effective,
                                        0, wi, val);
            } else if (space == AddressSpace::kConstant) {
                st = memory_->ldc(0, effective, wi, val);
            } else {  // local (per-warp window)
                st = MemoryService::lds(w.local, effective, 0, wi, val);
            }
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            // Phase 7 debug capture: the load committed.
            record_debug_access(w, static_cast<std::uint32_t>(lane), space,
                                effective, wi.bytes, false, false);
            // Phase 8 profiler: record the committed lane byte range.
            prof_lanes[static_cast<std::size_t>(lane)] = {
                effective, wi.bytes, true};
            prof_committed |= (1u << lane);
            prof_space = space;
            prof_width = static_cast<std::uint32_t>(wi.bytes);
            // 128-bit loads write Rd..Rd+3; narrower write Rd (and Rd+1 for
            // 64-bit) (Blocker-3).
            if (rd) {
                const std::uint64_t r = static_cast<std::uint64_t>(rd->value);
                if (r != 255 && r < kNumGprs) {
                    t.gpr[r] = val[0];
                    if (wi.bytes > 4 && r + 1 < kNumGprs) t.gpr[r + 1] = val[1];
                    if (wi.bytes > 8) {
                        if (r + 2 < kNumGprs) t.gpr[r + 2] = val[2];
                        if (r + 3 < kNumGprs) t.gpr[r + 3] = val[3];
                    }
                }
            }
            continue;
        }

        // Store / atomic: source value from Rb (or Rd for ATOMS' result).
        // 128-bit stores read Rb..Rb+3.
        MemValue val{};
        if (rb) {
            const std::uint64_t r = static_cast<std::uint64_t>(rb->value);
            if (r != 255 && r < kNumGprs) {
                val[0] = t.gpr[r];
                if (wi.bytes > 4 && r + 1 < kNumGprs) val[1] = t.gpr[r + 1];
                if (wi.bytes > 8) {
                    if (r + 2 < kNumGprs) val[2] = t.gpr[r + 2];
                    if (r + 3 < kNumGprs) val[3] = t.gpr[r + 3];
                }
            }
        }
        if (is_atom) {
            // Phase 6 Step 2D: race detector observation (shared/global).
            // Decode the real sem/sco so release/acquire clock bookkeeping
            // (Blocker-2) sees the actual memory order.
            const std::uint64_t semv = slot_value(inst, "sem").value_or(1);
            const std::uint64_t scov = slot_value(inst, "sco").value_or(0);
            std::string mem_order = "relaxed";
            if (semv == 2) mem_order = "acq_rel";
            else if (semv == 3) mem_order = "mmio";
            std::string scope;
            if (scov == 0) scope = "nosco";
            else if (scov == 1) scope = "cta";
            else if (scov == 2) scope = "sm";
            else if (scov == 3) scope = "vc";
            else if (scov == 4) scope = "gpu";
            else scope = "sys";
            // High-3: decode + validate the atomic BEFORE recording any race /
            // L2 event.  The race detector and L2 trace represent COMMITTED
            // memory accesses — an atomic that faults (unsupported op / FP /
            // SAFEADD / INVALID / 128-bit width / misaligned / OOB) must never
            // appear in the race log or the L2 access trace as if it happened.
            //
            // Blocker-4: decode the REAL atomic op.  FP atomics (ATOMICFPOPS),
            // SAFEADD, INVALID op slots and unsupported width/op combinations
            // fault as kNotSupported — they are NEVER silently downgraded to
            // ADD (INC/DEC were previously run as +1, MIN/MAX as unsigned).
            AtomicOp op = AtomicOp::kAdd;
            std::optional<AtomicOp> dec = decode_atomic_op(inst);
            if (find_op(inst, "Rc")) {
                dec = AtomicOp::kCas;  // ATOM/ATOMS/ATOMG.CAS / .CAST
            }
            if (!dec) {
                if (fault) {
                    *fault = Fault(FaultKind::kUnsupportedInstruction,
                                   inst.mnemonic + " atomic op is not "
                                   "implemented (never downgraded to ADD)")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            op = *dec;
            // CAS compare operand (Rc) for the compare-and-swap RMW.
            const MemValue* cmp = nullptr;
            MemValue cmp_val{};
            if (op == AtomicOp::kCas) {
                const Operand* rc = find_op(inst, "Rc");
                if (rc) {
                    const std::uint64_t r =
                        static_cast<std::uint64_t>(rc->value);
                    if (r != 255 && r < kNumGprs) {
                        cmp_val[0] = t.gpr[r];
                        if (wi.bytes > 4 && r + 1 < kNumGprs)
                            cmp_val[1] = t.gpr[r + 1];
                        if (wi.bytes > 8) {
                            if (r + 2 < kNumGprs) cmp_val[2] = t.gpr[r + 2];
                            if (r + 3 < kNumGprs) cmp_val[3] = t.gpr[r + 3];
                        }
                        cmp = &cmp_val;
                    }
                }
            }
            MemValue old{};
            Status st = (space == AddressSpace::kGlobal)
                ? memory_->atom_global(effective, wi.bytes, op, val, old, cmp)
                : MemoryService::atom_shared(ctas_[w.local_cta_id].shared,
                                             effective, wi.bytes, op, val, old,
                                             cmp);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            // The RMW committed: NOW record the race access and the L2 access
            // (committed-access semantics).
            if (space == AddressSpace::kShared ||
                space == AddressSpace::kGlobal) {
                record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                                   space, effective, wi.bytes, true, true,
                                   mem_order, scope);
            }
            if (space == AddressSpace::kGlobal) {
                record_l2_access(w, inst, pc, mask, "atomic", space, effective,
                                 wi.bytes, static_cast<std::uint32_t>(lane));
            }
            // Phase 7 debug capture: the atomic RMW committed.
            record_debug_access(w, static_cast<std::uint32_t>(lane), space,
                                effective, wi.bytes, true, true);
            // Phase 8 profiler: record the committed lane byte range.
            prof_lanes[static_cast<std::size_t>(lane)] = {
                effective, wi.bytes, true};
            prof_committed |= (1u << lane);
            prof_space = space;
            prof_width = static_cast<std::uint32_t>(wi.bytes);
            // Write the pre-value back to Rd (ATOM) or Rd for ATOMS.
            if (rd) {
                const std::uint64_t r = static_cast<std::uint64_t>(rd->value);
                if (r != 255 && r < kNumGprs) {
                    t.gpr[r] = old[0];
                    if (wi.bytes > 4 && r + 1 < kNumGprs) t.gpr[r + 1] = old[1];
                    if (wi.bytes > 8) {
                        if (r + 2 < kNumGprs) t.gpr[r + 2] = old[2];
                        if (r + 3 < kNumGprs) t.gpr[r + 3] = old[3];
                    }
                }
            }
            continue;
        }
        // Plain store.
        Status st = Status::success();
        if (space == AddressSpace::kGlobal) {
            st = memory_->stg(DevicePtr{0}, effective, 0, wi, val);
        } else if (space == AddressSpace::kShared) {
            st = MemoryService::sts(ctas_[w.local_cta_id].shared, effective, 0,
                                    wi, val);
        } else if (space == AddressSpace::kConstant) {
            // Constant stores are illegal (read-only) — model as a fault.
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "store to constant address space")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        } else {  // local
            st = MemoryService::sts(w.local, effective, 0, wi, val);
        }
        if (st.failed()) {
            if (fault) {
                *fault = memory_error_to_fault(
                             st.error(), pc,
                             static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }
        // High-3: the store committed — only now record the race access and L2
        // access (committed-access semantics, matching the atomic path).  A
        // store that faulted (OOB / misaligned / constant) never appears in the
        // race log or the L2 trace as if it happened.
        if (space == AddressSpace::kShared || space == AddressSpace::kGlobal) {
            record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                               space, effective, wi.bytes, true, false, "", "");
        }
        if (space == AddressSpace::kGlobal) {
            record_l2_access(w, inst, pc, mask, "store", space, effective,
                             wi.bytes, static_cast<std::uint32_t>(lane));
        }
        // Phase 7 debug capture: the store committed.
        record_debug_access(w, static_cast<std::uint32_t>(lane), space,
                            effective, wi.bytes, true, false);
        // Phase 8 profiler: record the committed lane byte range.
        prof_lanes[static_cast<std::size_t>(lane)] = {effective, wi.bytes,
                                                      true};
        prof_committed |= (1u << lane);
        prof_space = space;
        prof_width = static_cast<std::uint32_t>(wi.bytes);
    }
    // Phase 6 Step 2B / Phase 8: emit the trace-only issue event with the
    // committed per-lane ranges (never changes the functional path above).
    {
        std::string kind = "load";
        if (is_atom) kind = "atomic";
        else if (!is_load) kind = "store";
        record_memory_event(w, inst, pc, mask, kind,
                            prof_width != 0 ? prof_width : static_cast<std::uint32_t>(mem_sz(inst).bytes),
                            prof_space, prof_is_write, prof_lanes,
                            prof_committed);
    }
    return Status::success();
}

// Deterministic CTA -> SM mapping (High-3): with simulated_sm_count > 1 the
// CTA's SM is cta % count (explicit multi-SM topology shared by the race, L2
// and subcore layers); with 1 the launch's env_.sm_id applies.
std::uint32_t Interpreter::sm_of_cta(std::uint32_t cta) const {
    const std::uint32_t n =
        options_.model.simulated_sm_count > 0
            ? options_.model.simulated_sm_count
            : 1;
    if (n > 1) return cta % n;
    return static_cast<std::uint32_t>(env_.sm_id);
}

// ---------------------------------------------------------------------------
// Phase 9 subset: mbarrier / TMA / cp.async functional handlers
// ---------------------------------------------------------------------------

// Resolve a shared byte offset into the (CTA-local index, offset) pair.
// When clusters are enabled and the address's high byte is a nonzero cluster
// rank, translate to the peer CTA's shared window (DSMEM).  Cross-CTA access
// only works when the target CTA is present in THIS interpreter instance
// (single worker / the worker owning that CTA); otherwise it is a structured
// error.
std::optional<Interpreter::SharedTarget> Interpreter::resolve_shared_target(
    const WarpState& w, std::uint32_t shared_addr,
    std::optional<Fault>* fault) {
    SharedTarget out;
    const std::uint32_t rank = shared_addr >> 24;
    const std::uint32_t off = shared_addr & 0xFFFFFF;
    if (!cluster_topology_ || rank == 0) {
        out.cta_local_idx = static_cast<std::size_t>(w.local_cta_id);
        out.offset = shared_addr;
        out.target_rank = 0;
        return out;
    }
    // DSMEM: rank -> grid-linear target CTA within the source CTA's cluster.
    const std::uint64_t src_cta = static_cast<std::uint64_t>(w.cta_id);
    const std::uint64_t cluster = cluster_topology_->cluster_id(src_cta);
    if (!cluster_topology_->valid_rank(rank)) {
        if (fault) {
            *fault = Fault(FaultKind::kIllegalMemoryAccess,
                           "DSMEM rank " + std::to_string(rank) +
                               " out of range for cluster size " +
                               std::to_string(cluster_topology_->cluster_size()))
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return std::nullopt;
    }
    const std::uint64_t tgt_cta =
        cluster_topology_->grid_cta(cluster, rank);
    // Find the target CTA's local index (must be in this worker's subset).
    std::size_t local = 0;
    bool found = false;
    for (; local < ctas_.size(); ++local) {
        if (ctas_[local].cta_id == static_cast<int>(tgt_cta)) {
            found = true;
            break;
        }
    }
    if (!found) {
        if (fault) {
            *fault = Fault(
                FaultKind::kUnsupportedInstruction,
                "DSMEM target CTA " + std::to_string(tgt_cta) +
                    " is not owned by this interpreter worker (cluster "
                    "cross-CTA access requires single-worker determinism)")
                    .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return std::nullopt;
    }
    out.cta_local_idx = local;
    out.offset = off;
    out.target_rank = rank;
    return out;
}

// Look up (or lazily create from the shared word) the mbarrier state for a
// shared byte offset in the source CTA.  Returns null when the shared
// address is out of the window.
MbarrierState* Interpreter::mbarrier_at(CtaState& cta,
                                        std::uint32_t shared_off,
                                        bool create_if_missing) {
    auto it = cta.mbarriers.find(shared_off);
    if (it != cta.mbarriers.end()) return &it->second;
    if (!create_if_missing) return nullptr;
    // Read the current 64-bit word at the shared offset (may be an
    // uninitialized/zero barrier; SYNCS.ARRIVE on it faults as not-initialized
    // unless the program initialized it with SYNCS.EXCH.64 first).
    MbarrierState s;
    if (shared_off <= cta.shared.size() &&
        shared_off + 8 <= cta.shared.size()) {
        std::uint64_t word = 0;
        for (int i = 0; i < 8; ++i)
            word |= static_cast<std::uint64_t>(cta.shared[shared_off + i])
                    << (8 * i);
        // A zero word is a valid "uninitialized" marker: keep initialized=false
        // so the first ARRIVE faults (matches the boundary tests).  A non-zero
        // word (written by SYNCS.EXCH.64 / STS init) seeds the logical state.
        if (word != 0) s = MbarrierState::from_init_word(word);
    }
    auto [it2, _] = cta.mbarriers.emplace(shared_off, s);
    return &it2->second;
}

// Functional LDGSTS (cp.async): perform the global->shared copy per active
// lane and accumulate committed bytes into the CTA's open async group.  Also
// records the trace-only coupled prediction (kept from the old trace-only
// path).
Status Interpreter::do_ldgsts(WarpState& w, std::uint32_t mask,
                              const DecodedInstruction& inst, std::uint64_t pc,
                              std::optional<Fault>* fault) {
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    std::uint32_t goff[kLanesPerWarp] = {};
    std::uint32_t soff[kLanesPerWarp] = {};
    const std::int64_t rao = offset_value(inst, "Ra_offset");
    const std::int64_t rbo = offset_value(inst, "Rb_offset");
    const Operand* ra = find_op(inst, "Ra");
    const Operand* urc = find_op(inst, "Ra_URc");
    const bool wide = slot_value(inst, "input_reg_sz_64_dist").value_or(0) != 0;
    const std::uint64_t ur_base = urc ? read_ur_pair(w, *urc) : 0;
    const auto szv = slot_value(inst, "sz").value_or(0);
    const std::uint32_t ew = szv == 1 ? 8u : szv == 2 ? 16u : 4u;

    std::uint32_t goff_valid_mask = 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        const Operand* rb = find_op(inst, "Rb");
        const std::uint64_t s = rb ? read_reg_val(t, *rb) : 0;
        std::uint64_t g = 0;
        if (wide) {
            g = read_addr_pair(t, ra);
        } else if (ra) {
            g = read_reg_val(t, *ra);
        }
        std::uint64_t gadd = 0, gv = 0, sv = 0;
        if (!checked_uadd(g, ur_base, &gadd) ||
            !checked_add(gadd, rao, &gv) ||
            !checked_add(s, rbo, &sv)) {
            continue;  // lane excluded: address computation failed
        }
        goff[lane] = static_cast<std::uint32_t>(gv);
        soff[lane] = static_cast<std::uint32_t>(sv);
        goff_valid_mask |= (1u << lane);
        MemValue val{};
        Status st = memory_->ldg(DevicePtr{0}, gv, 0,
                                 MemWidthInfo{ew, false, true}, val);
        if (st.failed()) {
            if (fault) {
                *fault = memory_error_to_fault(
                             st.error(), pc,
                             static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask & (1u << lane));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        if (sv > cta.shared.size() || ew > cta.shared.size() - sv) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "LDGSTS shared destination out of bounds")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask & (1u << lane));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        for (std::uint32_t i = 0; i < ew; ++i) {
            cta.shared[sv + i] =
                static_cast<std::uint8_t>((val[i / 4] >> (8 * (i % 4))) & 0xff);
        }
        // Race + profiler observability: the committed global read range and
        // the shared write range.
        if (race_detector_ && race_detector_->enabled()) {
            record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                               AddressSpace::kGlobal, gv, ew, false, false, "",
                               "");
            record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                               AddressSpace::kShared, sv, ew, true, false, "",
                               "");
        }
    }
    // cp.async committed-bytes accounting: each lane commits `ew` bytes.
    const std::uint32_t committed = static_cast<std::uint32_t>(
        __builtin_popcount(goff_valid_mask)) * ew;
    if (committed) {
        cta.async_open.copies.push_back(
            CtaState::AsyncCopy{committed, 0});
        cta.async_open.committed_bytes += committed;
    }
    // Trace-only coupled prediction (kept for the L1TEX profiler).  The
    // coupled event carries ldgsts_goff/ldgsts_soff, which the profiler uses
    // to recompute the extended access-set counters — so no separate raw
    // event is emitted here (the profiler's expansion must match this
    // functional copy exactly; tests verify that).
    if (options_.model.l1tex == L1TexMode::kTraceOnly) {
        record_coupled_l1_to_shared(w, inst, pc, goff_valid_mask, goff, soff,
                                    ew, goff_valid_mask != mask);
    }
    // Phase 7 debug capture: shared writes committed.
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(goff_valid_mask & (1u << lane))) continue;
        record_debug_access(w, static_cast<std::uint32_t>(lane),
                            AddressSpace::kShared, soff[lane], ew, true, false);
    }
    return Status::success();
}

// LDGDEPBAR: seal the open async group and count it on the target SB.
void Interpreter::do_ldgdepbar(WarpState& w, const DecodedInstruction& inst,
                               std::uint64_t pc) {
    (void)w;
    (void)pc;
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    if (!cta.async_open.copies.empty() || cta.async_open.committed_bytes > 0) {
        // Seal into the committed group list (observable async state).
        cta.async_groups.push_back(cta.async_open);
        const auto wr = slot_value(inst, "dst_wr_sb").value_or(0);
        if (wr < cta.sb_group_count.size()) {
            cta.sb_group_count[wr]++;
        }
        cta.async_open = {};
    }
}

// DEPBAR.LE SBn, cnt: wait until SBn's group count <= cnt.  Memory is
// synchronous, so every copy has already landed; the bookkeeping (which
// groups are "in flight") is observable for the profiler/debugger.
void Interpreter::do_depbar(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc) {
    (void)pc;
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    const auto le = slot_value(inst, "le").value_or(0);
    const auto sbidx = slot_value(inst, "sbidx").value_or(0);
    const auto cnt = slot_value(inst, "cnt").value_or(0);
    if (le && sbidx < cta.sb_group_count.size()) {
        // Drain (seal->complete) groups until SBn's count <= cnt.  The copies
        // are already in shared; only the group tally is adjusted.
        if (cta.sb_group_count[sbidx] > cnt) {
            std::uint64_t excess = cta.sb_group_count[sbidx] - cnt;
            while (excess-- > 0 && !cta.async_groups.empty()) {
                cta.async_groups.pop_back();
            }
            cta.sb_group_count[sbidx] = cnt;
        }
    } else {
        // DEPBAR {S} / DEPBAR.ALL: drain everything.
        cta.async_groups.clear();
        std::fill(cta.sb_group_count.begin(), cta.sb_group_count.end(), 0);
    }
    if (cnt == 0) memory_->drain();
}

// ---------------------------------------------------------------------------
// Phase 9 subset: SYNCS (mbarrier) family
// ---------------------------------------------------------------------------
// The SYNCS classes (sm120):
//   syncs_arrive_ / syncs_tcnt_  0x19a7  ARRIVE / expect_tx / complete_tx
//   syncs_phasechk_              0x15a7  PHASECHK / try_wait.parity
//   syncs_cctl_                  0x19b1  CCTL per-address (.IV/.WB)
//   syncs_cctl_all_              0x9b1   CCTL.ALL (.IVALL/.WBALL)
//   syncs_ld_                    0x15b1  load barrier state to a GPR (.WATCH)
//   syncs_flush_                 0x3a7   barrier cache flush (decode-only)
//   syncs_uniform_exch_          0x15b2  EXCH.64 (mbarrier.init = uniform exchange)
//   syncs_uniform_cas_           0x13b2  CAS.64
//   syncs_uniform_ld_            0x19b2  LD.64 (uniform load)
//
// ARRIVE paramtype (bits[86:84]) selects {arrive, tx} contributions:
//   A1TR=0 (arrive+1, tx+R)  A1T0=1 (arrive+1, tx+0)  A0T1=2 (arrive+0, tx+1)
//   A0TR=3 (arrive+0, tx+R)  A0TX=4 (arrive+0, tx-R)  ART0=5 (arrive+R, tx+0)
// retval (bits[74:73]): OLDSTATE=0 (token in Rd) / TMASK=1 / RED=2 (DSMEM).

Status Interpreter::do_syncs(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst, std::uint64_t pc,
                             std::optional<Fault>* fault) {
    const std::uint16_t op = semu::opcode_of(inst.word.lo, inst.word.hi);
    // Guard: SYNCS.EXCH/CAS/LD are uniform-predicate guarded (@UPg); the
    // others carry a per-lane Pg (typically PT).  resolve_guard returns true
    // for PT; for uniform predicates the group already filtered per-lane.  We
    // accept an all-zeros guard meaning "every lane skipped" — execute_group
    // already returned for exec_mask == 0.
    (void)mask;

    // Shared target = [Ra + URc + Ra_offset] (Ra is RZ for mbarrier ops).
    const Operand* ura = find_op(inst, "URa");
    const Operand* urc = find_op(inst, "Ra_URc");
    const Operand* ura_off = find_op(inst, "URa_offset");
    const Operand* ra = find_op(inst, "Ra");
    const Operand* ra_off = find_op(inst, "Ra_offset");

    std::uint32_t addr = 0;
    if (ura) {
        addr = read_ur_val(w, *ura);
        const std::int64_t off = ura_off ? ura_off->value : 0;
        addr = static_cast<std::uint32_t>(
            static_cast<std::uint64_t>(addr) +
            static_cast<std::uint64_t>(off));
    } else {
        const std::uint64_t base = urc ? read_ur_val(w, *urc) : 0;
        const std::int64_t off = ra_off ? ra_off->value : 0;
        const std::uint64_t rbase =
            (ra && ra->kind == "Register") ? read_reg_val(w.threads[0], *ra)
                                           : 0;
        addr = static_cast<std::uint32_t>(
            rbase + base + static_cast<std::uint64_t>(off));
    }

    CtaState* cta = &ctas_[static_cast<std::size_t>(w.local_cta_id)];
    // Uniform atomics operate on the CURRENT CTA's shared window (no DSMEM
    // translation needed — EXCH/CAS/LD are local shared memory ops).
    switch (op) {
        case 0x19a7: {  // ARRIVE / tcnt (expect_tx / complete_tx)
            const std::uint64_t paramtype =
                slot_value(inst, "paramtype").value_or(0);
            const std::uint64_t retval =
                slot_value(inst, "retval").value_or(0);
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.ARRIVE at out-of-window shared "
                                   "address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const Operand* rb = find_op(inst, "Rb");
            const std::uint64_t rv =
                rb ? read_reg_val(w.threads[0], *rb) : 0;
            std::uint32_t inc = 0;
            std::uint64_t tx = 0;
            bool tx_is_complete = false;
            switch (paramtype) {
                case 0: inc = 1; tx = rv; break;          // A1TR
                case 1: inc = 1; tx = 0; break;           // A1T0
                case 2: inc = 0; tx = 1; break;           // A0T1
                case 3: inc = 0; tx = rv; break;          // A0TR (expect_tx)
                case 4: inc = 0; tx = rv; tx_is_complete = true; break;  // A0TX
                case 5: inc = static_cast<std::uint32_t>(rv); break;     // ART0
                default: {
                    if (fault) {
                        *fault = Fault(FaultKind::kInvalidInstruction,
                                       "SYNCS.ARRIVE invalid paramtype")
                                     .set_pc(pc)
                                     .set_warp(static_cast<std::uint32_t>(w.warp_id));
                    }
                    return Status::failure(Error::internal("memory fault"));
                }
            }
            MbarrierResult r = mbarrier_arrive(st, inc, tx, tx_is_complete);
            if (r.fault) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            // Mirror the new state word back into shared memory.
            const std::uint64_t nw = st->encode();
            if (addr <= cta->shared.size() && addr + 8 <= cta->shared.size()) {
                for (int i = 0; i < 8; ++i)
                    cta->shared[addr + i] =
                        static_cast<std::uint8_t>((nw >> (8 * i)) & 0xff);
            }
            // Token (retval OLDSTATE): write the old state word into Rd
            // (64-bit pair for TRANS64).
            if (retval == 0) {
                const Operand* rd = find_op(inst, "Rd");
                if (rd && rd->kind == "Register") {
                    const std::uint64_t reg = static_cast<std::uint64_t>(rd->value);
                    if (reg != 255 && reg + 1 < kNumGprs) {
                        w.threads[0].gpr[reg] =
                            static_cast<std::uint32_t>(r.old_word & 0xffffffffu);
                        w.threads[0].gpr[reg + 1] =
                            static_cast<std::uint32_t>(r.old_word >> 32);
                    }
                }
            }
            return Status::success();
        }
        case 0x15a7: {  // PHASECHK / try_wait.parity
            const Operand* pu = find_op(inst, "Pu");
            const Operand* rb = find_op(inst, "Rb");
            const std::uint64_t parity =
                rb ? ((read_reg_val(w.threads[0], *rb) >> 31) & 1) : 0;
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.PHASECHK at out-of-window shared "
                                   "address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            MbarrierResult r = mbarrier_phasechk(*st, static_cast<std::uint32_t>(parity));
            if (r.fault) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            if (pu && pu->kind == "Predicate") {
                const std::uint64_t p = static_cast<std::uint64_t>(pu->value);
                if (p < 7) {
                    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                        if (mask & (1u << lane))
                            w.threads[lane].pred[p] = r.predicate;
                    }
                }
            }
            return Status::success();
        }
        case 0x19b1: {  // CCTL per-address (.IV / .WB)
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.CCTL at out-of-window shared address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const auto cctlop = slot_value(inst, "cctlop").value_or(0);
            if (cctlop == 0) mbarrier_invalidate(st);  // IV
            // WB is a writeback hint: functional no-op.
            return Status::success();
        }
        case 0x9b1: {  // CCTL.ALL (.IVALL / .WBALL)
            const auto cctlop = slot_value(inst, "cctlop").value_or(0);
            if (cctlop == 0) {
                for (auto& [_, st] : cta->mbarriers) {
                    mbarrier_invalidate(&st);
                }
            }
            return Status::success();
        }
        case 0x15b1: {  // LD: load barrier state (64-bit) into GPR Rd
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.LD at out-of-window shared address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const Operand* rd = find_op(inst, "Rd");
            if (rd && rd->kind == "Register") {
                const std::uint64_t reg = static_cast<std::uint64_t>(rd->value);
                const std::uint64_t nw = st->encode();
                if (reg != 255 && reg + 1 < kNumGprs) {
                    w.threads[0].gpr[reg] =
                        static_cast<std::uint32_t>(nw & 0xffffffffu);
                    w.threads[0].gpr[reg + 1] =
                        static_cast<std::uint32_t>(nw >> 32);
                }
            }
            return Status::success();
        }
        case 0x3a7: {  // flush: decode-only
            if (fault) {
                *fault = Fault(FaultKind::kUnsupportedInstruction,
                               "SYNCS.FLUSH is decode-only (not implemented)")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        case 0x15b2: {  // EXCH.64: uniform shared atomic exchange (mbarrier.init)
            const Operand* urd = find_op(inst, "URd");
            const Operand* urb = find_op(inst, "URb");
            const std::uint64_t new_val =
                urb ? read_ur_pair(w, *urb) : 0;
            if (addr > cta->shared.size() || addr + 8 > cta->shared.size()) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.EXCH.64 out of shared window")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            std::uint64_t old_val = 0;
            for (int i = 0; i < 8; ++i)
                old_val |= static_cast<std::uint64_t>(cta->shared[addr + i])
                           << (8 * i);
            for (int i = 0; i < 8; ++i)
                cta->shared[addr + i] =
                    static_cast<std::uint8_t>((new_val >> (8 * i)) & 0xff);
            // Re-seed the mbarrier logical state from the exchanged word
            // (mbarrier.init writes the init encoding here).
            if (new_val != 0) {
                cta->mbarriers[addr] = MbarrierState::from_init_word(new_val);
            } else {
                cta->mbarriers.erase(addr);
            }
            if (urd) {
                const std::uint64_t u = static_cast<std::uint64_t>(urd->value);
                if (u != 255 && u + 1 < kNumUrs) {
                    w.ur[u] = static_cast<std::uint32_t>(old_val & 0xffffffffu);
                    w.ur[u + 1] = static_cast<std::uint32_t>(old_val >> 32);
                }
            }
            return Status::success();
        }
        case 0x13b2: {  // CAS.64: uniform shared atomic compare-and-swap
            const Operand* urd = find_op(inst, "URd");
            const Operand* urb = find_op(inst, "URb");
            const Operand* urc = find_op(inst, "URc");
            if (addr > cta->shared.size() || addr + 8 > cta->shared.size()) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.CAS.64 out of shared window")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            std::uint64_t old_val = 0;
            for (int i = 0; i < 8; ++i)
                old_val |= static_cast<std::uint64_t>(cta->shared[addr + i])
                           << (8 * i);
            const std::uint64_t cmp = urc ? read_ur_pair(w, *urc) : 0;
            if (old_val == cmp) {
                const std::uint64_t new_val = urb ? read_ur_pair(w, *urb) : 0;
                for (int i = 0; i < 8; ++i)
                    cta->shared[addr + i] =
                        static_cast<std::uint8_t>((new_val >> (8 * i)) & 0xff);
                if (new_val != 0) {
                    cta->mbarriers[addr] = MbarrierState::from_init_word(new_val);
                } else {
                    cta->mbarriers.erase(addr);
                }
            }
            if (urd) {
                const std::uint64_t u = static_cast<std::uint64_t>(urd->value);
                if (u != 255 && u + 1 < kNumUrs) {
                    w.ur[u] = static_cast<std::uint32_t>(old_val & 0xffffffffu);
                    w.ur[u + 1] = static_cast<std::uint32_t>(old_val >> 32);
                }
            }
            return Status::success();
        }
        case 0x19b2: {  // LD.64: uniform shared load
            const Operand* urd = find_op(inst, "URd");
            if (addr > cta->shared.size() || addr + 8 > cta->shared.size()) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.LD.64 out of shared window")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            std::uint64_t v = 0;
            for (int i = 0; i < 8; ++i)
                v |= static_cast<std::uint64_t>(cta->shared[addr + i]) << (8 * i);
            if (urd) {
                const std::uint64_t u = static_cast<std::uint64_t>(urd->value);
                if (u != 255 && u + 1 < kNumUrs) {
                    w.ur[u] = static_cast<std::uint32_t>(v & 0xffffffffu);
                    w.ur[u + 1] = static_cast<std::uint32_t>(v >> 32);
                }
            }
            return Status::success();
        }
        default:
            return do_unsupported(w, inst, pc, mask, fault);
    }
}

// ARRIVES (0x19b0): cp.async.mbarrier.arrive[.noinc].  Couples the current
// thread's outstanding LDGSTS group to the mbarrier at [URc+off]:
//   .TRANSCNT (barop=2): the group's committed bytes decrement the barrier's
//     pending tx count once the copies land (immediate in the synchronous
//     model).
//   .ARVCNT (barop=1): arrive without incrementing (cp.async.mbarrier.arrive
//     .noinc).
//   .LEGACY (barop=0): legacy arrive-count form (decode-only).
Status Interpreter::do_arrives(WarpState& w, const DecodedInstruction& inst,
                               std::uint64_t pc,
                               std::optional<Fault>* fault) {
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    const Operand* urc = find_op(inst, "Ra_URc");
    const Operand* ra_off = find_op(inst, "Ra_offset");
    const std::uint64_t base = urc ? read_ur_val(w, *urc) : 0;
    const std::int64_t off = ra_off ? ra_off->value : 0;
    const std::uint32_t addr = static_cast<std::uint32_t>(
        base + static_cast<std::uint64_t>(off));

    const std::uint64_t barop = slot_value(inst, "barop").value_or(0);
    auto* st = mbarrier_at(cta, addr, /*create_if_missing=*/true);
    if (!st) {
        if (fault) {
            *fault = Fault(FaultKind::kIllegalMemoryAccess,
                           "ARRIVES at out-of-window shared address")
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    // Consume the sealed LDGSTS group's committed bytes (TRANSCNT).
    if (barop == 2) {  // TRANSCNT
        std::uint64_t group_bytes = 0;
        if (!cta.async_groups.empty()) {
            group_bytes = cta.async_groups.back().committed_bytes;
        } else if (cta.async_open.committed_bytes) {
            group_bytes = cta.async_open.committed_bytes;
        }
        if (group_bytes) {
            MbarrierResult r =
                mbarrier_arrive(st, 0, group_bytes, /*tx_is_complete=*/true);
            if (r.fault) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const std::uint64_t nw = st->encode();
            if (addr <= cta.shared.size() && addr + 8 <= cta.shared.size()) {
                for (int i = 0; i < 8; ++i)
                    cta.shared[addr + i] =
                        static_cast<std::uint8_t>((nw >> (8 * i)) & 0xff);
            }
        }
        return Status::success();
    }
    if (barop == 1) {  // ARVCNT (noinc arrive)
        // Arrive without incrementing: leave the arrival count unchanged, but
        // validate the barrier is initialized.
        MbarrierResult r = mbarrier_phasechk(*st, st->phase);
        if (r.fault) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        return Status::success();
    }
    // LEGACY: decode-only.
    if (fault) {
        *fault = Fault(FaultKind::kUnsupportedInstruction,
                       "ARRIVES.LDGSTSBAR.64.LEGACY is decode-only")
                     .set_pc(pc)
                     .set_warp(static_cast<std::uint32_t>(w.warp_id));
    }
    return Status::failure(Error::internal("memory fault"));
}

// High-4: warp-linear id across the whole launch.  ceil(block_threads/32) so
// a block smaller than 32 threads still gives each warp a distinct id (floor
// division collapsed every warp of such a block onto the same id).
std::uint64_t Interpreter::warp_linear_id(const WarpState& w) const {
    const std::uint64_t block_threads = static_cast<std::uint64_t>(
        env_.block[0]) * env_.block[1] * env_.block[2];
    const std::uint64_t warps_per_cta =
        (block_threads + kLanesPerWarp - 1) / kLanesPerWarp;
    return static_cast<std::uint64_t>(w.cta_id) * warps_per_cta +
           static_cast<std::uint64_t>(w.warp_id);
}

// ---------------------------------------------------------------------------
// Phase 9 subset: TMA family (UTMALDG / UTMASTG / UTMAREDG /
// UTMACMDFLUSH / UTMACCTL)
// ---------------------------------------------------------------------------
// UTMALDG: tensor load (global -> shared).  One elected thread issues it on
// the uniform datapath.  URb is the coordinate block:
//   {URb+0 = dst smem, URb+1 = mbarrier addr, URb+2 = coord[rank-1], ...,
//    last = coord[0]}  (2D verified; higher ranks follow ISRC_B_SIZE).
// URa = 64-bit pointer to the 128-byte tensor-map descriptor in global memory.
// The copy engine decrements the mbarrier's pending tx count by the tile
// bytes as data lands (complete_tx) — that flips the phase when drained.
//
// UTMASTG / UTMAREDG: tensor store / reduce (shared -> global).  URb block:
//   {URb+0 = shared src, URb+1 = coord[rank-1], ..., coord[0]} (no mbarrier).
// Completion is via the bulk-async-group (UTMACMDFLUSH + DEPBAR.LE).
//
// All are decode-only safe: an unparseable descriptor / im2col / swizzle tile
// faults as kNotSupported rather than fabricating a wrong copy.
Status Interpreter::do_tma(WarpState& w, const DecodedInstruction& inst,
                           std::uint64_t pc, std::optional<Fault>* fault) {
    const std::uint16_t op = semu::opcode_of(inst.word.lo, inst.word.hi);
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    const std::uint64_t warp_linear = warp_linear_id(w);

    // UTMACMDFLUSH (0x9b7): commit_group for the TMA bulk-async-group path.
    // Same counted-scoreboard bookkeeping as LDGDEPBAR (seal the open group on
    // the target SB).
    if (op == 0x9b7) {
        if (!cta.async_open.copies.empty() || cta.async_open.committed_bytes) {
            cta.async_groups.push_back(cta.async_open);
            const auto wr = slot_value(inst, "dst_wr_sb").value_or(0);
            if (wr < cta.sb_group_count.size()) cta.sb_group_count[wr]++;
            cta.async_open = {};
        }
        return Status::success();
    }
    // UTMACCTL (0x19b9 / 0x9b9): tensor-map descriptor cache control
    // (fence.proxy.tensormap / prefetch.tensormap).  The CPU model reads the
    // descriptor fresh from global every time, so invalidate/prefetch are
    // functional no-ops.
    if (op == 0x19b9 || op == 0x9b9) {
        return Status::success();
    }

    const Operand* urb = find_op(inst, "URb");
    const Operand* ura = find_op(inst, "URa");
    if (!urb || !ura) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "TMA op missing URb/URa operands")
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    const std::uint32_t urb_idx = static_cast<std::uint32_t>(urb->value);
    const std::uint64_t desc_ptr = read_ur_pair(w, *ura);

    // Read the 128-byte descriptor from global memory.
    std::uint8_t blob[128] = {0};
    {
        MemValue val{};
        for (std::uint32_t chunk = 0; chunk < 8; ++chunk) {
            Status st = memory_->ldg(DevicePtr{0}, desc_ptr + chunk * 16, 0,
                                     MemWidthInfo{16, false, true}, val);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(0xffffffffu);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            for (int i = 0; i < 4; ++i) {
                const std::uint32_t base = chunk * 16 + i * 4;
                blob[base] = static_cast<std::uint8_t>(val[i] & 0xff);
                blob[base + 1] = static_cast<std::uint8_t>((val[i] >> 8) & 0xff);
                blob[base + 2] = static_cast<std::uint8_t>((val[i] >> 16) & 0xff);
                blob[base + 3] = static_cast<std::uint8_t>((val[i] >> 24) & 0xff);
            }
        }
    }
    auto parsed = parse_tensor_map(blob);
    if (parsed.failed()) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "TMA tensor-map parse: " +
                               parsed.take_error().describe())
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    TensorMap tm = parsed.value();
    // im2col / packed-U4-U6 maps are decode-only (see tensor_map.hpp).
    if (tm.mode == TensorMapMode::kIm2col || tm.element_bytes == 0) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "im2col / packed tensor maps are decode-only")
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }

    // Read the coordinate block from URb.  UTMALDG (load): block starts with
    // {dst smem, mbarrier addr, coords...}.  UTMASTG/UTMAREDG (store):
    // {src smem, coords...} (no mbarrier slot).
    const bool is_load = (op == 0x15b4 || op == 0x13b4);
    const std::uint32_t coord_slot_offset = is_load ? 2 : 1;
    std::uint32_t coords[5] = {0, 0, 0, 0, 0};
    std::uint32_t smem_src = 0;   // store direction: shared source
    std::uint32_t dst_smem = 0;   // load direction: shared destination
    std::uint32_t mbar_addr = 0;
    if (is_load) {
        dst_smem = w.ur[urb_idx];
        mbar_addr = w.ur[urb_idx + 1];
    } else {
        smem_src = w.ur[urb_idx];
    }
    // SASS coordinate order: {coord[rank-1] .. coord[0]} (reversed vs PTX).
    for (std::uint32_t i = 0; i < tm.rank; ++i) {
        coords[tm.rank - 1 - i] = w.ur[urb_idx + coord_slot_offset + i];
    }

    auto expanded = expand_tile(tm, coords);
    if (expanded.failed()) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "TMA tile expansion: " +
                               expanded.take_error().describe())
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    TileAccessSet acc = expanded.value();

    if (is_load) {
        // UTMALDG: global -> shared.  Copy every element; the shared side is
        // contiguous (row-major box) starting at dst_smem.
        std::vector<LaneByteRange> shared_ranges;
        std::vector<LaneByteRange> global_ranges;
        for (std::size_t k = 0; k < acc.global.size(); ++k) {
            const std::uint64_t g = acc.global[k];
            const std::uint64_t s = dst_smem + acc.shared[k];
            MemValue val{};
            Status st = memory_->ldg(DevicePtr{0}, g, 0,
                                     MemWidthInfo{acc.element_bytes, false,
                                                  true},
                                     val);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(0xffffffffu);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            if (s > cta.shared.size() ||
                acc.element_bytes > cta.shared.size() - s) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "UTMALDG shared destination out of bounds")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            for (std::uint32_t i = 0; i < acc.element_bytes; ++i) {
                cta.shared[s + i] =
                    static_cast<std::uint8_t>((val[i / 4] >> (8 * (i % 4))) &
                                              0xff);
            }
        }
        // Completion: decrement the mbarrier's pending tx by the tile bytes
        // (cp.async.bulk.tensor ... mbarrier::complete_tx::bytes).
        if (mbar_addr != 0) {
            auto* st = mbarrier_at(cta, mbar_addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "UTMALDG mbarrier out of shared window")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const std::uint64_t tile_bytes =
                acc.global.size() * acc.element_bytes;
            MbarrierResult r =
                mbarrier_arrive(st, 0, tile_bytes, /*tx_is_complete=*/true);
            if (r.fault) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const std::uint64_t nw = st->encode();
            if (mbar_addr <= cta.shared.size() &&
                mbar_addr + 8 <= cta.shared.size()) {
                for (int i = 0; i < 8; ++i)
                    cta.shared[mbar_addr + i] =
                        static_cast<std::uint8_t>((nw >> (8 * i)) & 0xff);
            }
        }
        // Profiler / race observability: the committed access set.
        if (options_.model.l1tex == L1TexMode::kTraceOnly) {
            for (std::size_t k = 0; k < acc.global.size(); ++k) {
                if (k >= kLanesPerWarp) break;
                shared_ranges.push_back(
                    {dst_smem + acc.shared[k], acc.element_bytes, true});
                global_ranges.push_back({acc.global[k], acc.element_bytes, true});
            }
            MemoryEvent ev;
            ev.kind = MemoryEventKind::kL1TexIssue;
            ev.instruction = executed_;
            ev.cta = static_cast<std::uint32_t>(w.cta_id);
            ev.warp = static_cast<std::uint32_t>(w.warp_id);
            ev.pc = pc;
            ev.mnemonic = "UTMALDG";
            ev.request_kind = "tma-load";
            ev.element_width = acc.element_bytes;
            ev.address_space = EventAddressSpace::kShared;
            ev.is_write = true;
            ev.lane_ranges = shared_ranges;
            ev.subcore = subcore_mapper_.map(warp_linear).id;
            ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
            memory_events_.push_back(std::move(ev));
            MemoryEvent gev;
            gev.kind = MemoryEventKind::kL1TexIssue;
            gev.instruction = executed_;
            gev.cta = static_cast<std::uint32_t>(w.cta_id);
            gev.warp = static_cast<std::uint32_t>(w.warp_id);
            gev.pc = pc;
            gev.mnemonic = "UTMALDG";
            gev.request_kind = "tma-load-read";
            gev.element_width = acc.element_bytes;
            gev.address_space = EventAddressSpace::kGlobal;
            gev.is_write = false;
            gev.lane_ranges = global_ranges;
            gev.subcore = subcore_mapper_.map(warp_linear).id;
            gev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
            memory_events_.push_back(std::move(gev));
        }
        return Status::success();
    }

    // Store / reduce direction: shared -> global.
    // RedOp (UTMAREDG): Pnz [89:87].
    std::uint32_t redop = 0;
    if (op == 0x13b6) redop = static_cast<std::uint32_t>(
        slot_value(inst, "Pnz").value_or(0));
    std::vector<LaneByteRange> shared_ranges;
    std::vector<LaneByteRange> global_ranges;
    for (std::size_t k = 0; k < acc.global.size(); ++k) {
        const std::uint64_t g = acc.global[k];
        const std::uint64_t s = smem_src + acc.shared[k];
        if (s > cta.shared.size() || acc.element_bytes > cta.shared.size() - s) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "TMA store shared source out of bounds")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        MemValue src{};
        for (std::uint32_t i = 0; i < acc.element_bytes; ++i) {
            src[i / 4] |= static_cast<std::uint32_t>(cta.shared[s + i])
                          << (8 * (i % 4));
        }
        if (op == 0x13b6) {  // UTMAREDG: atomic reduce into global
            // The element type is u32 in the verified tests (the descriptor's
            // dtype drives it); a non-4-byte reduce is decode-only.
            if (acc.element_bytes != 4) {
                if (fault) {
                    *fault = Fault(
                        FaultKind::kUnsupportedInstruction,
                        "UTMAREDG element size != 4 is decode-only")
                            .set_pc(pc)
                            .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            AtomicOp aop = AtomicOp::kAdd;
            switch (redop) {
                case 0: aop = AtomicOp::kAdd; break;
                case 1: aop = AtomicOp::kMin; break;
                case 2: aop = AtomicOp::kMax; break;
                case 3: aop = AtomicOp::kInc; break;
                case 4: aop = AtomicOp::kDec; break;
                case 5: aop = AtomicOp::kAnd; break;
                case 6: aop = AtomicOp::kOr; break;
                case 7: aop = AtomicOp::kXor; break;
                default: break;
            }
            MemValue old{};
            Status st = memory_->atom_global(g, 4, aop, src, old);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(0xffffffffu);
                }
                return Status::failure(Error::internal("memory fault"));
            }
        } else {  // UTMASTG: plain store
            Status st = memory_->stg(DevicePtr{0}, g, 0,
                                     MemWidthInfo{acc.element_bytes, false,
                                                  true},
                                     src);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(0xffffffffu);
                }
                return Status::failure(Error::internal("memory fault"));
            }
        }
        if (k < kLanesPerWarp) {
            shared_ranges.push_back({s, acc.element_bytes, true});
            global_ranges.push_back({g, acc.element_bytes, true});
        }
    }
    // Profiler observability.
    if (options_.model.l1tex == L1TexMode::kTraceOnly) {
        MemoryEvent ev;
        ev.kind = MemoryEventKind::kL1TexIssue;
        ev.instruction = executed_;
        ev.cta = static_cast<std::uint32_t>(w.cta_id);
        ev.warp = static_cast<std::uint32_t>(w.warp_id);
        ev.pc = pc;
        ev.mnemonic = inst.mnemonic;
        ev.request_kind = "tma-store";
        ev.element_width = acc.element_bytes;
        ev.address_space = EventAddressSpace::kShared;
        ev.is_write = false;
        ev.lane_ranges = shared_ranges;
        ev.subcore = subcore_mapper_.map(warp_linear).id;
        ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        memory_events_.push_back(std::move(ev));
        MemoryEvent gev;
        gev.kind = MemoryEventKind::kL1TexIssue;
        gev.instruction = executed_;
        gev.cta = static_cast<std::uint32_t>(w.cta_id);
        gev.warp = static_cast<std::uint32_t>(w.warp_id);
        gev.pc = pc;
        gev.mnemonic = inst.mnemonic;
        gev.request_kind = "tma-store-write";
        gev.element_width = acc.element_bytes;
        gev.address_space = EventAddressSpace::kGlobal;
        gev.is_write = true;
        gev.lane_ranges = global_ranges;
        gev.subcore = subcore_mapper_.map(warp_linear).id;
        gev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        memory_events_.push_back(std::move(gev));
    }
    return Status::success();
}

// Phase 6 Step 2B: trace-only subcore issue event.  Records the warp's stable

// Phase 6 Step 2B: trace-only subcore issue event.  Records the warp's stable
// subcore mapping + issue sequence.  Ordinary LDG/STG/LDS/STS/atomic/constant
// requests NEVER feed the UnifiedV1 estimator (it models the coupled
// L1-read -> shared-write transfer only); that path goes through
// record_coupled_l1_to_shared.
void Interpreter::record_memory_event(const WarpState& w,
                                      const DecodedInstruction& inst,
                                      std::uint64_t pc, std::uint32_t mask,
                                      const std::string& request_kind,
                                      std::uint32_t element_width,
                                      AddressSpace space, bool is_write,
                                      const std::vector<LaneByteRange>& lane_ranges,
                                      std::uint32_t committed_mask) {
    if (options_.model.l1tex == L1TexMode::kOff) return;
    const std::uint64_t warp_linear = warp_linear_id(w);
    SubcoreIssueResult ir = issue_on_subcore(l1tex_state_, subcore_mapper_,
                                             warp_linear);
    MemoryEvent ev;
    ev.kind = MemoryEventKind::kL1TexIssue;
    ev.event_id = ir.event_id;
    ev.instruction = executed_;
    ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
    ev.subcore = ir.subcore.id;
    ev.cta = static_cast<std::uint32_t>(w.cta_id);
    ev.warp = static_cast<std::uint32_t>(w.warp_id);
    ev.active_mask = committed_mask != 0 ? committed_mask : mask;
    ev.pc = pc;
    ev.mnemonic = inst.mnemonic;
    ev.request_kind = request_kind;
    ev.element_width = element_width;
    ev.issue_tick = ir.issue_tick;
    // No prediction on the ordinary path.
    ev.coupled_l1_to_shared = false;
    ev.prediction = false;
    // Phase 8 refinement: stable variant class + cache-policy contract.  The
    // ordinary LDG/STG/LDS/STS/atomic path always allocates through L1.
    ev.variant_class = inst.variant_class;
    ev.cache_policy = "default";
    ev.miss_path = "l1-access";
    // Phase 8 backend-neutral raw access stream.
    ev.address_space =
        space == AddressSpace::kShared ? EventAddressSpace::kShared
        : space == AddressSpace::kConstant ? EventAddressSpace::kConstant
        : space == AddressSpace::kLocal ? EventAddressSpace::kLocal
                                        : EventAddressSpace::kGlobal;
    ev.is_write = is_write;
    ev.lane_ranges = lane_ranges;
    memory_events_.push_back(std::move(ev));
}

// Phase 6 Step 2B (Blocker-4): a REAL coupled L1->shared transfer (LDGSTS /
// cp.async) carries the UnifiedV1 prediction.  The interpreter computes the
// per-lane global (goff) and shared (soff) byte offsets, the active mask and
// the element width, calls the estimator, and emits the prediction plus the
// per-token service decomposition.  Trace-only.
void Interpreter::record_coupled_l1_to_shared(const WarpState& w,
                                              const DecodedInstruction& inst,
                                              std::uint64_t pc,
                                              std::uint32_t mask,
                                              const std::uint32_t goff[32],
                                              const std::uint32_t soff[32],
                                              std::uint32_t element_width,
                                              bool prediction_unavailable) {
    if (options_.model.l1tex == L1TexMode::kOff) return;
    const std::uint64_t warp_linear = warp_linear_id(w);
    SubcoreIssueResult ir = issue_on_subcore(l1tex_state_, subcore_mapper_,
                                             warp_linear);
    MemoryEvent ev;
    ev.kind = MemoryEventKind::kL1TexIssue;
    ev.event_id = ir.event_id;
    ev.instruction = executed_;
    ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
    ev.subcore = ir.subcore.id;
    ev.cta = static_cast<std::uint32_t>(w.cta_id);
    ev.warp = static_cast<std::uint32_t>(w.warp_id);
    ev.active_mask = mask;
    ev.pc = pc;
    ev.mnemonic = inst.mnemonic;
    ev.request_kind = "coupled";
    ev.element_width = element_width;
    ev.issue_tick = ir.issue_tick;
    ev.coupled_l1_to_shared = true;
    // Phase 8 refinement: the LDGSTS cache-policy contract.  The `loc` FORMAT
    // slot discriminates LOC@ACCESS (default, L1 allocate) from LOC@BYPASS
    // (the .cg / L1-bypass path).  The estimator honors it: "cg" marks the
    // SharedWf / conflict counters unsupported on the profiler path.
    ev.variant_class = inst.variant_class;
    const bool l1_bypass = slot_value(inst, "loc").value_or(1) == 0;
    ev.cache_policy = l1_bypass ? "cg" : "default";
    ev.miss_path = l1_bypass ? "l1-bypass" : "l1-access";
    // High-2: an address-computation failure (silent-wrap-guard tripped) makes
    // the prediction explicitly unavailable — the estimate covers only the
    // VALID lanes and never fabricates a zero offset for the failed lane.
    ev.prediction = !prediction_unavailable;
    ev.model_version = semu::l1tex::kUnifiedModelVersion;
    // Phase 8: expose the raw per-lane source/dest offsets so the profiler
    // recomputes the extended counters (TWf/Sectors/TagConf/TSetAcc/SharedConf/
    // GlobalConf) without re-execution.
    for (int l = 0; l < 32; ++l) {
        ev.ldgsts_goff.push_back(goff[l]);
        ev.ldgsts_soff.push_back(soff[l]);
    }

    if (ev.prediction) {
        semu::l1tex::UnifiedV1Estimator est;
        semu::l1tex::UnifiedEstimate r = est.estimate(goff, soff,
                                                      static_cast<int>(element_width),
                                                      mask);
        ev.predicted_shared_wf = r.shared_wf;
        for (const auto& ts : r.token_stats) {
            TokenServiceEvent t;
            t.token_id = static_cast<std::uint64_t>(ts.token);
            t.active_lanes = static_cast<std::uint32_t>(ts.lanes);
            t.read_wf = ts.read_wf;
            t.write_wf = ts.write_wf;
            t.overlap_wf = ts.overlap_wf;
            t.shared_wf = ts.shared_wf;
            ev.tokens.push_back(t);
        }
    }
    memory_events_.push_back(std::move(ev));
}

// Phase 6 Step 2C: trace-only L2 access for a global byte range.  Workers do
// NOT touch the L2 engine here (High-2): a shared engine's request/completion/
// event ids and same-sector insertion order would depend on host thread
// scheduling (mutex acquisition order).  Instead a stable per-lane request
// DESCRIPTOR is appended to l2_log_ with a per-CTA ordinal; after all workers
// join, run_result_parallel sorts the merged descriptors by (cta, ordinal,
// lane) and drives a single-threaded launch-level engine to assign ids and the
// seed schedule.  Never changes functional values.
void Interpreter::record_l2_access(const WarpState& w,
                                   const DecodedInstruction& inst,
                                   std::uint64_t pc, std::uint32_t mask,
                                   const std::string& request_kind,
                                   AddressSpace space, std::uint64_t addr,
                                   std::uint64_t len, std::uint32_t lane) {
    (void)mask;
    if (!l2_engine_enabled_ || !l2_engine_ ||
        space != AddressSpace::kGlobal) {
        return;
    }
    const std::uint32_t cta = static_cast<std::uint32_t>(w.cta_id);
    L2RequestDescriptor d;
    d.cta = cta;
    d.sm = sm_of_cta(cta);
    d.subcore = subcore_mapper_.map(warp_linear_id(w)).id;
    d.warp = static_cast<std::uint32_t>(w.warp_id);
    d.lane = lane;
    d.ordinal = l2_ordinal_[cta]++;
    d.pc = pc;
    d.mnemonic = inst.mnemonic;
    d.request_kind = request_kind;
    d.addr = addr;
    d.len = len;
    l2_log_.push_back(std::move(d));
}

// Append any pending L2 events (requests + completions) to memory_events_
// (trace-only).  A worker on a SHARED engine does not drain (that would
// consume other workers' in-flight requests); the launch drains once after
// all workers join.  For an OWNED engine (single worker) the buffered
// descriptors are sorted and replayed through the engine first, so the trace
// is identical to the parallel path's deterministic (cta, ordinal, lane)
// order.
void Interpreter::flush_l2_events() {
    if (!l2_engine_ || l2_engine_shared_) return;
    std::sort(l2_log_.begin(), l2_log_.end(),
              [](const L2RequestDescriptor& a, const L2RequestDescriptor& b) {
                  if (a.cta != b.cta) return a.cta < b.cta;
                  if (a.ordinal != b.ordinal) return a.ordinal < b.ordinal;
                  return a.lane < b.lane;
              });
    for (const auto& d : l2_log_) {
        l2_engine_->issue_global(d.sm, d.subcore, d.cta, d.warp, d.pc,
                                 d.ordinal, 0, d.mnemonic, d.request_kind,
                                 d.addr, d.len);
    }
    l2_log_.clear();
    l2_engine_->drain_completions();
    for (auto& ev : l2_engine_->events()) {
        memory_events_.push_back(std::move(ev));
    }
    l2_engine_->events().clear();
}

// Phase 6 Step 2D: record a shared/global access in the race detector.
// Trace-only: never changes functional values, scoreboard, atomic
// linearization or happens-before edges.  Atomic accesses are buffered as
// kAtomic events so the replay dispatches them through atomic_rmw (release/
// acquire clock bookkeeping), plain accesses as kObserve.
void Interpreter::record_race_access(const WarpState& w,
                                     const DecodedInstruction& inst,
                                     std::uint64_t pc, std::uint32_t lane,
                                     AddressSpace space, std::uint64_t addr,
                                     std::uint64_t len, bool is_write,
                                     bool is_atomic,
                                     const std::string& mem_order,
                                     const std::string& scope) {
    if (!race_detector_ || !race_detector_->enabled()) return;
    RaceAccess a;
    a.instruction = executed_;
    a.pc = pc;
    a.mnemonic = inst.mnemonic;
    a.space = space;
    a.cta = static_cast<std::uint32_t>(w.cta_id);
    a.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
    a.warp = static_cast<std::uint32_t>(w.warp_id);
    a.lane = lane;
    a.byte_begin = addr;
    a.byte_end = addr + len;
    a.is_write = is_write;
    a.is_atomic = is_atomic;
    a.atomic_op = is_atomic ? inst.mnemonic : "";
    a.mem_order = mem_order;
    a.scope = scope;
    a.order_scope_ok = classify_order_scope(mem_order, scope);
    if (space == AddressSpace::kGlobal && memory_) {
        a.alloc_id = memory_->global_allocation_id();
        a.generation = 0;
    }
    // Buffer the event; the run result replays the log into the detector in
    // deterministic (cta, ordinal) order (see replay_race_log).
    RaceEvent ev;
    ev.kind = is_atomic ? RaceEvent::kAtomic : RaceEvent::kObserve;
    ev.cta = a.cta;
    ev.sm = a.sm;
    ev.ordinal = race_ordinal_[a.cta]++;
    ev.access = std::move(a);
    race_log_.push_back(std::move(ev));
}

// Phase 7: capture one committed lane memory access for the current debug
// step (no-op unless a step_group is running with debug capture on).  Calls
// sit at exactly the same commit points as record_race_access, so the
// debugger's memory events match the real effects (faulting accesses never
// appear).
void Interpreter::record_debug_access(const WarpState& w, std::uint32_t lane,
                                      AddressSpace space, std::uint64_t addr,
                                      std::uint64_t len, bool is_write,
                                      bool is_atomic) {
    (void)w;
    if (!debug_capture_) return;
    StepMemAccess a;
    a.lane = lane;
    a.space = space;
    a.address = addr;
    a.width = len;
    a.write = is_write;
    a.atomic = is_atomic;
    debug_step_accesses_.push_back(std::move(a));
}

// Phase 7: the interpreter's implemented mnemonic set.  The debugger consults
// this BEFORE executing a group so a decode-only instruction stops with state
// intact instead of faulting through the PC-advance.  (Value/state-dependent
// fault triggers — an unsupported S2R special register, a BSYNC with no
// matching BSSY, an unrecognized atomic op — stay at runtime and surface as a
// StepInfo fault.)
bool Interpreter::supports(const DecodedInstruction& inst) const {
    const std::string& m = inst.mnemonic;
    // Control flow (do_bra / do_bssy / do_bsync / do_exit / do_s2r / do_s2ur /
    // do_bar / NOP).
    if (m == "BRA" || m == "BRX" || m == "JMP" || m == "JMX" ||
        m == "BSSY" || m == "BSYNC" || m == "EXIT" || m == "S2R" ||
        m == "S2UR" || m == "BAR" || m == "NOP") {
        return true;
    }
    // Minimal ALU (do_mov / do_iadd3 / do_isetp / do_imad).  IMAD covers
    // the .WIDE / .HI / .X / imm / uniform variants (same mnemonic).
    if (m == "MOV" || m == "IADD3" || m == "ISETP" || m == "IMAD") {
        return true;
    }
    // Phase 6 memory (do_memory).  LDGSTS is now functional (cp.async).
    if (m == "LDG" || m == "STG" || m == "LDS" || m == "STS" ||
        m == "LDC" || m == "LDCU" || m == "LDL" || m == "STL" ||
        m == "ATOM" || m == "ATOMS" || m == "RED" || m == "REDS" ||
        m == "ATOMG" || m == "REDG" || m == "MEMBAR" || m == "FENCE" ||
        m == "ERRBAR" || m == "CGAERRBAR" || m == "CCTL" ||
        m == "DEPBAR" || m == "LDGDEPBAR" || m == "LDGSTS") {
        return true;
    }
    // Phase 9 subset: mbarrier (SYNCS), cp.async.mbarrier.arrive (ARRIVES)
    // and the TMA family (UTMALDG / UTMASTG / UTMAREDG / UTMACMDFLUSH /
    // UTMACCTL).
    if (m == "SYNCS" || m == "ARRIVES" || m == "UTMALDG" ||
        m == "UTMASTG" || m == "UTMAREDG" || m == "UTMACMDFLUSH" ||
        m == "UTMACCTL") {
        return true;
    }
    // Phase 9 tensor core: HMMA / QMMA / OMMA dense F32-accumulator shapes
    // (do_tensor).  Sparse/rowcol/scale alternatives and the F16 accumulator
    // fault at runtime (do_tensor dispatches on the decoded variant class /
    // modifier slots).
    if (m == "HMMA" || m == "QMMA" || m == "OMMA") {
        return true;
    }
    // Phase 5 compute (do_compute).
    if (m == "FADD" || m == "FMUL" || m == "FFMA" || m == "DADD" ||
        m == "DMUL" || m == "DFMA" || m == "FSETP" || m == "FSET" ||
        m == "FMNMX" || m == "FSEL" || m == "F2F" || m == "I2F" ||
        m == "F2I" || m == "FRND" || m == "P2R" || m == "VOTE" ||
        m == "ELECT" || m == "REDUX" || m == "SHFL" || m == "LOP3" ||
        m == "LOP" || m == "SHF" || m == "IABS" || m == "IMNMX" ||
        m == "ISCADD" || m == "LEA" || m == "POPC" || m == "FLO" ||
        m == "BFE" || m == "BMSK" || m == "BFREV" || m == "PRMT") {
        return true;
    }
    return false;
}

// Phase 7: S2R/S2UR special-register view (same resolve_sr the interpreter
// uses for the lane).  Returns 0 for unknown registers.
std::uint32_t Interpreter::special_register_value(SpecialReg sr,
                                                  std::uint32_t cta_id,
                                                  std::uint32_t warp_id,
                                                  int lane) const {
    return resolve_sr(sr, lane, static_cast<int>(warp_id),
                      static_cast<int>(cta_id), env_);
}

// Phase 9 tensor core: HMMA / QMMA / OMMA (dense F32-accumulator shapes).
//
// Functional semantics is delegated to semu::tensor (the C++ port of
// tools/hmma_model.py), so the interpreter result equals the Python model
// bit-for-bit by construction.  Per lane the handler reads the lane's own
// fragment registers (consecutive words from each base operand), folds the
// k-products via the engine's fragment functions and writes the 4 F32
// accumulator words to Rd..Rd+3.
//
// Hardware contract: HMMA/QMMA/OMMA results are NOT scoreboarded on the
// tensor pipe (INST_TYPE_COUPLED_MATH).  A D read closer than ~16 instructions
// after the MMA faults 0x715 on SM120; the interpreter is synchronous, so it
// does not need the padding itself, but hand-written tests keep the NOPs to
// stay faithful to the hardware contract (see AGENTS.md / ASSEMBLER_MANUAL.md).
Status Interpreter::do_tensor(WarpState& w, std::uint32_t mask,
                              const DecodedInstruction& inst, std::uint64_t pc,
                              std::optional<Fault>* fault) {
    const std::string& m = inst.mnemonic;
    const Operand* rd = find_op(inst, "Rd");
    if (!rd || rd->kind != "Register") {
        *fault = Fault(FaultKind::kInternal, "tensor op missing Rd")
                     .set_pc(pc)
                     .set_warp(static_cast<std::uint32_t>(w.warp_id))
                     .set_active_mask(mask)
                     .set_instruction(inst.word);
        return Status::failure(Error::internal("tensor op missing Rd"));
    }

    // Resolve the shape + source format for this instruction.
    tensor::Shape shape;
    tensor::Format fmt = tensor::Format::kBf16;
    bool need_uri = false;

    const std::string& cls = inst.variant_class;
    const auto unsupported =
        [&](const std::string& why) -> Status {
            Fault f(FaultKind::kUnsupportedInstruction,
                    "instruction '" + m + "' (" + cls + ") " + why +
                        " is decode-only (not implemented) at pc 0x" +
                        std::to_string(pc));
            f.set_warp(static_cast<std::uint32_t>(w.warp_id))
                .set_pc(pc)
                .set_active_mask(mask)
                .set_instruction(inst.word);
            if (fault) *fault = std::move(f);
            return Status::failure(Error::internal("interpreter fault"));
        };

    if (m == "HMMA") {
        // Dense HMMA (hmma_x8_): size 0=k8 / 1=k16 / 2=k4(TF32), srcfmt
        // 0=F16 1=BF16 2=TF32 3=E6M9, dstfmt 0=F16 1=F32 accumulator.
        if (cls != "hmma_x8_") return unsupported("(sparse/indexedRF variant)");
        const std::uint64_t size = slot_value(inst, "size").value_or(0);
        const std::uint64_t srcfmt = slot_value(inst, "srcfmt").value_or(0);
        const std::uint64_t dstfmt = slot_value(inst, "dstfmt").value_or(0);
        if (dstfmt != 1) return unsupported("(F16 accumulator)");
        if (srcfmt > 1) return unsupported("(TF32/E6M9 source)");
        if (!tensor::hmma_shape(static_cast<int>(size),
                                static_cast<int>(srcfmt), &shape)) {
            return unsupported("(shape)");
        }
        fmt = (srcfmt == 1) ? tensor::Format::kBf16 : tensor::Format::kF16;
    } else if (m == "QMMA") {
        // Dense QMMA (qmma_): size 0=k16 / 1=k32, dstfmt(ntz) 0=F16 1=F32.
        if (cls != "qmma_") return unsupported("(sparse/rowcol/scale variant)");
        const std::uint64_t size = slot_value(inst, "size").value_or(0);
        const std::uint64_t dstfmt = slot_value(inst, "dstfmt").value_or(0);
        if (dstfmt != 1) return unsupported("(F16 accumulator)");
        const std::uint64_t sfa = slot_value(inst, "srcFmtA").value_or(0);
        if (!tensor::qmma_shape(static_cast<int>(size), &shape)) {
            return unsupported("(shape)");
        }
        // Probed SM120 srcFmt mapping (AGENTS.md): E4M3=0 E3M4=1 E2M3=2
        // E5M2=4 E3M2=5 E2M1=6.
        switch (sfa) {
            case 0: fmt = tensor::Format::kFp8E4M3; break;
            case 1: fmt = tensor::Format::kFp8E3M4; break;
            case 2: fmt = tensor::Format::kFp8E2M3; break;
            case 4: fmt = tensor::Format::kFp8E5M2; break;
            case 5: fmt = tensor::Format::kFp8E3M2; break;
            case 6: fmt = tensor::Format::kFp8E2M1; break;
            default: return unsupported("(srcFmtA)");
        }
    } else {  // OMMA.SF (mxfp4 block-scaled)
        if (cls != "omma_scale_") return unsupported("(sparse/scale variant)");
        // Only the verified 2X-scale E8 e2m1 configuration is implemented.
        const std::uint64_t sf = slot_value(inst, "scalefmt").value_or(0);
        const std::uint64_t ssz = slot_value(inst, "scaleVectorSz").value_or(1);
        const std::uint64_t sfa = slot_value(inst, "srcFmtA").value_or(0);
        const std::uint64_t sfb = slot_value(inst, "srcFmtB").value_or(0);
        if (sf != 0) return unsupported("(non-E8 scale)");
        if (ssz != 1) return unsupported("(4X scale vector)");
        if (sfa != 0 || sfb != 0) return unsupported("(E0M3 source)");
        if (!tensor::omma_shape(&shape)) return unsupported("(shape)");
        need_uri = true;
        fmt = tensor::Format::kFp8E4M3;  // unused for gdfs; kept for symmetry
    }

    const Operand* ra = find_op(inst, "Ra");
    const Operand* rb = find_op(inst, "Rb");
    const Operand* rc = find_op(inst, "Rc");
    const Operand* re_op = find_op(inst, "Re");
    const Operand* rh_op = find_op(inst, "Rh");
    const Operand* uri_op = find_op(inst, "URi");
    if (!ra || !rb || !rc || !rd) {
        return unsupported("(operands)");
    }

    // OMMA selection register: only sel=0 is verified legal on SM120.
    if (need_uri) {
        std::uint32_t sel = 0;
        if (uri_op) sel = read_ur_val(w, *uri_op);
        if (sel != 0) {
            Fault f(FaultKind::kUnsupportedInstruction,
                    "OMMA.SF selector URi != 0 is decode-only (only sel=0 is "
                    "verified legal on SM120)");
            f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc)
                .set_active_mask(mask).set_instruction(inst.word);
            if (fault) *fault = std::move(f);
            return Status::failure(Error::internal("interpreter fault"));
        }
    }

    // Fragment register base indices (RZ reads as 0; base + width must stay in
    // range per the CONDITIONS — a misaligned/overflowing group already
    // decodes as OOR_REG_ERROR / MISALIGNED_REG_ERROR in the decoder).
    const int rd_base = rd->kind == "Register" ? static_cast<int>(rd->value) : 0;
    const int ra_base = ra->kind == "Register" ? static_cast<int>(ra->value) : 0;
    const int rb_base = rb->kind == "Register" ? static_cast<int>(rb->value) : 0;
    const int rc_base = rc->kind == "Register" ? static_cast<int>(rc->value) : 0;

    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;

        std::uint32_t a[8] = {0}, b[4] = {0}, c[4] = {0};
        for (int i = 0; i < shape.regs_a; ++i) {
            const int r = ra_base + i;
            a[i] = (ra_base == 255 || r >= kNumGprs) ? 0 : t.gpr[r];
        }
        for (int i = 0; i < shape.regs_b; ++i) {
            const int r = rb_base + i;
            b[i] = (rb_base == 255 || r >= kNumGprs) ? 0 : t.gpr[r];
        }
        for (int i = 0; i < shape.regs_c; ++i) {
            const int r = rc_base + i;
            c[i] = (rc_base == 255 || r >= kNumGprs) ? 0 : t.gpr[r];
        }

        std::uint32_t out[4] = {0};
        if (m == "HMMA") {
            if (shape.k == 16) {
                tensor::hmma_k16(a, b, c, fmt, out);
            } else {
                tensor::hmma_k8(a, b, c, fmt, out);
            }
        } else if (m == "QMMA") {
            if (shape.k == 32) {
                tensor::qmma_k32(a, b, c, fmt, out);
            } else {
                tensor::qmma_k16(a, b, c, fmt, out);
            }
        } else {
            if (!re_op || !rh_op) return unsupported("(missing Re/Rh)");
            std::uint32_t re = read_reg_val(t, *re_op);
            std::uint32_t rh = read_reg_val(t, *rh_op);
            const std::uint32_t sel = 0;  // validated above
            tensor::omma_k64(a, b, c, re, rh, sel, out);
        }

        for (int i = 0; i < 4; ++i) {
            const int r = rd_base + i;
            if (rd_base == 255 || r >= kNumGprs) break;  // RZ dest: discard
            t.gpr[r] = out[i];
        }
    }
    return Status::success();
}

Status Interpreter::do_compute(WarpState& w, std::uint32_t mask,
                               const DecodedInstruction& inst,
                               std::uint64_t pc,
                               std::optional<Fault>* fault) {
    const std::string& m = inst.mnemonic;
    const Operand* rd = find_op(inst, "Rd");

    // ---- FP32 add/mul/fma -----------------------------------------------
    if (m == "FADD" || m == "FMUL" || m == "FFMA") {
        const Rnd rnd = static_cast<Rnd>(slot_value(inst, "rnd").value_or(0));
        // FADD uses `ftz`; FMUL/FFMA use `fmz` (FMZ_hfma2: FMZ=1, FTZ=2).
        const bool flush = m == "FADD"
            ? slot_value(inst, "ftz").value_or(0) != 0
            : slot_value(inst, "fmz").value_or(0) != 0;
        const bool sat = slot_value(inst, "sat").value_or(0) != 0;
        if (!rd) return Status::success();
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* rc = find_op(inst, "Rc");
        const Operand* sc = find_op(inst, "Sc");  // RRI immediate addend
        const Operand* sb = find_op(inst, "Sb");  // RIR immediate mult-add
        const int op = m == "FADD" ? 0 : m == "FMUL" ? 1 : 2;
        // Phase 5.5: resolve the leaf policy once per instruction (M5).
        const Fp32Plan plan = plan_fp32(op, static_cast<int>(rnd), flush);
        // M5 pre-binding: resolve each source operand's register index /
        // immediate value once so the per-lane loop does no string compares.
        const Operand* second = (m == "FADD") ? rc : rb;
        const int ra_r = bind_reg_index(ra);
        const int second_r = bind_reg_index(second);
        const int rc_r = bind_reg_index(rc);
        const bool sb_imm = sb && (sb->kind == "UImm" || sb->kind == "SImm");
        const bool sc_imm = sc && (sc->kind == "UImm" || sc->kind == "SImm");
        const std::uint32_t sb_v = sb_imm ? static_cast<std::uint32_t>(sb->value) : 0;
        const std::uint32_t sc_v = sc_imm ? static_cast<std::uint32_t>(sc->value) : 0;
        const bool ra_abs = ra && ra->absolute, ra_neg = ra && ra->negated;
        const bool sb_abs = second && second->absolute, sb_neg = second && second->negated;
        const bool rc_abs = rc && rc->absolute, rc_neg = rc && rc->negated;
        const int rd_idx = bind_reg_index(rd);
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = read_bound(t, ra_r, ra_abs, ra_neg);
            std::uint32_t b = read_bound(t, second_r, sb_abs, sb_neg);
            if (second_r < 0 && sb_imm) b = sb_v;
            std::uint32_t c = read_bound(t, rc_r, rc_abs, rc_neg);
            if (rc_r < 0 && sc_imm) c = sc_v;
            bool use_fast = plan.use_fast;
            if (plan.need_exceptional &&
                (exceptional_f32(a) || exceptional_f32(b) ||
                 exceptional_f32(c))) {
                use_fast = false;
            }
            std::uint32_t out;
            if (use_fast) {
                if (plan.ignored_modifier) ++fast_stats_.ignored_modifier_ops;
                switch (op) {
                    case 0: out = fp::fast_fadd(a, b, static_cast<int>(rnd), flush, sat); break;
                    case 1: out = fp::fast_fmul(a, b, static_cast<int>(rnd), flush, sat); break;
                    default: out = fp::fast_ffma(a, b, c, static_cast<int>(rnd), flush, sat); break;
                }
                // Phase 5.5 High-2: kExceptional also falls back when the
                // NATIVE RESULT is exceptional, even if all inputs were
                // finite (e.g. overflow to Inf).  The input check above only
                // caught exceptional operands; recompute with the precise
                // helper here so the fallback policy is honored.
                if (plan.need_exceptional && exceptional_f32(out)) {
                    ++fast_stats_.precise_fallback_ops;
                    switch (op) {
                        case 0: out = fp::fadd(a, b, rnd, flush, sat); break;
                        case 1: out = fp::fmul(a, b, rnd, flush, sat); break;
                        default: out = fp::ffma(a, b, c, rnd, flush, sat); break;
                    }
                } else {
                    note_fast_leaf(true);
                }
            } else {
                if (fast_mode()) ++fast_stats_.precise_fallback_ops;
                switch (op) {
                    case 0: out = fp::fadd(a, b, rnd, flush, sat); break;
                    case 1: out = fp::fmul(a, b, rnd, flush, sat); break;
                    default: out = fp::ffma(a, b, c, rnd, flush, sat); break;
                }
            }
            if (rd_idx >= 0) t.gpr[rd_idx] = out;
        }
        return Status::success();
    }

    // ---- FP64 add/mul/fma -----------------------------------------------
    if (m == "DADD" || m == "DMUL" || m == "DFMA") {
        const Rnd rnd = static_cast<Rnd>(slot_value(inst, "rnd").value_or(0));
        const bool sat = slot_value(inst, "sat").value_or(0) != 0;
        const bool ftz = slot_value(inst, "ftz").value_or(0) != 0;
        if (!rd) return Status::success();
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* rc = find_op(inst, "Rc");
        const int op = m == "DADD" ? 0 : m == "DMUL" ? 1 : 2;
        // Phase 5.5: resolve the leaf policy once per instruction (M5).
        const Fp64Plan plan = plan_fp64(op, static_cast<int>(rnd));
        // M5 pre-binding: pair base indices resolved once (2nd source = Rb,
        // else Rc for DADD which has no Rb).
        const int ra_r = bind_reg_index(ra);
        const int rc_r = bind_reg_index(rc);
        const int sb_r = bind_reg_index(rb ? rb : rc);
        const int rd_r = bind_reg_index(rd);
        auto read_pair_at = [](const ThreadState& t, int idx) -> std::uint64_t {
            if (idx < 0 || idx >= kNumGprs - 1) return 0;
            std::uint64_t lo = t.gpr[idx];
            std::uint64_t hi = t.gpr[idx + 1];
            return lo | (hi << 32);
        };
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            const std::uint64_t a = read_pair_at(t, ra_r);
            const std::uint64_t b = read_pair_at(t, sb_r);
            const std::uint64_t c = read_pair_at(t, rc_r);
            bool use_fast = plan.use_fast;
            if (plan.need_exceptional &&
                (exceptional_f64(a) || exceptional_f64(b) ||
                 exceptional_f64(c))) {
                use_fast = false;
            }
            std::uint64_t out;
            if (use_fast) {
                if (plan.ignored_modifier) ++fast_stats_.ignored_modifier_ops;
                switch (op) {
                    case 0: out = fp::fast_fadd64(a, b, static_cast<int>(rnd), sat); break;
                    case 1: out = fp::fast_fmul64(a, b, static_cast<int>(rnd), sat); break;
                    default: out = fp::fast_fma64(a, b, c, static_cast<int>(rnd), sat); break;
                }
                // Phase 5.5 High-2: kExceptional also falls back on an
                // exceptional NATIVE RESULT (overflow -> Inf) even when all
                // inputs were finite.
                if (plan.need_exceptional && exceptional_f64(out)) {
                    ++fast_stats_.precise_fallback_ops;
                    switch (op) {
                        case 0: out = fp::fadd64(a, b, rnd, sat); break;
                        case 1: out = fp::fmul64(a, b, rnd, sat); break;
                        default: out = fp::fma64(a, b, c, rnd, sat); break;
                    }
                } else {
                    note_fast_leaf(true);
                }
            } else {
                if (fast_mode()) ++fast_stats_.precise_fallback_ops;
                switch (op) {
                    case 0: out = fp::fadd64(a, b, rnd, sat); break;
                    case 1: out = fp::fmul64(a, b, rnd, sat); break;
                    default: out = fp::fma64(a, b, c, rnd, sat); break;
                }
            }
            (void)ftz;
            if (rd_r >= 0 && rd_r < kNumGprs - 1) {
                t.gpr[rd_r] = static_cast<std::uint32_t>(out & 0xffffffffu);
                t.gpr[rd_r + 1] = static_cast<std::uint32_t>(out >> 32);
            }
        }
        return Status::success();
    }

    // ---- FP compares / min-max / select / round --------------------------
    if (m == "FSETP" || m == "FSET") {
        // FSETP Pu, Pv, Ra, Rb/Sb, Pp  (bop combines with Pp)
        // FSET  Rd, Ra, Rb/Sb, Pp       (Rd = 0x3f800000 or 0)
        const std::uint64_t fcomp = slot_value(inst, "fcomp").value_or(0);
        const std::uint64_t bop = slot_value(inst, "bop").value_or(0);
        const bool ftz = slot_value(inst, "ftz").value_or(0) != 0;
        const Operand* pu = find_op(inst, "Pu");
        const Operand* pv = find_op(inst, "Pv");
        const Operand* pp = find_op(inst, "Pp");
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* sb = find_op(inst, "Sb");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            std::uint32_t b = rb ? read_reg_val(t, *rb)
                : (sb && (sb->kind == "UImm" || sb->kind == "SImm"))
                    ? static_cast<std::uint32_t>(sb->value)
                    : 0;
            if (ftz) {
                if (fast_mode()) {
                    // Phase 5.5: kNone skips the subnormal flush and counts
                    // an ignored modifier; other policies fall back to the
                    // precise flush.
                    if (options_.fast_fp_fallback != FastFpFallback::kNone) {
                        ++fast_stats_.precise_fallback_ops;
                        a = fp::flush_f32(a);
                        b = fp::flush_f32(b);
                    } else {
                        ++fast_stats_.ignored_modifier_ops;
                    }
                } else {
                    a = fp::flush_f32(a);
                    b = fp::flush_f32(b);
                }
            }
            const float fa = std::bit_cast<float>(a);
            const float fb = std::bit_cast<float>(b);
            const bool anan = std::isnan(fa);
            const bool bnan = std::isnan(fb);
            bool r = false;
            switch (fcomp) {
                case 0:  r = false; break;                                   // F
                case 1:  r = !anan && !bnan && fa < fb; break;               // LT
                case 2:  r = !anan && !bnan && fa == fb; break;              // EQ
                case 3:  r = !anan && !bnan && fa <= fb; break;              // LE
                case 4:  r = !anan && !bnan && fa > fb; break;               // GT
                case 5:  r = !anan && !bnan && fa != fb; break;              // NE
                case 6:  r = !anan && !bnan && fa >= fb; break;              // GE
                case 7:  r = !anan && !bnan; break;                          // NUM
                case 8:  r = anan || bnan; break;                            // NAN
                // U-variants are unordered-true: true when either operand
                // is NaN (verified on sm120: every FSETP.*U(1.0, NaN) -> 1).
                case 9:  r = anan || bnan || fa < fb; break;                  // LTU
                case 10: r = anan || bnan || fa == fb; break;                 // EQU
                case 11: r = anan || bnan || fa <= fb; break;                 // LEU
                case 12: r = anan || bnan || fa > fb; break;                  // GTU
                case 13: r = anan || bnan || fa != fb; break;                 // NEU
                case 14: r = anan || bnan || fa >= fb; break;                 // GEU
                case 15: r = true; break;                                    // T
                default: break;
            }
            // Bop combines (r) with Pp: AND/OR/XOR.  Pu = (r) BOP Pp;
            // Pv = (!r) BOP Pp (verified: FSETP Pv is NOT !Pu for OR).
            bool ppv = true;
            if (pp) read_pred(t, *pp, &ppv);
            bool out = false;
            switch (bop) {
                case 0: out = r && ppv; break;  // AND
                case 1: out = r || ppv; break;  // OR
                case 2: out = r != ppv; break;  // XOR
                default: out = r; break;
            }
            bool outv = false;
            switch (bop) {
                case 0: outv = (!r) && ppv; break;
                case 1: outv = (!r) || ppv; break;
                case 2: outv = (!r) != ppv; break;
                default: outv = !r; break;
            }
            if (fast_mode()) note_fast_leaf(false);
            if (m == "FSETP") {
                if (pu) write_pred(t, *pu, out);
                if (pv) write_pred(t, *pv, outv);
            } else {  // FSET: Rd = 1.0f or 0.0f (also writes inverse via
                // Pv-style semantics not present; FSET.Rd holds result).
                write_rd(w, t, inst, rd, out ? 0x3f800000u : 0u, 0);
            }
        }
        return Status::success();
    }

    if (m == "FMNMX") {
        // FMNMX Rd, Ra, Rb/Sb, Pp  (Pp: PT=min, !PT=max; .NAN propagate).
        // XORSIGN: result sign = sign(Ra) XOR sign(Rb) XOR sign(result).
        const bool nan = slot_value(inst, "nan").value_or(0) != 0;
        const bool xorsign = slot_value(inst, "xorsign").value_or(0) != 0;
        const bool ftz = slot_value(inst, "ftz").value_or(0) != 0;
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* sb = find_op(inst, "Sb");
        const Operand* pp = find_op(inst, "Pp");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            std::uint32_t b = rb ? read_reg_val(t, *rb)
                : (sb && (sb->kind == "UImm" || sb->kind == "SImm"))
                    ? static_cast<std::uint32_t>(sb->value)
                    : 0;
            if (ftz) {
                if (fast_mode()) {
                    if (options_.fast_fp_fallback != FastFpFallback::kNone) {
                        ++fast_stats_.precise_fallback_ops;
                        a = fp::flush_f32(a);
                        b = fp::flush_f32(b);
                    } else {
                        ++fast_stats_.ignored_modifier_ops;
                    }
                } else {
                    a = fp::flush_f32(a);
                    b = fp::flush_f32(b);
                }
            }
            bool is_max = false;
            if (pp) {
                // Pp=PT (7) is "min" per the test; !PT is max.  read_pred
                // returns the raw predicate value: PT -> true.  We treat
                // (pred value == 7 AND not inverted) as min, anything else
                // as max (this matches FMNMX R3, R0, R1, PT -> min and
                // FMNMX R3, R0, R1, !PT -> max).
                is_max = !(pp->value == 7 && !pp->pred_not);
            } else {
                is_max = false;  // default min
            }
            const float fa = std::bit_cast<float>(a);
            const float fb = std::bit_cast<float>(b);
            const bool a_nan = std::isnan(fa);
            const bool b_nan = std::isnan(fb);
            std::uint32_t out;
            bool nan_propagated = false;
            if (nan && (a_nan || b_nan)) {
                // .NAN: propagate a NaN (canonicalize like arithmetic).
                out = fp::kCanonicalNan32;
                nan_propagated = true;
            } else if (a_nan || b_nan) {
                // nonan: return the non-NaN operand.
                out = a_nan ? b : a;
                nan_propagated = true;
            } else {
                // min/max of two numbers; ties pick b on min per the test
                // (+0/-0 handled by comparing as IEEE float).
                const bool pick_b = is_max ? (fb >= fa) : (fb <= fa);
                out = pick_b ? b : a;
            }
            // XORSIGN only applies to the selected min/max value, NOT to a
            // NaN-propagated result (verified: FMNMX.XORSIGN with a NaN
            // operand returns the non-NaN operand with its own sign).
            if (xorsign && !nan_propagated) {
                // XORSIGN: result sign = sign(a) XOR sign(b).  Verified:
                // FMNMX.XORSIGN min(-1,-2) -> +2 (sa^sb = 1^1 = 0 -> +).
                const std::uint32_t sa = (a >> 31) & 1;
                const std::uint32_t sb_ = (b >> 31) & 1;
                const std::uint32_t ns = sa ^ sb_;
                out = (out & 0x7fffffffu) | (ns << 31);
            }
            if (fast_mode()) note_fast_leaf(false);
            write_rd(w, t, inst, rd, out, 0);
        }
        return Status::success();
    }

    if (m == "FSEL") {
        // FSEL Rd, Ra, Rb/Sb, Pp (select Ra when Pp true, else Rb/Sb).
        const bool ftz = slot_value(inst, "ftz").value_or(0) != 0;
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* sb = find_op(inst, "Sb");
        const Operand* pp = find_op(inst, "Pp");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            if (ftz) {
                if (fast_mode()) {
                    if (options_.fast_fp_fallback != FastFpFallback::kNone) {
                        ++fast_stats_.precise_fallback_ops;
                        a = fp::flush_f32(a);
                    } else {
                        ++fast_stats_.ignored_modifier_ops;
                    }
                } else {
                    a = fp::flush_f32(a);
                }
            }
            std::uint32_t b = rb ? read_reg_val(t, *rb)
                : (sb && (sb->kind == "UImm" || sb->kind == "SImm"))
                    ? static_cast<std::uint32_t>(sb->value)
                    : 0;
            bool p = false;
            if (pp) read_pred(t, *pp, &p);
            if (fast_mode()) note_fast_leaf(false);
            write_rd(w, t, inst, rd, p ? a : b, 0);
        }
        return Status::success();
    }

    // ---- conversions -----------------------------------------------------
    if (m == "F2F") {
        // F2F Rd, Rb (src/dst format in the combined dstfmt.srcfmt slot).
        const std::uint64_t fmt = slot_value(inst, "dstfmt.srcfmt").value_or(0);
        const Rnd rnd = static_cast<Rnd>(slot_value(inst, "rnd").value_or(0));
        const bool ftz = slot_value(inst, "ftz").value_or(0) != 0;
        const bool sat = slot_value(inst, "sat").value_or(0) != 0;
        const Operand* rb = find_op(inst, "Rb");
        if (!rb || !rd) return Status::success();
        // Combined fmt codes (DSTFMT_SRCFMT_*): F16.F32=17, BF16.F32=20,
        // F32.F16=10, BF16.F16=12, F16.BF16=33, F32.BF16=34, F64.F16=11,
        // F64.BF16=35, F16.F64=25, F32.F64=26, BF16.F64=28.
        int dstfmt = 0, srcfmt = 0;
        switch (fmt) {
            case 17: dstfmt = 0; srcfmt = 1; break;   // F16.F32
            case 19: dstfmt = 2; srcfmt = 1; break;   // F64.F32
            case 20: dstfmt = 3; srcfmt = 1; break;   // BF16.F32
            case 10: dstfmt = 1; srcfmt = 0; break;   // F32.F16
            case 12: dstfmt = 3; srcfmt = 0; break;   // BF16.F16
            case 33: dstfmt = 0; srcfmt = 3; break;   // F16.BF16
            case 34: dstfmt = 1; srcfmt = 3; break;   // F32.BF16
            case 11: dstfmt = 2; srcfmt = 0; break;   // F64.F16
            case 35: dstfmt = 2; srcfmt = 3; break;   // F64.BF16
            case 25: dstfmt = 0; srcfmt = 2; break;   // F16.F64
            case 26: dstfmt = 1; srcfmt = 2; break;   // F32.F64
            case 28: dstfmt = 3; srcfmt = 2; break;   // BF16.F64
            default: break;
        }
        // M5 pre-binding: F64 source pair base + dest index (used by both the
        // fast and the precise path below; hoisted out of the lane loop).
        const int rb_r = bind_reg_index(rb);
        const int rd_r = bind_reg_index(rd);
        // Hoisted policy flag (Medium-7 / perf): under kNone the exceptional
        // input/result classification is skipped entirely; only kExceptional
        // pays for it.
        const bool exc_policy =
            options_.fast_fp_fallback == FastFpFallback::kExceptional;
        auto read_f64_pair = [](const ThreadState& t, int idx) {
            if (idx < 0 || idx >= kNumGprs - 1) return std::uint64_t{0};
            return t.gpr[idx] |
                   (static_cast<std::uint64_t>(t.gpr[idx + 1]) << 32);
        };
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t src = read_reg_val(t, *rb);
            std::uint32_t out = 0;
            std::uint32_t outhi = 0;
            // Phase 5.5: fast F2F for native host conversions (RN, no
            // FTZ/FMZ/SAT).  Fallback policy routes exceptional inputs and
            // modifier mismatches to the precise helpers.
            if (fast_mode() && rnd == Rnd::kRn && !ftz && !sat) {
                std::uint32_t src_hi = 0;
                bool exceptional = false;
                if (srcfmt == 2) {  // F64 source: read the {Rb,Rb+1} pair and
                                    // classify the FULL 64-bit pattern as a
                                    // double (not two separate f32s — High-3).
                    const std::uint64_t pair = read_f64_pair(t, rb_r);
                    src_hi = static_cast<std::uint32_t>(pair >> 32);
                    exceptional = exc_policy && exceptional_f64(pair);
                } else {
                    // Format-aware source classification (round-3 Blocker):
                    // a BF16/F16 source lives in the low 16 bits; the raw
                    // 32-bit register value is not a meaningful f32.
                    exceptional = exc_policy &&
                        exceptional_f2f_source(srcfmt, src, src_hi);
                }
                std::uint32_t fout = 0, fouthi = 0;
                if (!exceptional &&
                    fp::fast_f2f(src, src_hi, dstfmt, srcfmt, &fout,
                                 &fouthi)) {
                    // Fast conversion produced a native result.  Under
                    // kExceptional, a native RESULT that is exceptional (e.g.
                    // finite F32 -> F16 overflow to Inf) also falls back.
                    // Exactly ONE precise_fallback_ops increment per lane/leaf:
                    // fall through to the common exit below (Issue-2 round-2 —
                    // no double counting).
                    const bool result_exc =
                        exc_policy && exceptional_f2f_result(dstfmt, fout,
                                                             fouthi);
                    if (!result_exc) {
                        note_fast_leaf(true);
                        if (rd_r >= 0) {
                            t.gpr[rd_r] = fout;
                            if (dstfmt == 2 && rd_r < kNumGprs - 1)
                                t.gpr[rd_r + 1] = fouthi;
                        }
                        continue;
                    }
                }
                // Common fallback exit: reached when the input is exceptional,
                // fast_f2f cannot handle the (dstfmt,srcfmt) pair natively, or
                // the native result was exceptional.  Counted exactly once.
                ++fast_stats_.precise_fallback_ops;
            }
            if (dstfmt == 2) {
                std::uint32_t f32;
                if (srcfmt == 0) f32 = fp::f16_to_f32(
                    static_cast<std::uint16_t>(src & 0xffffu));
                else if (srcfmt == 3) f32 = src & 0xffff0000u;
                else f32 = src;
                if (ftz) f32 = fp::flush_f32(f32);
                const double dbl = static_cast<double>(
                    std::bit_cast<float>(f32));
                const std::uint64_t d = std::bit_cast<std::uint64_t>(dbl);
                out = static_cast<std::uint32_t>(d & 0xffffffffu);
                outhi = static_cast<std::uint32_t>(d >> 32);
            } else if (srcfmt == 2) {
                // 64-bit source (F16/BF16/F32 <- F64): read the {Rb,Rb+1}
                // pair as the F64 value and downconvert DIRECTLY from the
                // FP64 bit pattern (no FP32 intermediate — avoids double
                // rounding and preserves directed rounding).
                const std::uint64_t pair = read_f64_pair(t, rb_r);
                if (dstfmt == 1) {  // F32.F64
                    out = fp::f64_to_f32(pair, rnd, ftz, sat);
                } else if (dstfmt == 0) {  // F16.F64
                    out = fp::f64_to_f16(pair, rnd, ftz, sat);
                } else if (dstfmt == 3) {  // BF16.F64
                    out = fp::f64_to_bf16(pair, rnd, ftz, sat);
                }
            } else {
                out = fp::f2f(src, dstfmt, srcfmt, rnd, ftz, sat);
            }
            if (rd_r >= 0) {
                t.gpr[rd_r] = out;
                if (dstfmt == 2 && rd_r < kNumGprs - 1) t.gpr[rd_r + 1] = outhi;
            }
            (void)outhi;
        }
        return Status::success();
    }

    if (m == "I2F" || m == "F2I") {
        const Rnd rnd = static_cast<Rnd>(slot_value(inst, "rnd").value_or(0));
        const bool ftz = slot_value(inst, "ftz").value_or(0) != 0;
        const bool sat = slot_value(inst, "sat").value_or(0) != 0;
        // dstfmt/srcfmt: I2F uses {Float64,S32ONLY,...}; F2I uses
        // {DSTFMT_U64_S64,Float32} where the raw values match the fp.hpp
        // format constants (U32=4, S32=5, F32=1).
        const int dstfmt = static_cast<int>(slot_value(inst, "dstfmt").value_or(0));
        const int srcfmt = static_cast<int>(slot_value(inst, "srcfmt").value_or(1));
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* sb = find_op(inst, "Sb");
        const Operand* src = ra ? ra : (rb ? rb : sb);
        if (!src) return Status::success();
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            const std::uint32_t val =
                (src->kind == "Register") ? read_reg_val(t, *src)
                : static_cast<std::uint32_t>(src->value);
            std::uint64_t out = 0;
            if (fast_mode()) {
                // Phase 5.5 fast conversions.  I2F: RN + F32/F64 destination
                // are native host casts (bit-exact); otherwise fall back.
                // F2I: checked-range fast conversion; out-of-range / NaN /
                // Inf / unsupported format routes to the precise saturating
                // helper (no UB on any path).
                if (m == "I2F") {
                    const int f = dstfmt == 3 ? 2
                                 : dstfmt == 1 ? 0
                                 : dstfmt == 4 ? 3
                                 : 1;  // map to fp F16=0 F32=1 F64=2 BF16=3
                    std::uint32_t fout = 0, fouthi = 0;
                    if (rnd == Rnd::kRn &&
                        fp::fast_i2f(val, f, srcfmt, &fout, &fouthi)) {
                        note_fast_leaf(true);
                        write_rd(w, t, inst, rd, fout, fouthi, f == 2);
                        continue;
                    }
                    ++fast_stats_.precise_fallback_ops;
                } else {  // F2I
                    std::uint32_t fout = 0;
                    if (fp::fast_f2i(val, dstfmt, static_cast<int>(rnd), ftz,
                                     &fout)) {
                        note_fast_leaf(true);
                        write_rd(w, t, inst, rd, fout, 0, false);
                        continue;
                    }
                    ++fast_stats_.precise_fallback_ops;
                }
            }
            if (m == "I2F") {
                // I2F dstfmt enum: Float32 F32=2, Float64 F64=3,
                // DSTFMT_F16_F32_BF16 F16=1 F32=2 BF16=4.  Map to the fp
                // constants (F16=0 F32=1 F64=2 BF16=3).
                int f = 1;
                switch (dstfmt) {
                    case 1: f = 0; break;  // F16
                    case 2: f = 1; break;  // F32
                    case 3: f = 2; break;  // F64
                    case 4: f = 3; break;  // BF16
                    default: f = 1; break;
                }
                out = fp::i2f(val, f, srcfmt, rnd, sat);
            } else {
                out = fp::f2i(val, dstfmt, srcfmt, rnd, ftz, false);
            }
            // F64 destinations (I2F.F64, dstfmt==3) write a register pair.
            const bool f64_dst = (m == "I2F" && dstfmt == 3);
            write_rd(w, t, inst, rd, static_cast<std::uint32_t>(out),
                     static_cast<std::uint32_t>(out >> 32), f64_dst);
        }
        return Status::success();
    }

    if (m == "FRND") {
        const Rnd rnd = static_cast<Rnd>(slot_value(inst, "rnd").value_or(0));
        const Operand* ra = find_op(inst, "Ra");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            const float f = std::bit_cast<float>(a);
            float r;
            switch (rnd) {
                case Rnd::kRm: r = std::floor(f); break;
                case Rnd::kRp: r = std::ceil(f); break;
                case Rnd::kRz: r = std::trunc(f); break;
                default: r = std::nearbyint(f); break;
            }
            if (fast_mode()) note_fast_leaf(false);
            write_rd(w, t, inst, rd, std::bit_cast<std::uint32_t>(r), 0);
        }
        return Status::success();
    }

    if (m == "P2R") {
        // P2R[.B0/.B1/.B2/.B3] Rd, PR, Ra, Sb — pack predicates into Rd.
        // Rd = Ra (base); for each predicate i where Sb bit i is set, write
        // P[i] into bit (i + 8*insert); insert selects the byte (B0=0..B3=3).
        const std::uint64_t insert = slot_value(inst, "insert").value_or(0);
        const Operand* ra = find_op(inst, "Ra");
        const Operand* sb = find_op(inst, "Sb");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t base = ra ? read_reg_val(t, *ra) : 0;
            std::uint32_t sel = (sb && (sb->kind == "UImm" || sb->kind == "SImm"))
                ? static_cast<std::uint32_t>(sb->value)
                : (sb && sb->kind == "Register")
                    ? read_reg_val(t, *sb)
                    : 0;
            std::uint32_t out = base;
            const unsigned shift = static_cast<unsigned>(8 * (insert & 3));
            for (int i = 0; i < 8; ++i) {
                if (!(sel & (1u << i))) continue;
                const bool pv = (i == 7) ? true : t.pred[i];  // P7 = PT
                const std::uint32_t bit = 1u << (i + shift);
                if (pv) out |= bit;
                else out &= ~bit;
            }
            write_rd(w, t, inst, rd, out, 0);
        }
        return Status::success();
    }

    // ---- collectives -----------------------------------------------------
    if (m == "VOTE") {
        // VOTE.op Rd, Pu, Pp — warp-wide reduction of Pp into Rd (bitmask),
        // Pu = result predicate (per-lane).
        const std::uint64_t op = slot_value(inst, "voteop").value_or(1);
        const Operand* pu = find_op(inst, "Pu");
        const Operand* pp = find_op(inst, "Pp");
        // Build the warp mask of Pp over all ACTIVE lanes (those at this PC).
        std::uint32_t all = 0;
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            const ThreadState& t = w.threads[lane];
            bool p = false;
            if (pp) read_pred(t, *pp, &p);
            if (p) all |= (1u << lane);
        }
        const int pop = __builtin_popcount(all);
        const bool result = (op == 0) ? (pop == __builtin_popcount(mask))
            : (op == 1) ? (pop != 0)
            : (pop == __builtin_popcount(mask) || pop == 0);  // EQ
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            if (pu) write_pred(t, *pu, result);
            if (rd) write_rd(w, t, inst, rd, all, 0);
        }
        return Status::success();
    }

    if (m == "ELECT") {
        // ELECT Pu, URd, Pp: leader election — lowest active lane with Pp.
        const Operand* pu = find_op(inst, "Pu");
        const Operand* pp = find_op(inst, "Pp");
        int leader = -1;
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            const ThreadState& t = w.threads[lane];
            bool p = false;
            if (pp) read_pred(t, *pp, &p);
            if (p) { leader = lane; break; }
        }
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            const bool is_leader = (lane == leader);
            if (pu) write_pred(t, *pu, is_leader);
            // URd = leader lane id for all lanes.
            if (auto urd = find_op(inst, "URd")) {
                if (urd->kind == "UniformRegister") {
                    const std::uint64_t r = static_cast<std::uint64_t>(urd->value);
                    if (r < kNumUrs) w.ur[r] = static_cast<std::uint32_t>(leader);
                }
            }
        }
        return Status::success();
    }

    if (m == "REDUX") {
        // REDUX.op.sz URd, Ra — reduce active-lane Ra values into URd.
        const std::uint64_t op = slot_value(inst, "op").value_or(0);
        const Operand* urd = find_op(inst, "URd");
        const Operand* ra = find_op(inst, "Ra");
        bool first = true;
        std::uint32_t acc = 0;
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            const ThreadState& t = w.threads[lane];
            const std::uint32_t v = ra ? read_reg_val(t, *ra) : 0;
            if (first) { acc = v; first = false; }
            else {
                switch (op) {
                    case 0: acc &= v; break;  // AND
                    case 1: acc |= v; break;  // OR
                    case 2: acc ^= v; break;  // XOR
                    case 4: acc = (v < acc) ? v : acc; break;  // MIN
                    case 5: acc = (v > acc) ? v : acc; break;  // MAX
                    default: acc += v; break;  // SUM
                }
            }
        }
        if (!first && urd && urd->kind == "UniformRegister") {
            const std::uint64_t r = static_cast<std::uint64_t>(urd->value);
            if (r < kNumUrs) w.ur[r] = acc;
        }
        return Status::success();
    }

    if (m == "SHFL") {
        // SHFL.idx/mode Pu, Rd, Ra, Sb, Rc — warp shuffle.
        const std::uint64_t mode = slot_value(inst, "shflmd").value_or(0);
        const Operand* pu = find_op(inst, "Pu");
        const Operand* ra = find_op(inst, "Ra");
        const Operand* sb = find_op(inst, "Sb");
        const Operand* rc = find_op(inst, "Rc");
        // Gather all active-lane Ra values (per-lane).
        std::array<std::uint32_t, kLanesPerWarp> vals{};
        for (int lane = 0; lane < kLanesPerWarp; ++lane)
            vals[lane] = ra ? read_reg_val(w.threads[lane], *ra) : 0;
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            const std::uint32_t seg = (rc && rc->kind == "Register" &&
                                       rc->value != 255)
                ? read_reg_val(t, *rc) & 0x1f
                : 0;
            std::uint32_t idx = 0;
            if (sb) {
                if (sb->kind == "UImm" || sb->kind == "SImm") {
                    idx = static_cast<std::uint32_t>(sb->value) & 0x1f;
                } else if (sb->kind == "Register") {
                    idx = read_reg_val(t, *sb) & 0x1f;
                }
            }
            int srclane = -1;
            const int laneid = lane;
            switch (mode) {
                case 0:  // IDX: source lane = seg_base + idx
                    srclane = static_cast<int>(seg + (idx & 0x1f));
                    break;
                case 1:  // UP: source lane = lane - idx (own if out of range)
                    srclane = laneid - static_cast<int>(idx);
                    break;
                case 2:  // DOWN: source lane = lane + idx (own if >= bound)
                    srclane = laneid + static_cast<int>(idx);
                    break;
                case 3:  // BFLY: source lane = lane ^ idx
                    srclane = laneid ^ static_cast<int>(idx);
                    break;
                default: break;
            }
            // Range check: UP keeps only lane-idx >= 0; DOWN keeps only
            // lane+idx < 32; IDX keeps the source < 32 (segment bounds the
            // source to [seg*0, seg*0+31] — a full warp when seg=0).
            const bool valid = (srclane >= 0 && srclane < kLanesPerWarp);
            if (valid && (mask & (1u << srclane))) {
                write_rd(w, t, inst, rd, vals[srclane], 0);
                if (pu) write_pred(t, *pu, true);
            } else {
                // Out of range: Rd = the lane's own Ra value (verified in
                // test_shfl: UP t<delta keeps t; DOWN t+delta>=32 keeps t).
                write_rd(w, t, inst, rd, vals[lane], 0);
                if (pu) write_pred(t, *pu, false);
            }
        }
        return Status::success();
    }

    // ---- integer / bit ---------------------------------------------------
    if (m == "LOP3" || m == "LOP") {
        // LOP3 Rd, Ra, Rb, Rc, imm8 — 3-input logic with 8-bit LUT.
        // LOP  Rd, Ra, Rb — AND/OR/XOR/PASS_B.
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* rc = find_op(inst, "Rc");
        const Operand* imm = find_op(inst, "imm8");
        std::uint32_t lut = imm ? static_cast<std::uint32_t>(imm->value) : 0;
        if (m == "LOP") {
            // Map LOP.AND/OR/XOR/PASS_B to the matching 3-input truth table
            // with Rc=0:  AND=0x80, OR=0xfe, XOR=0x96, PASS_B=0xcc.
            const std::uint64_t lop = slot_value(inst, "lop").value_or(0);
            switch (lop) {
                case 0: lut = 0x80; break;  // AND
                case 1: lut = 0xfe; break;  // OR
                case 2: lut = 0x96; break;  // XOR
                case 3: lut = 0xcc; break;  // PASS_B
                default: break;
            }
        }
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            std::uint32_t b = rb ? read_reg_val(t, *rb) : 0;
            std::uint32_t c = rc ? read_reg_val(t, *rc) : 0;
            std::uint32_t out = 0;
            // LOP3 truth-table: bit i = output for input (a,b,c) with a as
            // the index MSB (verified: lut 0xC0 = a&b = bits 6,7).  Index =
            // (a<<2)|(b<<1)|(c<<0).
            for (int bit = 0; bit < 32; ++bit) {
                const int idx = (((a >> bit) & 1) << 2) |
                                (((b >> bit) & 1) << 1) |
                                ((c >> bit) & 1);
                if ((lut >> idx) & 1) out |= (1u << bit);
            }
            write_rd(w, t, inst, rd, out, 0);
        }
        return Status::success();
    }

    if (m == "SHF") {
        // SHF.L/.R Rd, Ra, Rb, Rc (shift count = Rb & 0x1f).  hilo selects
        // which register holds the value being shifted (verified on sm120):
        //   .L: HI uses (c<<sh)|(a>>(32-sh)); LO is just a<<sh (no fill)
        //   .R: LO uses (c<<(32-sh))|(a>>sh); HI is just c>>sh (no fill)
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* rc = find_op(inst, "Rc");
        const std::uint64_t dir = slot_value(inst, "dir").value_or(0);
        const std::uint64_t hilo = slot_value(inst, "hilo").value_or(0);
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            std::uint32_t b = rb ? read_reg_val(t, *rb) : 0;
            std::uint32_t c = rc ? read_reg_val(t, *rc) : 0;
            const unsigned sh = b & 0x1f;
            std::uint32_t out;
            if (dir == 0) {  // L
                if (hilo == 0) {
                    out = (sh == 0) ? a : (a << sh);
                } else {
                    out = (sh == 0) ? c : ((c << sh) | (a >> (32 - sh)));
                }
            } else {  // R
                if (hilo == 0) {
                    out = (sh == 0) ? a : ((c << (32 - sh)) | (a >> sh));
                } else {
                    out = (sh == 0) ? c : (c >> sh);
                }
            }
            write_rd(w, t, inst, rd, out, 0);
        }
        return Status::success();
    }

    if (m == "IABS") {
        const Operand* rb = find_op(inst, "Rb");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t b = rb ? read_reg_val(t, *rb) : 0;
            const std::uint32_t out = (b & 0x80000000u)
                ? ((b == 0x80000000u) ? b : (~b + 1)) : b;
            write_rd(w, t, inst, rd, out, 0);
        }
        return Status::success();
    }

    if (m == "IMNMX") {
        // IMNMX Rd, Ra, Sb, Pp — signed min/max (Pp: PT=min, !PT=max).
        const Operand* ra = find_op(inst, "Ra");
        const Operand* sb = find_op(inst, "Sb");
        const Operand* pp = find_op(inst, "Pp");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::int32_t a = static_cast<std::int32_t>(ra ? read_reg_val(t, *ra) : 0);
            std::int32_t b = (sb && (sb->kind == "UImm" || sb->kind == "SImm"))
                ? static_cast<std::int32_t>(sb->value)
                : (sb && (sb->kind == "Register")) ? static_cast<std::int32_t>(read_reg_val(t, *sb)) : 0;
            bool do_min = true;
            if (pp) read_pred(t, *pp, &do_min);
            std::int32_t out = do_min ? (a < b ? a : b) : (a > b ? a : b);
            write_rd(w, t, inst, rd, static_cast<std::uint32_t>(out), 0);
        }
        return Status::success();
    }

    if (m == "ISCADD") {
        // ISCADD Rd, Ra, Rb, imm (shift) — (Ra + (Rb << imm)).
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* imm = find_op(inst, "Ra_offset");
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            std::uint32_t b = rb ? read_reg_val(t, *rb) : 0;
            const unsigned sh = imm ? (static_cast<unsigned>(imm->value) & 0x1f) : 0;
            write_rd(w, t, inst, rd, a + (b << sh), 0);
        }
        return Status::success();
    }

    if (m == "LEA") {
        // LEA[.HI][.X] Rd, Pu, [-]Ra, [-]Rb, [Rc,] scaleU5.
        //   LO: Rd = low32((Ra << N) + Rb)
        //   HI: Rd = high32((Ra << N) + Rb + Rc)
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* rc = find_op(inst, "Rc");
        const std::uint64_t hilo = slot_value(inst, "hilo").value_or(0);
        const unsigned sh = static_cast<unsigned>(
            slot_value(inst, "scaleU5").value_or(0) & 0x1f);
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = ra ? read_reg_val(t, *ra) : 0;
            std::uint32_t b = rb ? read_reg_val(t, *rb) : 0;
            std::uint32_t c = rc ? read_reg_val(t, *rc) : 0;
            const std::uint64_t sum = (static_cast<std::uint64_t>(a) << sh) +
                                      b + (hilo ? c : 0);
            const std::uint32_t out = (hilo == 0)
                ? static_cast<std::uint32_t>(sum & 0xffffffffu)
                : static_cast<std::uint32_t>(sum >> 32);
            write_rd(w, t, inst, rd, out, 0);
        }
        return Status::success();
    }

    if (m == "POPC" || m == "FLO" || m == "BFE" || m == "BMSK" ||
        m == "BFREV" || m == "PRMT") {
        const Operand* ra = find_op(inst, "Ra");
        const Operand* rb = find_op(inst, "Rb");
        const Operand* sb = find_op(inst, "Sb");
        const Operand* src = ra ? ra : (rb ? rb : sb);
        if (!src) return Status::success();
        for (int lane = 0; lane < kLanesPerWarp; ++lane) {
            if (!(mask & (1u << lane))) continue;
            ThreadState& t = w.threads[lane];
            if (!t.active || t.exited) continue;
            std::uint32_t a = read_reg_val(t, *src);
            std::uint32_t b = rb ? read_reg_val(t, *rb)
                : (sb && (sb->kind == "UImm" || sb->kind == "SImm"))
                    ? static_cast<std::uint32_t>(sb->value)
                    : 0;
            std::uint32_t out = 0;
            if (m == "POPC") {
                out = static_cast<std::uint32_t>(__builtin_popcount(a));
            } else if (m == "FLO") {
                // FLO = find leading one (like __builtin_clz on the first
                // set bit).  Returns 0xffffffff when input is 0.
                out = (a == 0) ? 0xffffffffu
                    : static_cast<std::uint32_t>(31 - __builtin_clz(a));
            } else if (m == "BFE") {
                // BFE Rd, Ra, Rb: Rb[4:0]=offset, Rb[9:5]=size (u32).
                const unsigned off = b & 0x1f;
                const unsigned sz = (b >> 5) & 0x1f;
                if (sz == 0) out = 0;
                else if (sz == 32) out = a;
                else out = (a >> off) & ((1u << sz) - 1);
            } else if (m == "BMSK") {
                // BMSK[.C/.W] Rd, Ra, Rb: Ra = POSITION, Rb = WIDTH.
                //   Rd = ((1 << width) - 1) << pos (truncated to 32 bits).
                //   .C (clamp, default): pos>=32 -> 0; width>=32 -> all bits
                //      below pos (natural 32-bit truncation).
                //   .W (wrap): pos & 31 and width & 31 first.
                std::uint32_t pos = a;
                std::uint32_t width = b;
                const bool wrap = slot_value(inst, "cw").value_or(0) != 0;
                if (wrap) {
                    pos &= 31;
                    width &= 31;
                }
                if (pos >= 32) {
                    out = 0;  // .C: position out of range -> 0
                } else if (width == 0) {
                    out = 0;
                } else if (width >= 32) {
                    // all bits below pos (for pos=0 -> 0xFFFFFFFF).
                    out = ~0u << pos;
                } else {
                    out = ((1u << width) - 1u) << pos;
                }
            } else if (m == "BFREV") {
                // BFREV Rd, Ra — reverse bits.
                std::uint32_t v = a;
                for (int i = 0; i < 32; ++i) {
                    out = (out << 1) | (v & 1);
                    v >>= 1;
                }
            } else if (m == "PRMT") {
                // PRMT Rd, Ra, Rb, Rc — byte permute.  Rb[2:0]=src byte,
                // Rb[3]=zero/upper (0=source byte, 1=0xFF or 0), Rb[7:4]
                // ignored.  Rc = selector, Rb = sourceA, Ra = sourceB?  The
                // SASS form: PRMT Rd, Ra, Rb, Rc with Ra=sourceA, Rb=sel,
                // Rc=sourceB.  (Verified in test_prmt.)
                const Operand* rc_op = find_op(inst, "Rc");
                const std::uint32_t sel = b;
                const std::uint32_t srcb = rc_op ? read_reg_val(t, *rc_op) : 0;
                for (int i = 0; i < 4; ++i) {
                    const unsigned c = (sel >> (4 * i)) & 0xf;
                    if (c & 8) {
                        out |= ((c & 4) ? 0xffu : 0u) << (8 * i);
                    } else {
                        const unsigned by = (c & 3) * 8;
                        out |= ((a >> by) & 0xff) << (8 * i);
                    }
                }
                (void)srcb;
            }
            write_rd(w, t, inst, rd, out, 0);
        }
        return Status::success();
    }

    // ---- fault for unsupported --------------------------------------------------
    return do_unsupported(w, inst, pc, mask, fault);
}

Status Interpreter::do_unsupported(WarpState& w,
                                   const DecodedInstruction& inst,
                                   std::uint64_t pc, std::uint32_t mask,
                                   std::optional<Fault>* fault) {
    // decode-only instruction actually hit -> UnsupportedInstruction.
    Fault f(FaultKind::kUnsupportedInstruction,
            "instruction '" + inst.mnemonic + "' (" + inst.variant_class +
                ") is decode-only and not yet implemented at pc 0x" +
                std::to_string(pc));
    f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc)
        .set_active_mask(mask).set_instruction(inst.word);
    if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
}

Status Interpreter::detect_deadlock(CtaState& cta, const WarpState& w,
                                    std::uint64_t pc) {
    (void)cta; (void)w; (void)pc;
    // Placeholder: barrier deadlock detection is enforced by the scheduler
    // (a warp waiting at a barrier never becomes done; if all warps wait at
    // barriers, next_group returns false and the runner would exit cleanly —
    // Phase 4 marks this via a distinct check in the runner loop).
    return Status::success();
}

}  // namespace semu
