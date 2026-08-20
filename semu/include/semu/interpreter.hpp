#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <semu/cluster.hpp>
#include <semu/context.hpp>
#include <semu/decoder.hpp>
#include <semu/execution.hpp>
#include <semu/fault.hpp>
#include <semu/fp.hpp>
#include <semu/l2_events.hpp>
#include <semu/mbarrier.hpp>
#include <semu/memory_events.hpp>
#include <semu/memory_service.hpp>
#include <semu/race_detector.hpp>
#include <semu/subcore_scheduler.hpp>
#include <semu/tensor.hpp>
#include <semu/tensor_map.hpp>

// Interpreter execution core and control flow (SIM_PLAN Phase 4).
//
// FROZEN (SIM_PLAN Phase 10): the Interpreter is the REFERENCE backend for
// the kBackendApiVersion contract (context.hpp/api.hpp).  Its public
// run/step/supports surface and Result are part of the frozen public API; the
// mock backend (mock_backend.hpp) decides interpreter-fallback by consulting
// `supports()` + the capability manifest.
//
// Implements per-lane independent thread scheduling (ITS): each thread has
// its own GPR file, predicate, lane PC and exit state; a warp executes one
// dynamic warp instruction for a chosen group of lanes sharing the same PC.
//
// State hierarchy:
//   - ThreadState: GPRs, predicates, lane PC, local state, exit/fault.
//   - WarpState: uniform registers (URs), uniform predicates, per-lane
//     thread states, BSSY/BSYNC sync stack, barrier/convergence state.
//   - CtaState: shared memory, warp list, named barriers, scheduler state.
//
// Control flow: guard predicate, BRA/BRX (relative), JMP/JMX (absolute /
// register), EXIT, BSSY/BSYNC (sync-stack reconvergence), natural
// convergence via per-lane PC.  S2R/S2UR special registers.  Dynamic
// instruction limit, no-progress detection, barrier deadlock detection.
// decode-only instructions hit at runtime -> Fault(kUnsupportedInstruction).

namespace semu {

constexpr int kLanesPerWarp = 32;
constexpr int kNumGprs = 256;
constexpr int kNumPreds = 8;      // P0..P6 + PT
constexpr int kNumUrs = 64;
constexpr int kNumUpreds = 8;     // UP0..UP6 + UPT

// One thread's execution state.
struct ThreadState {
    std::array<std::uint32_t, kNumGprs> gpr{};   // R0..R255 (RZ = 0)
    std::array<bool, 7> pred{};                   // P0..P6
    std::uint64_t pc = 0;        // byte offset within kernel text
    bool exited = false;
    bool active = true;          // false when exited or waiting
    // Fault locality (Phase 4 exit criterion).
    std::optional<Fault> fault;
};

// Per-warp state.
struct WarpState {
    int warp_id = 0;
    int cta_id = 0;              // grid-linear CTA id
    int local_cta_id = 0;        // index into Interpreter::ctas_ (worker subset)
    std::array<std::uint32_t, kNumUrs> ur{};   // UR0..UR63
    std::array<bool, kNumUpreds> upred{};      // UP0..UP6
    std::array<ThreadState, kLanesPerWarp> threads{};
    // BSSY/BSYNC sync stack (per-warp reconvergence).
    // BSSY/BSYNC reconvergence entry (Blocker fix, codex round 3).
    // `participating_lanes`: lanes that pushed this BSSY (the divergent
    // branch-takers that will reconverge at the BSYNC target).
    // `pending_lanes`: participating lanes still executing their divergent
    // path (not yet arrived at the BSYNC).
    // `arrived_lanes`: participating lanes that reached the BSYNC and are
    // suspended waiting for the rest.
    struct SyncEntry {
        std::uint64_t return_pc = 0;      // PC after the BSSY
        std::uint64_t reconverge_pc = 0;  // BSSY target (join point)
        std::uint32_t barrier_register = 0;  // Bn matched by BSYNC
        std::uint32_t participating_lanes = 0;
        std::uint32_t pending_lanes = 0;
        std::uint32_t arrived_lanes = 0;
    };
    std::vector<SyncEntry> sync_stack;
    // Phase 6: per-warp local memory window (local address space).
    std::vector<std::uint8_t> local;
    // Warp-wide uniform predicates latch (used by BAR / collective).
    std::uint64_t active_lanes = 0;   // 32-bit active mask
    bool done = false;                 // all lanes exited
    // Barrier a suspended warp is waiting at (-1 = not waiting).
    int waiting_barrier = -1;
};

// Per-CTA state: shared memory, warps, named barriers.
struct CtaState {
    int cta_id = 0;              // grid-linear CTA id
    std::vector<std::uint8_t> shared;   // shared memory window
    DevicePtr shared_base{0};    // shared window VA in the device map
    std::vector<WarpState> warps;
    // Named barriers: map barrier id -> {count, waiters bitmask}.
    struct NamedBarrier {
        std::uint32_t expected = 0;      // threads expected at the barrier
        std::vector<int> arrived;        // warp ids that arrived
        bool armed = true;
    };
    std::map<std::uint32_t, NamedBarrier> barriers;
    // Scheduler state (which warp to run next).
    std::uint64_t scheduler_tick = 0;

    // --- Phase 9 subset: async / TMA / mbarrier state ---------------------
    // mbarrier logical state keyed by shared byte offset (the 64-bit word at
    // that address is mirrored in `shared` for observability).
    std::map<std::uint32_t, MbarrierState> mbarriers;
    // cp.async (LDGSTS) committed-bytes accounting.  Each LDGSTS appends a
    // committed-bytes record to the current OPEN group; LDGDEPBAR seals it
    // (increments the group count on the target scoreboard); DEPBAR.LE drains.
    struct AsyncCopy {
        std::uint64_t committed_bytes = 0;  // width * active lanes
        std::uint32_t lane = 0;
    };
    struct AsyncGroup {
        std::vector<AsyncCopy> copies;
        std::uint64_t committed_bytes = 0;
        bool sealed = false;  // sealed by LDGDEPBAR (counted on a scoreboard)
    };
    // Group counter per scoreboard (SB0..SB5), driven by LDGDEPBAR / DEPBAR.
    std::array<std::uint64_t, 6> sb_group_count{};
    // Outstanding (sealed but not drained) LDGSTS groups, for the profiler /
    // debugger async-state view.  The interpreter's memory is synchronous, so
    // the copies land immediately; the group bookkeeping is observable state.
    std::vector<AsyncGroup> async_groups;
    AsyncGroup async_open;  // current unsealed group (LDGSTS accumulates here)
};

// Special register enum (subset Phase 4 implements).
enum class SpecialReg : std::uint32_t {
    kTidX = 0,   kTidY,   kTidZ,
    kCtaidX,     kCtaidY, kCtaidZ,
    kLaneid,
    kWarpId,     kWarpSize,
    kNtidX,      kNtidY,  kNtidZ,
    kNctaidX,    kNctaidY, kNctaidZ,
    kSmId,       kSmemBase,
    kClock,      kClock64,
    kLaneMaskEq, kLaneMaskLt, kLaneMaskLe,
    kLaneMaskGt, kLaneMaskGe,
    kUndefined,
};

// Launch-time parameter values the interpreter needs.
struct LaunchEnv {
    std::array<std::uint32_t, 3> grid{1, 1, 1};
    std::array<std::uint32_t, 3> block{1, 1, 1};
    std::array<std::uint32_t, 3> cluster{1, 1, 1};
    int sm_id = 0;
};

// Scheduler policies for the warp loop (Phase 4 verification).
enum class RunMode {
    kRunToExit,   // execute until all warps exit / limit / fault
    kStep,        // one dynamic warp instruction
};

// ---------------------------------------------------------------------------
// Phase 7 debugger support: one step of execution plus the introspection /
// mutation surface a debug session drives.  Everything here is part of the
// public C++ API (the CLI debug REPL and the debug session build on it); the
// debugger never reaches around the interpreter or the profiler.
// ---------------------------------------------------------------------------

// A single dynamic memory access performed by one lane of an executed group.
// Captured only while a step_group call is running (see step_group).
struct StepMemAccess {
    std::uint32_t lane = 0;      // lane id (0..31)
    AddressSpace space = AddressSpace::kGlobal;
    std::uint64_t address = 0;   // effective address: global VA, shared/local
                                 // byte offset, or constant-bank offset
    std::uint64_t width = 0;     // byte width of the access
    bool write = false;          // store (as opposed to load)
    bool atomic = false;         // atomic RMW
};

// Scheduling filter: should a (cta, warp) be eligible to run?  The CTA id is
// the grid-linear id, the warp the warp id inside that CTA.  Used to pin a
// debug session to one warp (warp step) without touching the scheduler.
using ScheduleFilter =
    std::function<bool(std::uint32_t cta, std::uint32_t warp)>;

// Phase 7 re-review (round 2, Blocker-2): WHY does the scheduler currently
// have no group to run?  Neither the normal runner nor the debugger may lump
// a deadlocked launch into "done": a barrier deadlock / no-progress stall is
// a FAULT, while focus-blocked is not terminal at all.
enum class ExecutionTerminalState : std::uint8_t {
    kRunning = 0,         // at least one runnable group passes the filter
    kDone,                // every warp exited cleanly (no stuck waiters)
    kBarrierDeadlock,     // >= 1 warp suspended at a named barrier that can
                          // never release (the other participants exited)
    kNoProgress,          // no runnable group and no barrier waiter: the
                          // launch is stalled (e.g. a sync-wait that never
                          // converges) — NOT a clean completion
    kFocusBlocked,        // runnable groups exist but the `eligible` filter
                          // excluded all of them — NOT terminal (clearing /
                          // re-targeting the filter resumes progress)
};

// Pre-execution veto: called with the decoded instruction of a selected group
// right before it executes.  Return false to STOP WITHOUT executing (the
// group stays runnable, state is untouched).  Breakpoints / unsupported-
// instruction stops are implemented through this.
using PreExecFilter =
    std::function<bool(std::uint32_t cta, std::uint32_t warp,
                       std::uint64_t pc, std::uint32_t mask,
                       const DecodedInstruction& inst)>;

// Outcome of one step_group call.
struct StepGroupFrame {
    std::uint32_t cta = 0;       // local CTA index (within ctas())
    std::uint32_t warp = 0;      // warp id
    std::uint64_t pc = 0;        // executed (or stopped-at) word address
    std::uint32_t mask = 0;      // lanes issued this group
    bool runnable = false;       // a runnable group existed
    bool executed = false;       // the group executed
    bool stopped = false;        // pre-exec veto stopped WITHOUT executing
    bool limit_hit = false;      // dynamic instruction limit reached
    // Blocker (Phase 7 re-review): set when step_group could not pick a group
    // because the `eligible` schedule filter (warp-step focus) excluded every
    // runnable group — even though the launch still has runnable warps.  This
    // is NOT "no runnable group" / launch done: a debugger must keep the
    // session alive so clearing focus (or re-targeting it) can continue.
    bool focus_blocked = false;
    std::optional<Fault> fault;  // fault produced by the executed group
    std::vector<StepMemAccess> accesses;  // committed accesses of the group
};

// Phase 6 Step 2D: one buffered race-relevant event.  The interpreter never
// feeds the RaceDetector during execution; it records events into a per-run
// log so the detector can be driven in a *deterministic* order afterwards.
// Parallel workers each produce a per-CTA-ordered log; the run result merges
// all logs sorted by (cta_id, ordinal) and replays them into ONE shared
// detector.  That guarantees cross-CTA/global races are observed together and
// the report JSON is byte-for-byte identical for any worker count.
struct RaceEvent {
    enum Kind {
        kObserve = 0,     // a shared/global memory access (plain load/store)
        kCtaBarrier = 1,  // CTA barrier release (HB across participating warps)
        kFence = 2,       // MEMBAR / FENCE (no standalone HB; diagnostics +
                          // combined with a matching atomic)
        kAtomic = 3,      // an atomic RMW (release/acquire clock bookkeeping)
    };
    Kind kind = kObserve;
    std::uint32_t cta = 0;      // grid-linear CTA id (global sort key 1)
    std::uint32_t sm = 0;       // actor SM (matches the accesses' actor())
    std::uint64_t ordinal = 0;  // per-CTA event sequence (global sort key 2)
    RaceAccess access;                 // kObserve / kAtomic
    std::vector<std::uint32_t> warps;  // kCtaBarrier
    std::uint32_t warp = 0;            // kFence: the executing warp
    std::string scope;                 // kFence (e.g. "cta", "gpu", "sys")
};

// Phase 6 Step 2C (High-2): one buffered L2 request descriptor.  Workers NEVER
// drive the shared L2 engine during execution (mutex acquisition order is not
// deterministic across threads, so request ids / sector insertion order would
// depend on host scheduling).  Instead each worker appends these stable
// descriptors in execution order with a per-CTA ordinal; after all workers
// join, run_result_parallel sorts them by (cta, ordinal, lane) and feeds them
// to a SINGLE-THREADED launch-level L2EventEngine, which assigns request/event
// ids and the seed schedule.  The result is a byte-for-byte deterministic,
// worker-count-independent L2 trace.
struct L2RequestDescriptor {
    std::uint32_t cta = 0;
    std::uint32_t sm = 0;
    std::uint32_t subcore = 0;
    std::uint32_t warp = 0;
    std::uint32_t lane = 0;
    std::uint64_t ordinal = 0;  // per-CTA access sequence (sort key 2)
    std::uint64_t pc = 0;
    std::string mnemonic;
    std::string request_kind;  // load / store / atomic / writeback
    std::uint64_t addr = 0;    // effective global VA
    std::uint64_t len = 0;     // access byte width
};

// Ready accessor for the interpreter's implemented mnemonic family: whether
// the reference interpreter FUNCTIONALLY executes this decoded instruction's
// family (mnemonic-level).  `Interpreter::supports` delegates here (it needs
// no instance state, so the mock backend can call it without constructing an
// interpreter).  NOTE: variant-level decode-only alternatives INSIDE a
// supported family (e.g. sparse/rowcol/scale tensor, TMA) are NOT excluded —
// callers that need the frozen capability boundary must ALSO consult the
// capability manifest (the mock backend does exactly that).
bool interpreter_handles(const DecodedInstruction& inst);

class Interpreter {
public:
    // Run a kernel's pre-decoded IR from pc=0 with the given environment.
    // Returns the fault (if any) or nullopt on clean completion.
    static std::optional<Fault> run(
        const Kernel& kernel, const LaunchEnv& env,
        std::uint64_t instruction_limit = 1000000,
        bool report_trace = false);
    static std::optional<Fault> run_shared(
        const Kernel& kernel, const LaunchEnv& env,
        std::vector<std::uint8_t>* shared_out,
        std::uint64_t instruction_limit = 1000000);

    // Expose the CTA state after run() for tests (via a result struct).
    struct Result {
        std::optional<Fault> fault;
        std::vector<CtaState> ctas;
        std::vector<std::string> trace;  // when report_trace
        std::uint64_t dynamic_instructions = 0;
        bool limit_reached = false;
        // Phase 5.5: which mode ran and fast-path accounting.
        ExecutionMode execution_mode = ExecutionMode::kPrecise;
        FastExecutionStats fast_stats;
        bool approximate = false;  // true once a fast FP leaf executed
        // Phase 6 Step 2B: trace-only memory events (empty unless model.l1tex
        // != kOff).  Never affects functional results.
        std::vector<MemoryEvent> memory_events;
        // Phase 6 Step 2D: data-race reports (empty unless model.race ==
        // kReport).  Trace-only; never affects functional results.
        std::vector<RaceReport> race_reports;
        // Phase 10 hotspot profile (empty unless options.collect_hotspots):
        // kernel-relative PC -> dynamic issue count for every static word that
        // executed.  Sorted ascending by PC.  The benchmark derives top-N
        // mnemonics from this map against the kernel's predecoded text.
        std::map<std::uint64_t, std::uint64_t> pc_hotspots;
    };
    static Result run_result(const Kernel& kernel, const LaunchEnv& env,
                             std::uint64_t instruction_limit = 1000000,
                             bool report_trace = false);
    static Result run_result(const Kernel& kernel, const LaunchEnv& env,
                             const RunOptions& options);

    // Run with explicit options (Phase 5.5).
    static std::optional<Fault> run(const Kernel& kernel,
                                    const LaunchEnv& env,
                                    const RunOptions& options);

    // Step-mode runner: execute exactly one dynamic warp instruction,
    // exposing the CTA state for the continuous-vs-step consistency test.
    // Returns false when no step is possible (all done / deadlock).
    bool step_once(std::vector<CtaState>* state_out,
                   std::uint64_t* executed_out,
                   std::optional<Fault>* fault_out);

    // Step-by-step consistency gate: run continuously vs one-group-at-a-time
    // and compare final GPR/predicate/exit state.  True on match.
    static bool step_consistent(const Kernel& kernel, const LaunchEnv& env,
                                std::uint64_t limit,
                                std::vector<CtaState>* final_state);

    // Phase 5.5: same gate parameterized by RunOptions (mode + limit).
    static bool step_consistent(const Kernel& kernel, const LaunchEnv& env,
                                const RunOptions& options,
                                std::vector<CtaState>* final_state);

    // Converge every sync entry whose pending set is empty: resume its
    // participating lanes at reconverge_pc+16 and erase the entries safely
    // (largest index first, avoiding iterator invalidation).  Called after
    // a BSYNC arrival or an EXIT removes pending lanes.
    void converge_completed_sync(WarpState& w);

    // TEST-ONLY (High-2 boundary): compute a BRX/JMX-style target from raw
    // 64-bit pair + offset values with the same checked arithmetic the
    // interpreter uses, clamped to a kernel of `text_size` bytes.  Returns
    // nullopt on overflow or out-of-range.  Used to probe INT64_MIN/MAX.
    static std::optional<std::uint64_t> probe_branch_target(
        const std::string& mnemonic, std::uint64_t pc,
        std::uint64_t pair, std::int64_t off, std::uint64_t text_size);

    // Phase 7 debugger: construct a single-worker stepping instance directly
    // (the debug session keeps it alive across steps; worker-subset behaviour
    // is not enabled here).  Determinism: the instance runs all CTAs on the
    // calling thread with the round-robin scheduler, so repeated identical
    // step sequences are byte-for-byte reproducible.
    Interpreter(const Kernel& kernel, const LaunchEnv& env,
                std::uint64_t limit, const RunOptions& options);

    // --- Phase 7 live state (inspection + modification by a debug session)
    // Live CTA state (the same objects the scheduler mutates).  A debugger
    // reads and rewrites GPR / UR / predicate / lane PC / exit / active /
    // barrier state here between steps; the next step observes the changes.
    std::vector<CtaState>& ctas() { return ctas_; }
    const std::vector<CtaState>& ctas() const { return ctas_; }
    // The interpreter's memory service (global/constant backing + shared /
    // local windows).  The debugger reads and writes device memory here.
    MemoryService* memory() { return memory_.get(); }
    const MemoryService* memory() const { return memory_.get(); }
    // Dynamic instruction count and run limit.
    std::uint64_t executed() const { return executed_; }
    std::uint64_t limit() const { return limit_; }
    const Kernel& kernel() const { return kernel_; }
    const LaunchEnv& env() const { return env_; }

    // True iff the interpreter can functionally execute this decoded
    // instruction (its control/memory/compute dispatch handles the mnemonic).
    // decode-only instructions report false so the debugger stops BEFORE
    // executing them with state still intact.  (Value/state-dependent fault
    // triggers — e.g. an unsupported atomic op enum or a BSYNC with no
    // matching BSSY — stay at runtime and surface as a StepInfo fault.)
    bool supports(const DecodedInstruction& inst) const;

    // Compute the S2R/S2UR special-register value for a lane (the same
    // `resolve_sr` the interpreter uses).  Returns 0 for unknown registers.
    std::uint32_t special_register_value(SpecialReg sr, std::uint32_t cta_id,
                                         std::uint32_t warp_id,
                                         int lane) const;

    // Phase 7 stepping: execute exactly one dynamic warp instruction.
    // `eligible` optionally restricts which (cta, warp) pairs the scheduler
    // may pick (warp step).  `pre_exec` is consulted right before the
    // selected group executes: returning false STOPS WITHOUT executing (the
    // group stays runnable and state is untouched; frame.stopped = true).
    // Returns false when no runnable group exists (all done / deadlock /
    // barrier-deadlock).  When the launch still has runnable groups but the
    // `eligible` filter excludes all of them, step_group also returns false
    // but sets frame.focus_blocked (NOT the launch-done case — the caller
    // must not latch `done`).  `state_out` / `executed_out` receive the live
    // state after the call.
    bool step_group(StepGroupFrame* frame, std::vector<CtaState>* state_out,
                    std::uint64_t* executed_out,
                    const ScheduleFilter* eligible = nullptr,
                    const PreExecFilter* pre_exec = nullptr);

    // Phase 7 re-review (round 2, Blocker-2): classify why the scheduler
    // would have no group to run right now under `eligible` (null = no
    // filter).  Returns kRunning when a group passes the filter; kFocusBlocked
    // when runnable groups exist but the filter excludes every one of them;
    // kBarrierDeadlock / kNoProgress when the launch is genuinely stuck; and
    // kDone when every warp exited cleanly.  The debugger calls this after a
    // step_group failure (focus_blocked == false) so a deadlocked launch is
    // reported as a fault instead of a clean Done.
    ExecutionTerminalState terminal_state(
        const ScheduleFilter* eligible = nullptr);
    // Build the descriptive barrier-deadlock Fault (first stuck CTA/barrier:
    // participants / expected / exited warps) — the exact fault the normal
    // run path reports.  Empty when terminal_state() != kBarrierDeadlock.
    std::optional<Fault> barrier_deadlock_fault() const;

private:
    // Worker-subset constructor (Phase 6 Step 2): builds only the CTAs whose
    // id % worker_count == worker_id, sharing a caller-provided MemoryService
    // so parallel workers observe one global buffer.
    Interpreter(const Kernel& kernel, const LaunchEnv& env,
                std::uint64_t limit, const RunOptions& options,
                MemoryService* shared_memory, int worker_id,
                int worker_count, RaceDetector* shared_detector = nullptr,
                L2EventEngine* shared_l2 = nullptr);
    // Run just the CTAs built by this (possibly worker-subset) instance.
    Result run_owned();
    // Phase 6 Step 2A: parallel worker pool over CTAs (shared MemoryService).
    static Result run_result_parallel(const Kernel& kernel,
                                      const LaunchEnv& env,
                                      const RunOptions& options);

    // --- scheduler --------------------------------------------------------
    // One scheduler scan over every (cta, warp, pc-group), shared by
    // next_group (which picks a group) and terminal_state (which classifies
    // why none was pickable).  `groups` holds the runnable groups passing
    // `eligible`; `any_runnable` is the runnable test ignoring the filter;
    // `any_barrier_wait` / `any_stalled` flag stuck warps (named-barrier
    // suspension / sync-wait with no live lanes).  Lazily marks all-exited
    // warps `done` (same side effect the old next_group scan had).
    struct ScheduleScan {
        struct Group {
            std::uint64_t cta = 0;    // index into ctas_
            std::uint64_t warp = 0;   // warp index within the CTA
            std::uint64_t pc = 0;
            std::uint32_t mask = 0;
        };
        std::vector<Group> groups;     // runnable groups passing `eligible`
        bool any_runnable = false;     // runnable regardless of the filter
        bool any_barrier_wait = false; // >= 1 warp waiting at a named barrier
        bool any_stalled = false;      // >= 1 warp stuck with no live lanes and
                                       // not at a barrier (sync-wait)
    };
    ScheduleScan scan_schedule(const ScheduleFilter* eligible);
    // Select the next (cta, warp, lane-group) to execute.  Returns false when
    // every warp is done / no runnable lanes remain.  `eligible`, when
    // non-null, restricts the (grid-linear cta, warp) pairs considered
    // (Phase 7 warp step).  When the scan finds runnable groups but `eligible`
    // excludes all of them, `eligible_blocked` (when non-null) is set true so
    // callers can distinguish "focus has nothing to run" from "launch done".
    bool next_group(int* cta_out, int* warp_out, std::uint64_t* pc_out,
                    std::uint32_t* mask_out,
                    const ScheduleFilter* eligible = nullptr,
                    bool* eligible_blocked = nullptr);
    // Execute one dynamic warp instruction for `mask` at `pc` in `cta`.  On
    // failure `fault` receives the enriched Fault (kind/pc/warp/active-mask/
    // instruction preserved).  When `exec_mask_out` is non-null it receives
    // the lanes that actually executed (the pc-group mask after per-lane
    // guard-predicate filtering), used by the Phase 7 debugger for accurate
    // active-mask reporting.
    Status execute_group(int cta, int warp, std::uint64_t pc,
                         std::uint32_t mask, std::optional<Fault>* fault,
                         std::uint32_t* exec_mask_out = nullptr);

    // --- helpers ----------------------------------------------------------
    std::uint32_t& reg(ThreadState& t, int n);
    bool resolve_guard(const WarpState& w, const DecodedInstruction& inst);
    std::uint32_t read_reg(ThreadState& t, int n) const;
    // Extract a branch target from decoded operands (kernel-relative byte).
    std::optional<std::uint64_t> branch_target(const DecodedInstruction& inst,
                                               std::uint64_t pc,
                                               ThreadState& t) const;
    // Extract the special register enum from the decoded SRa operand.
    std::optional<SpecialReg> special_reg(const DecodedInstruction& inst) const;
    // Medium-1: shared control-target validation (16-byte alignment + in
    // kernel text).  Returns the target on success, nullopt on violation.
    std::optional<std::uint64_t> validate_control_target(
        std::uint64_t target) const;
    // Phase 6 Step 2B (High-3): deterministic CTA -> SM mapping for the
    // simulated L2 / race / subcore domains.  With simulated_sm_count > 1 the
    // CTA's SM is cta % count (explicit topology); with 1 the launch's
    // env_.sm_id applies.
    std::uint32_t sm_of_cta(std::uint32_t cta) const;
    // High-4: warp-linear id across the whole launch.  ceil(block_threads/32)
    // so blocks smaller than 32 threads still give each warp a distinct id.
    std::uint64_t warp_linear_id(const WarpState& w) const;


    // --- per-opcode handlers ----------------------------------------------
    Status do_bra(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst, std::uint64_t pc,
                  std::optional<Fault>* fault);
    Status do_bssy(WarpState& w, const DecodedInstruction& inst,
                   std::uint64_t pc, std::uint32_t mask,
                   std::optional<Fault>* fault);
    Status do_bsync(WarpState& w, const DecodedInstruction& inst,
                    std::uint64_t pc, std::uint32_t mask,
                    std::optional<Fault>* fault);
    Status do_exit(WarpState& w, const DecodedInstruction& inst,
                   std::uint32_t mask, std::uint64_t pc);
    Status do_s2r(WarpState& w, const DecodedInstruction& inst,
                  std::uint32_t mask, std::uint64_t pc,
                  std::optional<Fault>* fault);
    Status do_s2ur(WarpState& w, const DecodedInstruction& inst,
                   std::uint64_t pc, std::optional<Fault>* fault);
    Status do_bar(WarpState& w, const DecodedInstruction& inst,
                  std::uint32_t mask, std::uint64_t pc,
                  std::optional<Fault>* fault);
    Status do_unsupported(WarpState& w, const DecodedInstruction& inst,
                          std::uint64_t pc, std::uint32_t mask,
                          std::optional<Fault>* fault);
    // Minimal ALU (MOV / IADD3 / ISETP / IMAD) to run control-flow kernels.
    Status do_mov(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst, std::uint64_t pc);
    // Phase 9 subset: uniform-register ALU (UMOV / UIADD3 / USHF) — used to
    // materialize mbarrier init words and TMA coordinate blocks in
    // hand-assembled kernels.
    Status do_umov(WarpState& w, const DecodedInstruction& inst,
                   std::uint64_t pc);
    Status do_uiadd3(WarpState& w, const DecodedInstruction& inst,
                     std::uint64_t pc);
    Status do_ushf(WarpState& w, const DecodedInstruction& inst,
                   std::uint64_t pc);
    Status do_iadd3(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst, std::uint64_t pc);
    Status do_isetp(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst, std::uint64_t pc);
    Status do_imad(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst, std::uint64_t pc,
                   std::optional<Fault>* fault);

    // --- Phase 6 memory ------------------------------------------------
    Status do_memory(WarpState& w, std::uint32_t mask,
                     const DecodedInstruction& inst, std::uint64_t pc,
                     std::optional<Fault>* fault);
    // Phase 9 subset: async / mbarrier / TMA instruction families.
    Status do_syncs(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst, std::uint64_t pc,
                    std::optional<Fault>* fault);
    Status do_arrives(WarpState& w, const DecodedInstruction& inst,
                      std::uint64_t pc, std::optional<Fault>* fault);
    Status do_tma(WarpState& w, const DecodedInstruction& inst,
                  std::uint64_t pc, std::optional<Fault>* fault);
    // Functional LDGSTS (cp.async): perform the global->shared copy per
    // active lane and accumulate committed bytes into the CTA's open async
    // group.  Also records the trace-only coupled prediction (kept from the
    // old trace-only path).
    Status do_ldgsts(WarpState& w, std::uint32_t mask,
                     const DecodedInstruction& inst, std::uint64_t pc,
                     std::optional<Fault>* fault);
    // LDGDEPBAR: seal the open async group and count it on the target SB.
    // DEPBAR.LE SBn, cnt: drain sealed groups until SBn's count <= cnt
    // (memory is synchronous, so the copies have already landed; the
    // bookkeeping is observable for the profiler/debugger).
    void do_ldgdepbar(WarpState& w, const DecodedInstruction& inst,
                      std::uint64_t pc);
    void do_depbar(WarpState& w, const DecodedInstruction& inst,
                   std::uint64_t pc);

    // --- Phase 9 subset: mbarrier / DSMEM helpers ----------------------
    // Look up (or lazily create from the shared word) the mbarrier state for
    // a shared byte offset in the source CTA.  Returns null when the shared
    // address is out of the window.
    MbarrierState* mbarrier_at(CtaState& cta, std::uint32_t shared_off,
                               bool create_if_missing);
    // Resolve a shared byte offset into the (CTA-local index, offset) pair.
    // When clusters are enabled and the address's high byte is a nonzero
    // cluster rank, translate to the peer CTA's shared window (DSMEM).  On
    // failure returns nullopt with the error set in `fault` (when provided).
    struct SharedTarget {
        std::size_t cta_local_idx = 0;
        std::uint32_t offset = 0;
        std::uint32_t target_rank = 0;
    };
    std::optional<SharedTarget> resolve_shared_target(
        const WarpState& w, std::uint32_t shared_addr,
        std::optional<Fault>* fault = nullptr);
    // The interpreter's cluster topology (built when the launch declares
    // cluster dims); empty = clusters disabled.
    std::optional<ClusterTopology> cluster_topology_;

    // Phase 6 Step 2B: record a trace-only subcore issue event for a warp
    // memory instruction (does not change any functional value).  Ordinary
    // LDG/STG/LDS/STS/atomic/constant paths NEVER feed the estimator.
    // Phase 8: `space`/`is_write`/`lane_ranges` carry the backend-neutral
    // raw per-lane byte ranges of the committed access so profiler analyzers
    // can subscribe to the same stream without re-execution.
    void record_memory_event(const WarpState& w, const DecodedInstruction& inst,
                             std::uint64_t pc, std::uint32_t mask,
                             const std::string& request_kind,
                             std::uint32_t element_width,
                             AddressSpace space, bool is_write,
                             const std::vector<LaneByteRange>& lane_ranges,
                             std::uint32_t committed_mask);
    // Phase 6 Step 2B (Blocker-4): record a REAL coupled L1->shared transfer
    // prediction (LDGSTS path only).  Collects the per-lane global/shared
    // offsets, active mask and element width, calls the UnifiedV1Estimator
    // and emits the prediction + token-service events.  Trace-only.
    // `prediction_unavailable` is set when one or more originally-active lanes
    // could not compute a valid address (High-2): the estimate is formed over
    // the VALID lanes only (the invalid lane's offset is never fabricated as
    // zero) and the event is explicitly marked prediction-unavailable.
    void record_coupled_l1_to_shared(const WarpState& w,
                                     const DecodedInstruction& inst,
                                     std::uint64_t pc, std::uint32_t mask,
                                     const std::uint32_t goff[32],
                                     const std::uint32_t soff[32],
                                     std::uint32_t element_width,
                                     bool prediction_unavailable = false);
    // Phase 6 Step 2C: trace-only L2 access for a global byte range.  Buffers
    // a stable request descriptor (see L2RequestDescriptor) instead of driving
    // the shared engine from a worker thread — the launch-level drain sorts by
    // (cta, ordinal, lane) and replays through a single-threaded engine, so
    // the trace is worker-count independent (High-2).  Never changes
    // functional values.  `lane` is the active lane the descriptor belongs to.
    void record_l2_access(const WarpState& w, const DecodedInstruction& inst,
                          std::uint64_t pc, std::uint32_t mask,
                          const std::string& request_kind,
                          AddressSpace space, std::uint64_t addr,
                          std::uint64_t len, std::uint32_t lane = 0);
    // Append any pending L2 events (requests + completions) to memory_events_
    // (trace-only).  Called before result assembly.
    void flush_l2_events();
    // Phase 6 Step 2D: record one shared/global access in the race detector
    // (trace-only; no functional effect).  `addr` is the per-lane address
    // (global VA or shared byte offset); `len` the access width.
    void record_race_access(const WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc, std::uint32_t lane,
                            AddressSpace space, std::uint64_t addr,
                            std::uint64_t len, bool is_write,
                            bool is_atomic, const std::string& mem_order,
                            const std::string& scope);
    // Phase 7: record one committed lane memory access for the current debug
    // step (no-op unless debug_capture_ is set).  Called at the same commit
    // points as the race detector so the debugger's memory events match the
    // actual memory effects.
    void record_debug_access(const WarpState& w, std::uint32_t lane,
                             AddressSpace space, std::uint64_t addr,
                             std::uint64_t len, bool is_write,
                             bool is_atomic);
    // Resolve a memory instruction's address operand (descriptor + Ra +
    // offset / shared offset / constant) into a target + width.
    Status resolve_mem_addr(const DecodedInstruction& inst,
                            const ThreadState& t, const WarpState& w,
                            std::uint64_t* addr_out, std::int64_t* off_out,
                            std::uint64_t* width_out, AddressSpace* space_out,
                            std::optional<Fault>* fault);

    // --- Phase 5 compute: one handler per instruction (plan-b refactor) ---
    // Every compute mnemonic has its own entry point; closely-related
    // instructions share a per-lane core (parameterized by the extracted
    // operands/modifiers) so the per-instruction function is just the
    // concrete-shape cast + forward.
    Status fp32_arith_core(WarpState& w, std::uint32_t mask,
                           const shape::OperandValue* ops,
                           std::uint64_t rd_rv, int op, semu::fp::Rnd rnd,
                           bool flush, bool sat, int fmz_val);
    Status fp64_arith_core(WarpState& w, std::uint32_t mask,
                           const shape::OperandValue* ops, int op,
                           semu::fp::Rnd rnd);
    Status fset_core(WarpState& w, std::uint32_t mask,
                     const shape::OperandValue* ops, std::uint16_t nops,
                     std::uint64_t fcomp, std::uint64_t bop, bool ftz,
                     int ra_pos, int pp_pos, bool dest_is_pred);
    Status cvtx_core(WarpState& w, std::uint32_t mask,
                     const shape::OperandValue* ops,
                     semu::fp::Rnd rnd, bool ftz,
                     int dstfmt, int srcfmt, bool is_i2f);
    Status lut_core(WarpState& w, std::uint32_t mask,
                    const shape::OperandValue* ops, std::uint32_t lut);
    Status bitops_core(WarpState& w, std::uint32_t mask,
                       const shape::OperandValue* ops, int apos, int bpos,
                       std::uint64_t cw, int mode);
    Status do_fadd(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_fmul(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_ffma(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_dadd(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_dmul(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_dfma(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_fsetp(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst);
    Status do_fset(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_fmnmx(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst);
    Status do_fsel(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_f2f(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_i2f(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_f2i(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_frnd(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_p2r(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_vote(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_elect(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst);
    Status do_redux(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst);
    Status do_shfl(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_lop3(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_lop(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_shf(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_iabs(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_imnmx(WarpState& w, std::uint32_t mask,
                    const DecodedInstruction& inst);
    Status do_iscadd(WarpState& w, std::uint32_t mask,
                     const DecodedInstruction& inst);
    Status do_lea(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_popc(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_flo(WarpState& w, std::uint32_t mask,
                  const DecodedInstruction& inst);
    Status do_bmsk(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    Status do_prmt(WarpState& w, std::uint32_t mask,
                   const DecodedInstruction& inst);
    // Temporary family dispatcher (removed when execute_group gains the
    // unified mnemonic switch).
    Status do_compute(WarpState& w, std::uint32_t mask,
                      const DecodedInstruction& inst, std::uint64_t pc,
                      std::optional<Fault>* fault);
    // Phase 9 tensor core: HMMA (0x23c) / QMMA (0x27a) / OMMA (0x47f).
    // Functional for the dense F32-accumulator shapes the tensor engine
    // implements; the sparse / rowcol / scaled-variant alternatives and the
    // F16 accumulator are decode-only and fault as unsupported.  Results are
    // NOT scoreboarded on hardware (COUPLED_MATH): programs must insert the
    // required NOP padding before reading D (the interpreter is synchronous
    // so this is a program contract, not a simulator requirement).
    Status do_tensor(WarpState& w, std::uint32_t mask,
                     const DecodedInstruction& inst, std::uint64_t pc,
                     std::optional<Fault>* fault);
    // Per-lane compute helpers (single lane value in, value out).
    std::uint64_t compute_value(const DecodedInstruction& inst,
                                const WarpState& w, const ThreadState& t,
                                std::uint64_t pc,
                                std::optional<Fault>* fault);

    // --- Phase 5.5 fast FP -------------------------------------------------
    bool fast_mode() const { return options_.mode == ExecutionMode::kFast; }
    // Per-instruction resolution of the FP32 add/mul/fma leaf, hoisted out of
    // the per-lane loop (M5: mode dispatch / function-pointer prebinding).
    // `op` is 0=FADD 1=FMUL 2=FFMA; the handler dispatches the leaf call via
    // op after consulting `use_fast` / `need_exceptional`.
    struct Fp32Plan {
        bool use_fast = false;         // fast leaf in effect for this lane
        bool need_exceptional = false; // kExceptional policy: classify inputs
        bool ignored_modifier = false; // fast ran a non-RN/FTZ/FMZ encoding
    };
    // FP64 counterpart.
    struct Fp64Plan {
        bool use_fast = false;
        bool need_exceptional = false;
        bool ignored_modifier = false;
    };
    // Resolve one instruction's FP32 leaf policy (op 0=FADD 1=FMUL 2=FFMA).
    Fp32Plan plan_fp32(int op, int rnd, bool flush) const;
    // Resolve one instruction's FP64 leaf policy (op 0=DADD 1=DMUL 2=DFMA).
    Fp64Plan plan_fp64(int op, int rnd) const;
    // Uniform FP-leaf accounting (High-4): every FP leaf executed in fast
    // mode is counted.  `approximate_result` marks leaves whose result can
    // differ from sm_120 (arithmetic/conversions); shared-native leaves
    // (FRND/FMNMX/FSEL/FSETP) count fast_fp_ops but keep any_fast_fp false.
    // Inline: called per-lane on the fast hot path.
    void note_fast_leaf(bool approximate_result) {
        ++fast_stats_.fast_fp_ops;
        if (approximate_result) fast_stats_.any_fast_fp = true;
    }

    // --- detection --------------------------------------------------------
    Status detect_deadlock(CtaState& cta, const WarpState& w,
                           std::uint64_t pc);

    // --- Phase 7 debug support -------------------------------------------
    // True while a debug step_group is running so do_memory records the
    // group's committed lane accesses into debug_step_accesses_.
    bool debug_capture_ = false;
    std::vector<StepMemAccess> debug_step_accesses_;

    const Kernel& kernel_;
    const LaunchEnv& env_;
    std::vector<CtaState> ctas_;
    // Phase 6 memory service (owned, or shared across parallel workers via a
    // no-op-deleter shared_ptr).
    std::shared_ptr<MemoryService> memory_;
    // Phase 6 Step 2B: per-SM L1TEX issue state (trace-only).
    SmL1TexState l1tex_state_;
    Mod4SubcoreMapper subcore_mapper_;
    // Phase 6 Step 2C: trace-only L2 event engine (cross-SM serialization).
    // Shared across parallel workers at launch level (High-3) so request/
    // completion/event ids are globally unique; owned otherwise.
    std::shared_ptr<L2EventEngine> l2_engine_;
    bool l2_engine_enabled_ = false;
    // True when the L2 engine is the launch-level shared engine: workers must
    // NOT drain it (a drain consumes every pending request, including other
    // workers' in-flight ones); the launch drains once after all workers join.
    bool l2_engine_shared_ = false;
    // Phase 6 Step 2D: happens-before data-race detector (trace-only).
    std::shared_ptr<RaceDetector> race_detector_;
    // Phase 6 Step 2D: deterministic race-event buffer (see RaceEvent).  The
    // interpreter appends events here in execution order; the run result
    // replays them sorted by (cta_id, ordinal) into the detector.
    std::vector<RaceEvent> race_log_;
    // Per-CTA ordinal counter for race_log_ events.
    std::map<std::uint32_t, std::uint64_t> race_ordinal_;
    // Phase 6 Step 2C (High-2): buffered L2 request descriptors (see
    // L2RequestDescriptor).  Workers append; the launch-level drain sorts and
    // drives the single-threaded L2 engine after all workers join.
    std::vector<L2RequestDescriptor> l2_log_;
    std::map<std::uint32_t, std::uint64_t> l2_ordinal_;
    // Emitted memory events (trace-only; functional results unchanged).
    std::vector<MemoryEvent> memory_events_;
    std::uint64_t limit_;
    std::uint64_t executed_ = 0;
    // Phase 10 hotspot profile accumulator (populated only when
    // options_.collect_hotspots).  See Result::pc_hotspots.
    std::map<std::uint64_t, std::uint64_t> pc_hotspots_;
    std::vector<std::string> trace_;
    bool report_trace_ = false;
    // Phase 5.5 execution mode + fast accounting (fixed at construction).
    const RunOptions options_;
    FastExecutionStats fast_stats_;
    // Round-robin scheduler cursors (High-1): a monotonically advancing
    // cursor over (cta, warp) so no runnable warp is starved.  The cursor
    // wraps; each next_group starts from the previous position + 1.
    std::uint64_t rr_ = 0;
};

}  // namespace semu
