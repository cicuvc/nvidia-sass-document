// sm120 baseline interpreter -- run/step/orchestration, events, registry adapter.
// Split from src/interpreter.cpp (Interpreter member definitions
// moved verbatim; class, dispatch and orchestration untouched).

#include <semu/interpreter/interpreter.hpp>

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

#include <semu/fp/fast_fp.hpp>
#include <semu/fp/fp.hpp>
#include <semu/memory/l1tex_model.hpp>

#include "isa_shapes_fill.hpp"
#include "isa_data.hpp"

#include "sm120_shared.hpp"

namespace semu {
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
            const DecodedInstruction& inst = *kernel_.predecoded[idx].inst;
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

InterpreterResult Interpreter::run_result(const Kernel& kernel,
                                            const LaunchEnv& env,
                                            std::uint64_t limit,
                                            bool report_trace) {
    RunOptions opts;
    opts.instruction_limit = limit;
    opts.report_trace = report_trace;
    return run_result(kernel, env, opts);
}

InterpreterResult Interpreter::run_result(const Kernel& kernel,
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
InterpreterResult Interpreter::run_result_parallel(
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
        InterpreterResult r;
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
        // Phase 10 hotspot profile (opt-in): the winning worker's subset is
        // the deterministic minimum, so its profile is the report.
        if (options.collect_hotspots) merged.pc_hotspots = winning->pc_hotspots;
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
        // Phase 10 hotspot profile (opt-in): every worker profiled its own CTA
        // subset; summing the per-PC counts yields the launch-wide profile.
        if (options.collect_hotspots) {
            for (auto& [pc, n] : wr.r.pc_hotspots) {
                merged.pc_hotspots[pc] += n;
            }
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
InterpreterResult Interpreter::run_owned() {
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
            r.pc_hotspots = std::move(pc_hotspots_);
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
            r.pc_hotspots = std::move(pc_hotspots_);
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
            // Append mnemonic from a fresh decode + on-demand disassembly.
            const auto& pw = kernel_.predecoded[pc / 16];
            std::string d = Decoder::instance().disassemble(
                Word128{pw.lo, pw.hi}, /*full=*/false);
            if (!d.empty()) {
                std::snprintf(line, sizeof(line),
                              "w%d pc=0x%llx mask=0x%08x %s",
                              warp, static_cast<unsigned long long>(pc),
                              mask, d.c_str());
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
            r.pc_hotspots = std::move(pc_hotspots_);
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
            r.pc_hotspots = std::move(pc_hotspots_);
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
    r.pc_hotspots = std::move(pc_hotspots_);
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
    const DecodedInstruction& inst = *w.inst;

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
            // Phase 10 hotspot profile (opt-in): count every dynamic issue of a
            // static word, keyed by its kernel-relative BYTE PC (a future JIT
            // identifies hot basic blocks by byte PC).  Guarded by a single
            // branch when disabled.
            if (options_.collect_hotspots) ++pc_hotspots_[pc];
            // Unified per-instruction dispatch (plan-b refactor): every
            // implemented mnemonic has its own handler.  The decoded Mnemonic
            // is unique per instruction; no family falls through a generic
            // dispatcher anymore.  Anything not listed here is decode-only
            // and faults as unsupported.
            switch (inst.mnemonic) {
                // ---- control flow ------------------------------------------
                case isa::Mnemonic::kBRA:
                case isa::Mnemonic::kBRX:
                case isa::Mnemonic::kJMP:
                case isa::Mnemonic::kJMX:
                    return do_bra(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kBSSY:
                    return do_bssy(ws, inst, pc, exec_mask, fault);
                case isa::Mnemonic::kBSYNC:
                    return do_bsync(ws, inst, pc, exec_mask, fault);
                case isa::Mnemonic::kEXIT:
                    return do_exit(ws, inst, mask, pc);
                case isa::Mnemonic::kS2R:
                    return do_s2r(ws, inst, exec_mask, pc, fault);
                case isa::Mnemonic::kS2UR:
                    return do_s2ur(ws, inst, pc, fault);
                case isa::Mnemonic::kBAR:
                    return do_bar(ws, inst, exec_mask, pc, fault);
                case isa::Mnemonic::kNOP:
                    return Status::success();
                // ---- uniform-register ALU --------------------------------
                case isa::Mnemonic::kMOV:
                    return do_mov(ws, exec_mask, inst, pc);
                case isa::Mnemonic::kUMOV:
                    return do_umov(ws, inst, pc);
                case isa::Mnemonic::kUIADD3:
                    return do_uiadd3(ws, inst, pc);
                case isa::Mnemonic::kUSHF:
                    return do_ushf(ws, inst, pc);
                case isa::Mnemonic::kIADD3:
                    return do_iadd3(ws, exec_mask, inst, pc);
                case isa::Mnemonic::kISETP:
                    return do_isetp(ws, exec_mask, inst, pc);
                case isa::Mnemonic::kIMAD:
                    return do_imad(ws, exec_mask, inst, pc, fault);
                // ---- memory (one handler per instruction) ----------------
                case isa::Mnemonic::kLDG:
                    return do_ldg(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kSTG:
                    return do_stg(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kLDS:
                    return do_lds(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kSTS:
                    return do_sts(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kLDL:
                    return do_ldl(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kSTL:
                    return do_stl(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kLDC:
                    return do_ldc(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kLDCU:
                    return do_ldcu(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kATOM:
                    return do_atom(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kATOMS:
                    return do_atoms(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kREDS:
                    return do_reds(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kATOMG:
                    return do_atomg(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kREDG:
                    return do_redg(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kMEMBAR:
                    return do_membar(ws, inst);
                case isa::Mnemonic::kFENCE:
                    return do_fence(ws);
                case isa::Mnemonic::kERRBAR:
                    return do_errbar(ws, inst, pc);
                case isa::Mnemonic::kCGAERRBAR:
                    return do_cgaerrbar(ws, inst, pc);
                case isa::Mnemonic::kCCTL:
                    return do_cctl(ws, inst, pc);
                case isa::Mnemonic::kDEPBAR:
                    do_depbar(ws, inst, pc);
                    return Status::success();
                case isa::Mnemonic::kLDGDEPBAR:
                    do_ldgdepbar(ws, inst, pc);
                    return Status::success();
                case isa::Mnemonic::kLDGSTS:
                    return do_ldgsts(ws, exec_mask, inst, pc, fault);
                // ---- mbarrier / TMA families -------------------------------
                case isa::Mnemonic::kSYNCS:
                    return do_syncs(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kARRIVES:
                    return do_arrives(ws, inst, pc, fault);
                case isa::Mnemonic::kUTMALDG:
                    return do_utmaldg(ws, inst, pc, fault);
                case isa::Mnemonic::kUTMASTG:
                    return do_utmastg(ws, inst, pc, fault);
                case isa::Mnemonic::kUTMAREDG:
                    return do_utmaredg(ws, inst, pc, fault);
                case isa::Mnemonic::kUTMACMDFLUSH:
                    return do_utmacmdflush(ws, inst, pc);
                case isa::Mnemonic::kUTMACCTL:
                    return do_utmacctl(ws, inst, pc);
                // ---- tensor core -------------------------------------------
                case isa::Mnemonic::kHMMA:
                    return do_hmma(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kQMMA:
                    return do_qmma(ws, exec_mask, inst, pc, fault);
                case isa::Mnemonic::kOMMA:
                    return do_omma(ws, exec_mask, inst, pc, fault);
                // ---- compute (one handler per instruction) -----------------
                case isa::Mnemonic::kFADD:
                    return do_fadd(ws, exec_mask, inst);
                case isa::Mnemonic::kFMUL:
                    return do_fmul(ws, exec_mask, inst);
                case isa::Mnemonic::kFFMA:
                    return do_ffma(ws, exec_mask, inst);
                case isa::Mnemonic::kDADD:
                    return do_dadd(ws, exec_mask, inst);
                case isa::Mnemonic::kDMUL:
                    return do_dmul(ws, exec_mask, inst);
                case isa::Mnemonic::kDFMA:
                    return do_dfma(ws, exec_mask, inst);
                case isa::Mnemonic::kFSETP:
                    return do_fsetp(ws, exec_mask, inst);
                case isa::Mnemonic::kFSET:
                    return do_fset(ws, exec_mask, inst);
                case isa::Mnemonic::kFMNMX:
                    return do_fmnmx(ws, exec_mask, inst);
                case isa::Mnemonic::kFSEL:
                    return do_fsel(ws, exec_mask, inst);
                case isa::Mnemonic::kF2F:
                    return do_f2f(ws, exec_mask, inst);
                case isa::Mnemonic::kI2F:
                    return do_i2f(ws, exec_mask, inst);
                case isa::Mnemonic::kF2I:
                    return do_f2i(ws, exec_mask, inst);
                case isa::Mnemonic::kFRND:
                    return do_frnd(ws, exec_mask, inst);
                case isa::Mnemonic::kP2R:
                    return do_p2r(ws, exec_mask, inst);
                case isa::Mnemonic::kVOTE:
                    return do_vote(ws, exec_mask, inst);
                case isa::Mnemonic::kELECT:
                    return do_elect(ws, exec_mask, inst);
                case isa::Mnemonic::kREDUX:
                    return do_redux(ws, exec_mask, inst);
                case isa::Mnemonic::kSHFL:
                    return do_shfl(ws, exec_mask, inst);
                case isa::Mnemonic::kLOP3:
                    return do_lop3(ws, exec_mask, inst);
                case isa::Mnemonic::kLOP:
                    return do_lop(ws, exec_mask, inst);
                case isa::Mnemonic::kSHF:
                    return do_shf(ws, exec_mask, inst);
                case isa::Mnemonic::kIABS:
                    return do_iabs(ws, exec_mask, inst);
                case isa::Mnemonic::kIMNMX:
                    return do_imnmx(ws, exec_mask, inst);
                case isa::Mnemonic::kISCADD:
                    return do_iscadd(ws, exec_mask, inst);
                case isa::Mnemonic::kLEA:
                    return do_lea(ws, exec_mask, inst);
                case isa::Mnemonic::kPOPC:
                    return do_popc(ws, exec_mask, inst);
                case isa::Mnemonic::kFLO:
                    return do_flo(ws, exec_mask, inst);
                case isa::Mnemonic::kBMSK:
                    return do_bmsk(ws, exec_mask, inst);
                case isa::Mnemonic::kPRMT:
                    return do_prmt(ws, exec_mask, inst);
                default:
                    return do_unsupported(ws, inst, pc, exec_mask, fault);
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
}  // namespace

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
    ev.mnemonic = isa::mnemonic_name(inst.mnemonic);
    ev.request_kind = request_kind;
    ev.element_width = element_width;
    ev.issue_tick = ir.issue_tick;
    // No prediction on the ordinary path.
    ev.coupled_l1_to_shared = false;
    ev.prediction = false;
    // Phase 8 refinement: stable variant class + cache-policy contract.  The
    // ordinary LDG/STG/LDS/STS/atomic path always allocates through L1.
    ev.variant_class = isa::variant_class_name(inst.variant_class);
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
    ev.mnemonic = isa::mnemonic_name(inst.mnemonic);
    ev.request_kind = "coupled";
    ev.element_width = element_width;
    ev.issue_tick = ir.issue_tick;
    ev.coupled_l1_to_shared = true;
    // Phase 8 refinement: the LDGSTS cache-policy contract.  The `loc` typed
    // member (LOC enum) discriminates LOC@ACCESS (default, L1 allocate) from
    // LOC@BYPASS (the .cg / L1-bypass path).  The estimator honors it: "cg"
    // marks the SharedWf / conflict counters unsupported on the profiler path.
    ev.variant_class = isa::variant_class_name(inst.variant_class);

    std::uint64_t loc = 1;
    if (inst.variant_class == isa::VariantClass::kldgsts__desc_RRU) {
        // LDGSTS6 split: 0 = RUR, 1 = RR32U/RR64U (same `loc` member).
        loc = (inst.variant_class == isa::VariantClass::kldgsts__RUR ||
               inst.variant_class == isa::VariantClass::kldgsts_no_ra__RUR)
                  ? static_cast<std::uint64_t>(
                        static_cast<const shape::DecodedLDGSTS6_0*>(&inst)->loc)
                  : static_cast<std::uint64_t>(
                        static_cast<const shape::DecodedLDGSTS6_1*>(&inst)->loc);
    } else if (inst.variant_class == isa::VariantClass::kldgsts_memdesc_) {
        loc = static_cast<std::uint64_t>(
            static_cast<const shape::DecodedLDGSTS8*>(&inst)->loc);
    } else {  // LDGSTS6 (RUR/RR32U/RR64U/no-ra)
        loc = (inst.variant_class == isa::VariantClass::kldgsts__RUR ||
               inst.variant_class == isa::VariantClass::kldgsts_no_ra__RUR)
                  ? static_cast<std::uint64_t>(
                        static_cast<const shape::DecodedLDGSTS6_0*>(&inst)->loc)
                  : static_cast<std::uint64_t>(
                        static_cast<const shape::DecodedLDGSTS6_1*>(&inst)->loc);
    }
    const bool l1_bypass = loc == 0;
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
    d.mnemonic = isa::mnemonic_name(inst.mnemonic);
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
    a.mnemonic = isa::mnemonic_name(inst.mnemonic);
    a.space = space;
    a.cta = static_cast<std::uint32_t>(w.cta_id);
    a.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
    a.warp = static_cast<std::uint32_t>(w.warp_id);
    a.lane = lane;
    a.byte_begin = addr;
    a.byte_end = addr + len;
    a.is_write = is_write;
    a.is_atomic = is_atomic;
    a.atomic_op = is_atomic ? isa::mnemonic_name(inst.mnemonic) : "";
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
//
// Phase 10: extracted into the free `interpreter_handles` function so a
// backend (mock backend) can query the reference interpreter's runtime
// capability without constructing an interpreter.
bool interpreter_handles(const DecodedInstruction& inst) {
    const isa::Mnemonic m = inst.mnemonic;
    // Control flow (do_bra / do_bssy / do_bsync / do_exit / do_s2r / do_s2ur /
    // do_bar / NOP).
    if (m == isa::Mnemonic::kBRA || m == isa::Mnemonic::kBRX || m == isa::Mnemonic::kJMP || m == isa::Mnemonic::kJMX ||
        m == isa::Mnemonic::kBSSY || m == isa::Mnemonic::kBSYNC || m == isa::Mnemonic::kEXIT || m == isa::Mnemonic::kS2R ||
        m == isa::Mnemonic::kS2UR || m == isa::Mnemonic::kBAR || m == isa::Mnemonic::kNOP) {
        return true;
    }
    // Minimal ALU (do_mov / do_iadd3 / do_isetp / do_imad).  IMAD covers
    // the .WIDE / .HI / .X / imm / uniform variants (same mnemonic).
    if (m == isa::Mnemonic::kMOV || m == isa::Mnemonic::kIADD3 || m == isa::Mnemonic::kISETP || m == isa::Mnemonic::kIMAD) {
        return true;
    }
    // Phase 6 memory (per-instruction handlers; LDGSTS is functional).
    if (m == isa::Mnemonic::kLDG || m == isa::Mnemonic::kSTG || m == isa::Mnemonic::kLDS || m == isa::Mnemonic::kSTS ||
        m == isa::Mnemonic::kLDC || m == isa::Mnemonic::kLDCU || m == isa::Mnemonic::kLDL || m == isa::Mnemonic::kSTL ||
        m == isa::Mnemonic::kATOM || m == isa::Mnemonic::kATOMS || std::strcmp(isa::mnemonic_name(m), "RED") == 0 || m == isa::Mnemonic::kREDS ||
        m == isa::Mnemonic::kATOMG || m == isa::Mnemonic::kREDG || m == isa::Mnemonic::kMEMBAR || m == isa::Mnemonic::kFENCE ||
        m == isa::Mnemonic::kERRBAR || m == isa::Mnemonic::kCGAERRBAR || m == isa::Mnemonic::kCCTL ||
        m == isa::Mnemonic::kDEPBAR || m == isa::Mnemonic::kLDGDEPBAR || m == isa::Mnemonic::kLDGSTS) {
        return true;
    }
    // Phase 9 subset: mbarrier (SYNCS), cp.async.mbarrier.arrive (ARRIVES)
    // and the TMA family (UTMALDG / UTMASTG / UTMAREDG / UTMACMDFLUSH /
    // UTMACCTL).
    if (m == isa::Mnemonic::kSYNCS || m == isa::Mnemonic::kARRIVES || m == isa::Mnemonic::kUTMALDG ||
        m == isa::Mnemonic::kUTMASTG || m == isa::Mnemonic::kUTMAREDG || m == isa::Mnemonic::kUTMACMDFLUSH ||
        m == isa::Mnemonic::kUTMACCTL) {
        return true;
    }
    // Phase 9 tensor core: HMMA / QMMA / OMMA dense F32-accumulator shapes.
    // Sparse/rowcol/scale alternatives and the F16 accumulator fault at runtime
    // (do_hmma/do_qmma/do_omma dispatch on the decoded variant class /
    // modifier slots).
    if (m == isa::Mnemonic::kHMMA || m == isa::Mnemonic::kQMMA || m == isa::Mnemonic::kOMMA) {
        return true;
    }
    // Phase 5 compute (per-instruction handlers).
    if (m == isa::Mnemonic::kFADD || m == isa::Mnemonic::kFMUL || m == isa::Mnemonic::kFFMA || m == isa::Mnemonic::kDADD ||
        m == isa::Mnemonic::kDMUL || m == isa::Mnemonic::kDFMA || m == isa::Mnemonic::kFSETP || m == isa::Mnemonic::kFSET ||
        m == isa::Mnemonic::kFMNMX || m == isa::Mnemonic::kFSEL || m == isa::Mnemonic::kF2F || m == isa::Mnemonic::kI2F ||
        m == isa::Mnemonic::kF2I || m == isa::Mnemonic::kFRND || m == isa::Mnemonic::kP2R || m == isa::Mnemonic::kVOTE ||
        m == isa::Mnemonic::kELECT || m == isa::Mnemonic::kREDUX || m == isa::Mnemonic::kSHFL || m == isa::Mnemonic::kLOP3 ||
        m == isa::Mnemonic::kLOP || m == isa::Mnemonic::kSHF || m == isa::Mnemonic::kIABS || m == isa::Mnemonic::kIMNMX ||
        m == isa::Mnemonic::kISCADD || m == isa::Mnemonic::kLEA || m == isa::Mnemonic::kPOPC || m == isa::Mnemonic::kFLO ||
        m == isa::Mnemonic::kBMSK || m == isa::Mnemonic::kPRMT) {
        return true;
    }
    return false;
}

// The debugger-facing member: pure delegation to the free function.
bool Interpreter::supports(const DecodedInstruction& inst) const {
    return interpreter_handles(inst);
}

// Phase 7: S2R/S2UR special-register view (same resolve_sr the interpreter
// uses for the lane).  Returns 0 for unknown registers.
Status Interpreter::do_unsupported(WarpState& w,
                                   const DecodedInstruction& inst,
                                   std::uint64_t pc, std::uint32_t mask,
                                   std::optional<Fault>* fault) {
    // decode-only instruction actually hit -> UnsupportedInstruction.
    Fault f(FaultKind::kUnsupportedInstruction,
            "instruction '" + std::string(isa::mnemonic_name(inst.mnemonic)) + "' (" + std::string(isa::variant_class_name(inst.variant_class)) +
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

namespace {

// The reference-backend adapter: forwards the abstract IInterpreter surface
// to the concrete Interpreter statics.  Nothing else in the simulator needs
// to name Interpreter directly once it goes through the registry.
class DefaultInterpreter final : public IInterpreter {
public:
    const char* name() const override { return "reference-sm120"; }
    bool handles(const DecodedInstruction& inst) const override {
        return interpreter_handles(inst);
    }
    InterpreterResult run_result(const Kernel& kernel, const LaunchEnv& env,
                                 std::uint64_t limit, bool report_trace) const override {
        return Interpreter::run_result(kernel, env, limit, report_trace);
    }
    InterpreterResult run_result(const Kernel& kernel, const LaunchEnv& env,
                                 const RunOptions& options) const override {
        return Interpreter::run_result(kernel, env, options);
    }
    std::optional<Fault> run(const Kernel& kernel, const LaunchEnv& env,
                             std::uint64_t limit, bool report_trace) const override {
        return Interpreter::run(kernel, env, limit, report_trace);
    }
    std::optional<Fault> run(const Kernel& kernel, const LaunchEnv& env,
                             const RunOptions& options) const override {
        return Interpreter::run(kernel, env, options);
    }
    std::optional<Fault> run_shared(const Kernel& kernel, const LaunchEnv& env,
                                    std::vector<std::uint8_t>* shared_out,
                                    std::uint64_t limit) const override {
        return Interpreter::run_shared(kernel, env, shared_out, limit);
    }
};

std::vector<std::pair<std::string, InterpreterRegistry::Factory>>&
interpreter_registry_table() {
    static std::vector<std::pair<std::string, InterpreterRegistry::Factory>> t;
    return t;
}

}  // namespace

const IInterpreter* InterpreterRegistry::default_impl() {
    static const DefaultInterpreter d;
    return &d;
}

void InterpreterRegistry::register_impl(const char* name,
                                        InterpreterRegistry::Factory factory) {
    auto& t = interpreter_registry_table();
    for (auto& [n, f] : t) {
        if (n == name) {
            f = factory;
            return;
        }
    }
    t.emplace_back(name, factory);
}

const IInterpreter* InterpreterRegistry::find(const char* name) {
    for (auto& [n, f] : interpreter_registry_table()) {
        if (n == name) return f();
    }
    return nullptr;
}

std::vector<std::string> InterpreterRegistry::names() {
    std::vector<std::string> out;
    for (auto& [n, f] : interpreter_registry_table()) {
        out.push_back(n);
    }
    std::sort(out.begin(), out.end());
    return out;
}

}  // namespace semu
