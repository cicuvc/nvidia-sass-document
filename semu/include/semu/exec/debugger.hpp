#pragma once

#include <cstdint>
#include <array>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <semu/decoder/decoder.hpp>
#include <semu/interpreter/interpreter.hpp>
#include <semu/memory/memory.hpp>
#include <semu/core/status.hpp>

// Phase 7 debug session (SIM_PLAN Phase 7 — single-step debugger interface).
//
// DebugSession drives ONE interpreter instance (forced to worker_count == 1:
// deterministic, reproducible stepping) through the public C++ API.  Every
// capability — step / continue / breakpoints / watchpoints / state view and
// modify / warp-step / fault-stop / instruction limit — is implemented on top
// of the public Interpreter step surface (step_group), never through the
// profiler and never by reaching around the backend.
//
// Semantics summary:
//   step()            executes exactly one dynamic warp instruction (ignores
//                     breakpoints); stops BEFORE a decode-only instruction.
//   step_n(n)         step n times, stopping early on any stop condition.
//   continue_run()    executes groups until a breakpoint (stop BEFORE the
//                     matched word), an executed instruction that hits a
//                     watchpoint, a fault, the instruction limit, or the
//                     whole launch finishes.  After a breakpoint stop the
//                     next continue steps over the matched word once.
//   set_focus()       restricts scheduling to one (cta, warp) pair (warp
//                     step); clearing it restores the whole launch.
//
// The session keeps a live Interpreter whose CtaState (GPR / UR / predicate /
// lane PC / barrier / sync state), MemoryService (global / constant / shared /
// local bytes) and pending memory-op groups are exposed for view and modify.

namespace semu {

// ---------------------------------------------------------------------------
// Breakpoints
// ---------------------------------------------------------------------------

enum class BreakpointKind : std::uint8_t {
    kPc = 0,       // match the byte PC (16-byte aligned word boundary)
    kMnemonic = 1, // match the decoded mnemonic (e.g. "STG")
};

struct Breakpoint {
    std::uint64_t id = 0;
    BreakpointKind kind = BreakpointKind::kPc;
    std::uint64_t pc = 0;      // kPc target (byte address)
    std::string mnemonic;      // kMnemonic target
    bool enabled = true;
    // Conditional filters: only fire when the executing group matches.
    std::optional<std::uint32_t> cta;        // grid-linear CTA id
    std::optional<std::uint32_t> warp;       // warp id within the CTA
    std::optional<std::uint32_t> lane_mask;  // require group mask & lane_mask

    // `f_mnemonic` is the decoded mnemonic of the group about to execute.
    // A mnemonic breakpoint matches when it EQUALS the target (round 2
    // re-review Blocker-1: previously only non-emptiness was checked, so a
    // `break mnem STG` fired on every instruction).
    bool matches(std::uint32_t f_cta, std::uint32_t f_warp,
                 std::uint64_t f_pc, std::uint32_t f_mask,
                 const std::string& f_mnemonic) const;
    std::string describe() const;
};

// ---------------------------------------------------------------------------
// Watchpoints
// ---------------------------------------------------------------------------

enum WatchKind : std::uint32_t {
    WK_READ = 1,     // loads
    WK_WRITE = 2,    // stores
    WK_ATOMIC = 4,   // atomic read-modify-write
};

struct Watchpoint {
    std::uint64_t id = 0;
    AddressSpace space = AddressSpace::kGlobal;
    std::uint64_t base = 0;   // global buffer offset / shared / local offset
    std::uint64_t size = 0;   // byte range [base, base+size); size >= 1
    std::uint32_t kind = WK_READ | WK_WRITE | WK_ATOMIC;
    bool enabled = true;
    std::optional<std::uint32_t> cta;
    std::optional<std::uint32_t> warp;
    std::optional<std::uint32_t> lane_mask;

    // True when a lane access [addr, addr+width) with the given kind flags
    // hits this watchpoint (range intersection + kind + lane conditions).
    bool hits(std::uint64_t addr, std::uint64_t width,
              std::uint32_t kind_flags, std::uint32_t lane,
              std::uint32_t f_cta, std::uint32_t f_warp,
              std::uint32_t f_mask) const;
    std::string describe() const;
};

// ---------------------------------------------------------------------------
// Step record
// ---------------------------------------------------------------------------

enum class ChangeKind : std::uint8_t {
    kGpr = 0,               // per-lane general-purpose register (lane set)
    kUniformReg,            // warp-uniform register (lane = -1)
    kPredicate,             // per-lane predicate P0..P6
    kUniformPredicate,      // warp-uniform UPred (lane = -1)
    kPc,                    // per-lane PC
    kActive,                // per-lane active flag
    kExited,                // per-lane exited flag
};

struct RegisterChange {
    ChangeKind kind = ChangeKind::kGpr;
    int lane = -1;             // -1 = warp-uniform
    int index = 0;             // register / predicate index (pc uses 0)
    std::uint64_t old_value = 0;
    std::uint64_t new_value = 0;
    std::string describe() const;
};

enum class DebugStopReason : std::uint8_t {
    kStepped = 0,            // an instruction executed normally
    kPcBreakpoint,           // stopped BEFORE a PC breakpoint (no execution)
    kMnemonicBreakpoint,     // stopped BEFORE a mnemonic breakpoint
    kWatchpoint,             // an executed instruction hit a watchpoint
    kUnsupported,            // stopped BEFORE a decode-only instruction
    kFault,                  // the executed group produced a runtime fault
    kLimit,                  // dynamic instruction limit reached (suspended)
    kFocusBlocked,           // warp-step focus has no eligible group, but the
                             // launch is NOT done (another warp is runnable);
                             // clearing/re-targeting focus can continue.
    kDone,                   // no runnable groups remain (launch finished)
};

const char* to_string(DebugStopReason reason);

struct WatchHit {
    std::uint64_t watchpoint_id = 0;
    std::uint32_t lanes = 0;       // lanes whose access matched this watchpoint
    AddressSpace space = AddressSpace::kGlobal;
    std::uint64_t address = 0;
    std::uint64_t width = 0;
    bool write = false;
    bool atomic = false;
};

struct DebugStepInfo {
    DebugStopReason reason = DebugStopReason::kStepped;
    std::string kernel_name;
    std::uint32_t cta = 0;          // grid-linear CTA id
    std::uint32_t warp = 0;         // warp id
    std::uint64_t pc = 0;           // executed / stopped-at word address
    std::uint32_t active_mask = 0;  // lanes issued this group
    DecodedInstruction instruction; // decoded word at pc
    std::vector<RegisterChange> reg_diffs;     // state changed by the step
    std::vector<StepMemAccess> accesses;       // committed lane memory accesses
    std::vector<WatchHit> watch_hits;          // non-empty on kWatchpoint
    std::optional<Fault> fault;                // kFault / kUnsupported / kLimit
    std::uint64_t breakpoint_id = 0;           // fired breakpoint (0 = n/a)
    std::uint64_t dynamic_instructions = 0;    // executed count after the step

    // Single-line human summary (CLI / traces).
    std::string summary() const;
    // Fully deterministic serialization of every reproducible field (used to
    // prove trace reproducibility).  The session can be replayed byte-for-
    // byte identical from the same setup because stepping is single-worker.
    std::string canonical() const;
};

// ---------------------------------------------------------------------------
// DebugSession
// ---------------------------------------------------------------------------

// Scope disambiguating shared/local memory windows (Blocker, Phase 7
// re-review).  shared memory is per-CTA; local memory in this sim is a
// PER-WARP window (WarpState::local): all lanes of a warp share one `local`
// buffer, and a per-thread frame lives inside it at a PROGRAM-COMPUTED byte
// offset (typically lane*frame_size folded into the SASS address by the
// compiler).  The debugger addresses that window by RAW BYTE OFFSET — there
// is no separate per-lane backing and NO scope.lane dimension (High-1,
// round 2 re-review): the previous `scope.lane` field never participated in
// addressing and only misled callers into thinking lane 0 and lane 1 could
// point at different bytes at the same offset.  global/constant addresses are
// launch-wide and need no scope.
//
//   shared read/write  -> REQUIRE scope.cta (offset into that CTA's window)
//   local read/write   -> REQUIRE scope.cta + scope.warp (offset into that
//                         warp's per-warp window)
//
// Missing scope on a scoped space is an error — there is NO first-match
// scan, so a write can never silently modify an unintended window.
struct MemoryScope {
    std::optional<std::uint32_t> cta;    // shared/local: owning CTA id
    std::optional<std::uint32_t> warp;   // local: owning warp id
};

// GDB-style step-over identity: while continue resumes past a breakpoint it
// remembers the (cta, warp, pc) at which we stopped, and breakpoint matching
// is suppressed for that exact group until it executes.  The PC is a FULL
// 64-bit word address (Medium, Phase 7 re-review): the previous uint32_t
// truncation collapsed high PCs.  Extracted as a plain public value type so
// the identity comparison is directly unit-testable (mutation gate against a
// uint32_t regression — round 2 re-review Medium-1).
struct SuspendBp {
    std::uint32_t cta = 0;
    std::uint32_t warp = 0;
    std::uint64_t pc = 0;
    bool matches(std::uint32_t cta, std::uint32_t warp,
                 std::uint64_t pc) const {
        return this->cta == cta && this->warp == warp && this->pc == pc;
    }
};

class DebugSession {
public:
    // Begin a debug session for a kernel.  `options.worker_count` is forced
    // to 1 (deterministic single-worker stepping — reproducibility contract).
    // `instruction_limit` caps dynamic instructions; the session suspends AT
    // the limit with the state fully inspectable.
    static StatusOr<DebugSession> begin(const Kernel& kernel,
                                        const LaunchEnv& env,
                                        const RunOptions& options,
                                        std::uint64_t instruction_limit =
                                            1000000);

    ~DebugSession();
    DebugSession(DebugSession&&) noexcept;
    DebugSession& operator=(DebugSession&&) noexcept;
    DebugSession(const DebugSession&) = delete;
    DebugSession& operator=(const DebugSession&) = delete;

    // --- breakpoints / watchpoints ----------------------------------------
    StatusOr<std::uint64_t> add_breakpoint(const Breakpoint& bp);
    Status remove_breakpoint(std::uint64_t id);
    void clear_breakpoints();
    StatusOr<std::uint64_t> add_watchpoint(const Watchpoint& wp);
    Status remove_watchpoint(std::uint64_t id);
    void clear_watchpoints();
    const std::vector<Breakpoint>& breakpoints() const;
    const std::vector<Watchpoint>& watchpoints() const;
    std::string badges() const;  // "bp:0x30,w:g:0x40" CLI line

    // --- limits / focus ----------------------------------------------------
    void set_instruction_limit(std::uint64_t n);
    std::uint64_t instruction_limit() const;
    // Warp step: restrict scheduling to one (cta_id, warp_id); nullopt
    // restores the whole launch.  A non-null target is validated against the
    // live launch (the (cta, warp) must exist) and rejected with Status
    // otherwise — a nonexistent focus is a structured error, never a silent
    // "the launch is done" (Blocker, Phase 7 re-review).
    Status set_focus(std::optional<std::pair<std::uint32_t, std::uint32_t>> f);
    const std::optional<std::pair<std::uint32_t, std::uint32_t>>& focus()
        const;

    // --- stepping ----------------------------------------------------------
    DebugStepInfo step();                    // one dynamic warp instruction
    DebugStepInfo step_n(std::uint64_t n);   // n instructions, stop early
    DebugStepInfo continue_run();            // until stop condition / end

    // --- session state -----------------------------------------------------
    std::uint64_t executed_count() const;
    bool finished() const;      // kDone reached (all warps exited cleanly)
    bool faulted() const;       // a terminal fault stopped the session
    const std::optional<Fault>& fault() const;
    const std::vector<CtaState>& ctas() const;      // live interpreter state
    StatusOr<std::size_t> cta_index(std::uint32_t cta_id) const;

    // --- register / state view + modify -----------------------------------
    Status read_gpr(std::uint32_t cta_id, std::uint32_t warp, int lane,
                    int reg, std::uint32_t* out) const;
    Status write_gpr(std::uint32_t cta_id, std::uint32_t warp, int lane,
                     int reg, std::uint32_t value);
    Status read_ur(std::uint32_t cta_id, std::uint32_t warp, int reg,
                   std::uint32_t* out) const;
    Status write_ur(std::uint32_t cta_id, std::uint32_t warp, int reg,
                    std::uint32_t value);
    Status read_pred(std::uint32_t cta_id, std::uint32_t warp, int lane,
                     int pred, bool* out) const;
    Status write_pred(std::uint32_t cta_id, std::uint32_t warp, int lane,
                      int pred, bool value);
    Status read_upred(std::uint32_t cta_id, std::uint32_t warp, int pred,
                      bool* out) const;
    Status write_upred(std::uint32_t cta_id, std::uint32_t warp, int pred,
                       bool value);
    StatusOr<std::uint64_t> read_pc(std::uint32_t cta_id, std::uint32_t warp,
                                    int lane) const;
    Status write_pc(std::uint32_t cta_id, std::uint32_t warp, int lane,
                    std::uint64_t pc);
    StatusOr<std::uint32_t> read_special(std::uint32_t cta_id,
                                         std::uint32_t warp, int lane,
                                         SpecialReg sr) const;

    // --- memory / barrier / scoreboard / pending view ---------------------
    // Global addresses use the interpreter's global-buffer byte offset; shared
    // and local use their byte offsets within an EXPLICITLY scoped window (see
    // MemoryScope — required for shared/local, never a first-match scan).  All
    // accesses are bounds-checked with overflow-safe (subtractive) range
    // arithmetic.  global/constant ignore the scope.
    Status read_memory(AddressSpace space, std::uint64_t address,
                       std::uint64_t len, std::vector<std::uint8_t>* out,
                       const MemoryScope& scope = MemoryScope{}) const;
    Status write_memory(AddressSpace space, std::uint64_t address,
                        const std::vector<std::uint8_t>& bytes,
                        const MemoryScope& scope = MemoryScope{});
    // Named barriers of a CTA (map: barrier id -> state).
    StatusOr<std::map<std::uint32_t, CtaState::NamedBarrier>> barriers(
        std::uint32_t cta_id) const;
    // Logical pending memory-op scoreboard (cp.async / DEPBAR groups).
    StatusOr<std::uint64_t> pending_groups() const;
    StatusOr<std::size_t> pending_ops(std::uint64_t group) const;
    // Decode the word at a byte PC (instruction / scoreboard inspection; std
    // DecodedInstruction::schedule carries the scoreboard bits).
    StatusOr<DecodedInstruction> decode_at(std::uint64_t pc) const;
    // Full multi-line text state dump (CLI `info state`).
    std::string state_report() const;

private:
    DebugSession() = default;

    // Snapshot of one warp's observable state (used for register diffs).
    struct WarpSnapshot {
        std::array<std::uint64_t, kNumUrs> ur{};
        std::array<bool, kNumUpreds> upred{};
        std::array<std::array<std::uint32_t, kNumGprs>, kLanesPerWarp> gpr{};
        std::array<std::array<bool, 7>, kLanesPerWarp> pred{};
        std::array<std::uint64_t, kLanesPerWarp> pc{};
        std::array<bool, kLanesPerWarp> active{};
        std::array<bool, kLanesPerWarp> exited{};
    };
    void snapshot_warp(const WarpState& ws, WarpSnapshot* out) const;
    void diff_warp(const WarpSnapshot& before, const WarpState& now,
                   std::vector<RegisterChange>* out) const;

    // One step_group drive.  Executes exactly one candidate group (subject to
    // focus / pre-exec veto), fills `out` and snapshots the executed warp via
    // `snapshot` for the register diff.  `continue_mode` enables breakpoint +
    // watchpoint stops.  The session terminates (kFault / kLimit / kDone)
    // once reached; later drives return the same terminal info.
    bool drive_group(bool continue_mode, WarpSnapshot* snapshot,
                     DebugStepInfo* out);

    std::unique_ptr<Interpreter> interp_;
    std::uint64_t limit_ = 0;
    std::vector<Breakpoint> breakpoints_;
    std::vector<Watchpoint> watchpoints_;
    std::optional<std::pair<std::uint32_t, std::uint32_t>> focus_;
    std::optional<Fault> terminal_fault_;   // fault/limit terminal stop
    bool done_ = false;                      // launch finished
    // While continue resumes past a breakpoint, this remembers the
    // (cta, warp, pc) at which we stopped; breakpoint matching is suppressed
    // for that exact group until it executes (GDB-style step-over).  The PC is
    // kept as a full 64-bit word address (Medium, Phase 7 re-review): the
    // previous uint32_t truncation collapsed high PCs.  Identity comparison
    // lives in the public SuspendBp::matches (round 2 re-review Medium-1).
    std::optional<SuspendBp> suspend_bp_{};
    // Breakpoints and watchpoints share ONE id allocator so ids are unique
    // across both kinds (Medium, Phase 7 re-review): `del <id>` is then
    // unambiguous instead of always hitting the breakpoint first.
    std::uint64_t next_id_ = 1;
};

}  // namespace semu