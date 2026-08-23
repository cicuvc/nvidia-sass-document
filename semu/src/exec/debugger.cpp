// Phase 7 debug session implementation (see debugger.hpp for the contract).
//
// Everything here drives the public Interpreter API (step_group with an
// eligible schedule filter and a pre-exec veto); it never touches the
// profiler and never reaches around the backend.  The session is pinned to
// worker_count == 1 so identical setups + identical command sequences replay
// byte-for-byte.

#include <semu/exec/debugger.hpp>

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>
#include <iomanip>
#include <sstream>

#include <semu/core/capability.hpp>

namespace semu {

namespace {

std::string hex64(std::uint64_t v) {
    std::ostringstream os;
    os << "0x" << std::hex << v;
    return os.str();
}

// RZ (255) reads as 0 and cannot be written.
constexpr int kRegRzLocal = 255;

}  // namespace

// ---------------------------------------------------------------------------
// Descriptions / serialization
// ---------------------------------------------------------------------------

const char* to_string(DebugStopReason reason) {
    switch (reason) {
        case DebugStopReason::kStepped: return "stepped";
        case DebugStopReason::kPcBreakpoint: return "pc-breakpoint";
        case DebugStopReason::kMnemonicBreakpoint: return "mnemonic-breakpoint";
        case DebugStopReason::kWatchpoint: return "watchpoint";
        case DebugStopReason::kUnsupported: return "unsupported";
        case DebugStopReason::kFault: return "fault";
        case DebugStopReason::kLimit: return "limit";
        case DebugStopReason::kFocusBlocked: return "focus-blocked";
        case DebugStopReason::kDone: return "done";
    }
    return "?";
}

bool Breakpoint::matches(std::uint32_t f_cta, std::uint32_t f_warp,
                         std::uint64_t f_pc, std::uint32_t f_mask,
                         const std::string& f_mnemonic) const {
    if (!enabled) return false;
    if (cta && *cta != f_cta) return false;
    if (warp && *warp != f_warp) return false;
    if (kind == BreakpointKind::kPc) {
        if (pc != f_pc) return false;
    } else {
        // Blocker (Phase 7 re-review, round 2): a mnemonic breakpoint must
        // compare the DECODED mnemonic of the group about to execute.  The
        // previous check only required a non-empty target, so `break mnem
        // STG` fired on EVERY instruction (e.g. the entry S2R of kS2rExit).
        if (f_mnemonic.empty() || mnemonic != f_mnemonic) return false;
    }
    if (lane_mask && (f_mask & *lane_mask) == 0) return false;
    return true;
}

std::string Breakpoint::describe() const {
    std::ostringstream os;
    os << "#" << id << " ";
    if (kind == BreakpointKind::kPc) {
        os << "pc " << hex64(pc);
    } else {
        os << "mnem " << mnemonic;
    }
    if (cta) os << " cta=" << *cta;
    if (warp) os << " warp=" << *warp;
    if (lane_mask) os << " lane=" << hex64(*lane_mask);
    if (!enabled) os << " (disabled)";
    return os.str();
}

bool Watchpoint::hits(std::uint64_t addr, std::uint64_t width,
                      std::uint32_t kind_flags, std::uint32_t lane,
                      std::uint32_t f_cta, std::uint32_t f_warp,
                      std::uint32_t f_mask) const {
    if (!enabled) return false;
    if ((kind & kind_flags) == 0) return false;
    if (cta && *cta != f_cta) return false;
    if (warp && *warp != f_warp) return false;
    if (lane_mask && (f_mask & *lane_mask) == 0) return false;
    if (lane_mask && ((1u << (lane % 32)) & *lane_mask) == 0) return false;
    if (size == 0) return false;
    // Range intersection [addr, addr+width) ∩ [base, base+size), computed
    // with SUBTRACTIVE checks so `base + size` / `addr + width` can never
    // wrap (Medium, Phase 7 re-review).  base+size overflow is already
    // rejected at add_watchpoint time; addr+width here is a per-lane access.
    if (addr < base) {
        // The access starts below the watchpoint: it intersects iff the
        // watchpoint's base lies inside the access, i.e. base - addr < width.
        return base - addr < width;
    }
    // The access starts inside/at the watchpoint: intersects iff it starts
    // before the watchpoint's end, i.e. addr - base < size.
    return addr - base < size;
}

std::string Watchpoint::describe() const {
    std::ostringstream os;
    os << "#" << id << " " << to_string(space) << " "
       << hex64(base) << "..";
    // Overflow-safe end (add_watchpoint already rejects wrapping ranges; this
    // is defensive for unvalidated copies).
    os << ((base <= UINT64_MAX - size) ? hex64(base + size)
                                       : "<uint64-overflow>")
       << " (";
    if (kind & WK_READ) os << "r";
    if (kind & WK_WRITE) os << "w";
    if (kind & WK_ATOMIC) os << "a";
    os << ")";
    if (cta) os << " cta=" << *cta;
    if (warp) os << " warp=" << *warp;
    if (lane_mask) os << " lane=" << hex64(*lane_mask);
    if (!enabled) os << " (disabled)";
    return os.str();
}

std::string RegisterChange::describe() const {
    std::ostringstream os;
    switch (kind) {
        case ChangeKind::kGpr:
            os << "R" << index;
            break;
        case ChangeKind::kUniformReg:
            os << "UR" << index;
            break;
        case ChangeKind::kPredicate:
            os << "P" << index;
            break;
        case ChangeKind::kUniformPredicate:
            os << "UP" << index;
            break;
        case ChangeKind::kPc:
            os << "PC";
            break;
        case ChangeKind::kActive:
            os << "active";
            break;
        case ChangeKind::kExited:
            os << "exited";
            break;
    }
    if (lane >= 0) os << "[l" << lane << "]";
    os << " " << hex64(old_value) << " -> " << hex64(new_value);
    return os.str();
}

std::string DebugStepInfo::summary() const {
    std::ostringstream os;
    os << to_string(reason) << " cta=" << cta << " warp=" << warp
       << " pc=" << hex64(pc) << " mask=" << std::hex
       << std::setw(8) << std::setfill('0') << active_mask << std::dec;
    if (instruction.mnemonic != isa::Mnemonic::kUnknown)
        os << " "
           << Decoder::instance().disassemble(instruction.word,
                                              /*full=*/true);
    if (watch_hits.size())
        os << " watch=" << watch_hits.size() << " hit(s)";
    if (reg_diffs.size()) os << " diff=" << reg_diffs.size();
    if (accesses.size()) os << " mem=" << accesses.size();
    if (fault) os << " fault=" << to_string(fault->kind());
    return os.str();
}

std::string DebugStepInfo::canonical() const {
    std::ostringstream os;
    os << to_string(reason) << "|" << kernel_name << "|" << cta << "|" << warp
       << "|" << pc << "|" << active_mask << "|" << isa::mnemonic_name(instruction.mnemonic)
       << "|" << instruction.word.lo << "|" << instruction.word.hi << "|"
       << breakpoint_id << "|" << dynamic_instructions;
    // Register diffs (fixed natural order).
    os << "|r[";
    for (std::size_t i = 0; i < reg_diffs.size(); ++i) {
        if (i) os << ",";
        const auto& c = reg_diffs[i];
        os << static_cast<int>(c.kind) << ":" << c.lane << ":" << c.index
           << ":" << c.old_value << ":" << c.new_value;
    }
    os << "]|a[";
    for (std::size_t i = 0; i < accesses.size(); ++i) {
        if (i) os << ",";
        const auto& a = accesses[i];
        os << a.lane << ":" << static_cast<int>(a.space) << ":" << a.address
           << ":" << a.width << ":" << a.write << ":" << a.atomic;
    }
    os << "]|w[";
    for (std::size_t i = 0; i < watch_hits.size(); ++i) {
        if (i) os << ",";
        os << watch_hits[i].watchpoint_id << ":" << watch_hits[i].lanes;
    }
    os << "]|f" << (fault ? static_cast<int>(fault->kind()) : -1);
    return os.str();
}

// ---------------------------------------------------------------------------
// Breakpoint / watchpoint management
// ---------------------------------------------------------------------------

StatusOr<std::uint64_t> DebugSession::add_breakpoint(const Breakpoint& bp) {
    if (!(bp.kind == BreakpointKind::kPc || bp.kind == BreakpointKind::kMnemonic)) {
        return StatusOr<std::uint64_t>::failure(Error::invalid_argument(
            "breakpoint kind must be pc or mnemonic"));
    }
    if (bp.kind == BreakpointKind::kPc && (bp.pc % 16 != 0)) {
        return StatusOr<std::uint64_t>::failure(Error::invalid_argument(
            "pc breakpoint must be at a 16-byte instruction boundary"));
    }
    if (bp.kind == BreakpointKind::kMnemonic && bp.mnemonic.empty()) {
        return StatusOr<std::uint64_t>::failure(Error::invalid_argument(
            "mnemonic breakpoint needs a mnemonic"));
    }
    Breakpoint copy = bp;
    // Medium (Phase 7 re-review): breakpoints and watchpoints draw from ONE
    // id pool so ids are globally unique across both kinds.
    copy.id = next_id_++;
    if (copy.id == 0) copy.id = next_id_++;
    breakpoints_.push_back(std::move(copy));
    return StatusOr<std::uint64_t>::success(breakpoints_.back().id);
}

Status DebugSession::remove_breakpoint(std::uint64_t id) {
    const auto before = breakpoints_.size();
    breakpoints_.erase(
        std::remove_if(breakpoints_.begin(), breakpoints_.end(),
                       [id](const Breakpoint& b) { return b.id == id; }),
        breakpoints_.end());
    if (breakpoints_.size() == before) {
        return Status::failure(Error::not_found(
            "breakpoint #" + std::to_string(id) + " not found"));
    }
    return Status::success();
}

void DebugSession::clear_breakpoints() { breakpoints_.clear(); }

StatusOr<std::uint64_t> DebugSession::add_watchpoint(const Watchpoint& wp) {
    if (wp.size == 0) {
        return StatusOr<std::uint64_t>::failure(Error::invalid_argument(
            "watchpoint size must be >= 1 byte"));
    }
    // Medium (Phase 7 re-review): reject ranges whose [base, base+size) span
    // would wrap uint64 (hits() relies on a non-wrapping range).
    if (wp.base > UINT64_MAX - wp.size) {
        return StatusOr<std::uint64_t>::failure(Error::invalid_argument(
            "watchpoint range [base, base+size) overflows uint64"));
    }
    Watchpoint copy = wp;
    copy.id = next_id_++;
    if (copy.id == 0) copy.id = next_id_++;
    watchpoints_.push_back(std::move(copy));
    return StatusOr<std::uint64_t>::success(watchpoints_.back().id);
}

Status DebugSession::remove_watchpoint(std::uint64_t id) {
    const auto before = watchpoints_.size();
    watchpoints_.erase(
        std::remove_if(watchpoints_.begin(), watchpoints_.end(),
                       [id](const Watchpoint& w) { return w.id == id; }),
        watchpoints_.end());
    if (watchpoints_.size() == before) {
        return Status::failure(Error::not_found(
            "watchpoint #" + std::to_string(id) + " not found"));
    }
    return Status::success();
}

void DebugSession::clear_watchpoints() { watchpoints_.clear(); }

const std::vector<Breakpoint>& DebugSession::breakpoints() const {
    return breakpoints_;
}
const std::vector<Watchpoint>& DebugSession::watchpoints() const {
    return watchpoints_;
}

std::string DebugSession::badges() const {
    std::ostringstream os;
    for (const auto& b : breakpoints_)
        if (b.enabled)
            os << (os.tellp() ? "," : "") << (b.kind == BreakpointKind::kPc
                                                  ? "bp:" + hex64(b.pc)
                                                  : "bm:" + b.mnemonic);
    for (const auto& w : watchpoints_) {
        if (!w.enabled) continue;
        std::ostringstream t;
        t << "w:" << to_string(w.space) << ":" << hex64(w.base) << "-"
          << (w.base <= UINT64_MAX - w.size ? hex64(w.base + w.size)
                                            : "<overflow>");
        if (os.tellp()) os << ",";
        os << t.str();
    }
    return os.str();
}

// ---------------------------------------------------------------------------
// Limits / focus
// ---------------------------------------------------------------------------

void DebugSession::set_instruction_limit(std::uint64_t n) {
    limit_ = n;
    // Raising the limit past the current execution resumes a session that had
    // stopped at the instruction limit (clear the terminal stop).
    if (terminal_fault_ &&
        terminal_fault_->kind() == FaultKind::kInstructionLimit &&
        executed_count() < n) {
        terminal_fault_.reset();
        done_ = false;
    }
}
std::uint64_t DebugSession::instruction_limit() const { return limit_; }

Status DebugSession::set_focus(
    std::optional<std::pair<std::uint32_t, std::uint32_t>> f) {
    // Blocker (Phase 7 re-review): a nonexistent (cta, warp) focus is
    // REJECTED structurally.  Otherwise `focus 99.0` would silently behave
    // like "the launch is done" — the very confusion this round removes.
    if (f) {
        if (!interp_) {
            return Status::failure(Error::illegal_state("no interpreter"));
        }
        const auto& ctas = interp_->ctas();
        bool found = false;
        for (const auto& c : ctas) {
            if (static_cast<std::uint32_t>(c.cta_id) != f->first) continue;
            for (const auto& ws : c.warps) {
                if (static_cast<std::uint32_t>(ws.warp_id) == f->second) {
                    found = true;
                    break;
                }
            }
        }
        if (!found) {
            return Status::failure(Error::invalid_argument(
                "focus cta=" + std::to_string(f->first) + " warp=" +
                std::to_string(f->second) +
                " does not exist in this launch"));
        }
    }
    focus_ = std::move(f);
    return Status::success();
}
const std::optional<std::pair<std::uint32_t, std::uint32_t>>&
DebugSession::focus() const {
    return focus_;
}

// ---------------------------------------------------------------------------
// Construction / destruction
// ---------------------------------------------------------------------------

StatusOr<DebugSession> DebugSession::begin(const Kernel& kernel,
                                           const LaunchEnv& env,
                                           const RunOptions& options,
                                           std::uint64_t instruction_limit) {
    // Single worker is a Phase 7 contract: reproducible stepping.
    RunOptions opts = options;
    opts.worker_count = 1;
    DebugSession s;
    s.limit_ = instruction_limit;
    // The session owns the limit (set_instruction_limit can raise it at
    // runtime), so the interpreter's internal cap is disabled.
    s.interp_ = std::make_unique<Interpreter>(kernel, env, UINT64_MAX, opts);
    return StatusOr<DebugSession>::success(std::move(s));
}

DebugSession::~DebugSession() = default;
DebugSession::DebugSession(DebugSession&&) noexcept = default;
DebugSession& DebugSession::operator=(DebugSession&&) noexcept = default;

// ---------------------------------------------------------------------------
// Session state
// ---------------------------------------------------------------------------

std::uint64_t DebugSession::executed_count() const {
    return interp_ ? interp_->executed() : 0;
}
bool DebugSession::finished() const { return done_; }
bool DebugSession::faulted() const { return terminal_fault_.has_value(); }
const std::optional<Fault>& DebugSession::fault() const {
    return terminal_fault_;
}

const std::vector<CtaState>& DebugSession::ctas() const {
    static const std::vector<CtaState> kEmpty{};
    return interp_ ? interp_->ctas() : kEmpty;
}

StatusOr<std::size_t> DebugSession::cta_index(std::uint32_t cta_id) const {
    if (!interp_) {
        return StatusOr<std::size_t>::failure(
            Error::illegal_state("no interpreter"));
    }
    const auto& ctas = interp_->ctas();
    for (std::size_t i = 0; i < ctas.size(); ++i) {
        if (static_cast<std::uint32_t>(ctas[i].cta_id) == cta_id)
            return StatusOr<std::size_t>::success(i);
    }
    return StatusOr<std::size_t>::failure(
        Error::not_found("CTA " + std::to_string(cta_id) + " not in launch"));
}

// ---------------------------------------------------------------------------
// Snapshot / diff
// ---------------------------------------------------------------------------

void DebugSession::snapshot_warp(const WarpState& ws, WarpSnapshot* out) const {
    for (int u = 0; u < kNumUrs; ++u) out->ur[u] = ws.ur[static_cast<std::size_t>(u)];
    for (int u = 0; u < kNumUpreds; ++u)
        out->upred[u] = ws.upred[static_cast<std::size_t>(u)];
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        const ThreadState& t = ws.threads[static_cast<std::size_t>(lane)];
        for (int r = 0; r < kNumGprs; ++r)
            out->gpr[lane][r] = t.gpr[static_cast<std::size_t>(r)];
        for (int p = 0; p < 7; ++p)
            out->pred[lane][p] = t.pred[static_cast<std::size_t>(p)];
        out->pc[lane] = t.pc;
        out->active[lane] = t.active;
        out->exited[lane] = t.exited;
    }
}

void DebugSession::diff_warp(const WarpSnapshot& before, const WarpState& now,
                             std::vector<RegisterChange>* out) const {
    for (int u = 0; u < kNumUrs; ++u) {
        if (before.ur[u] != now.ur[u]) {
            out->push_back(RegisterChange{
                ChangeKind::kUniformReg, -1, u, before.ur[u], now.ur[u]});
        }
    }
    for (int u = 0; u < kNumUpreds; ++u) {
        if (before.upred[u] != now.upred[u]) {
            out->push_back(RegisterChange{
                ChangeKind::kUniformPredicate, -1, u,
                before.upred[u] ? 1u : 0u, now.upred[u] ? 1u : 0u});
        }
    }
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        const ThreadState& t = now.threads[static_cast<std::size_t>(lane)];
        for (int r = 0; r < kNumGprs; ++r) {
            if (before.gpr[lane][r] != t.gpr[static_cast<std::size_t>(r)]) {
                out->push_back(RegisterChange{
                    ChangeKind::kGpr, lane, r, before.gpr[lane][r],
                    t.gpr[static_cast<std::size_t>(r)]});
            }
        }
        for (int p = 0; p < 7; ++p) {
            if (before.pred[lane][p] != t.pred[static_cast<std::size_t>(p)]) {
                out->push_back(RegisterChange{
                    ChangeKind::kPredicate, lane, p,
                    before.pred[lane][p] ? 1u : 0u,
                    t.pred[static_cast<std::size_t>(p)] ? 1u : 0u});
            }
        }
        if (before.pc[lane] != t.pc)
            out->push_back(RegisterChange{ChangeKind::kPc, lane, 0,
                                          before.pc[lane], t.pc});
        if (before.active[lane] != t.active)
            out->push_back(RegisterChange{ChangeKind::kActive, lane, 0,
                                          before.active[lane] ? 1u : 0u,
                                          t.active ? 1u : 0u});
        if (before.exited[lane] != t.exited)
            out->push_back(RegisterChange{ChangeKind::kExited, lane, 0,
                                          before.exited[lane] ? 1u : 0u,
                                          t.exited ? 1u : 0u});
    }
}

// ---------------------------------------------------------------------------
// One drive step (the primitive behind step / step_n / continue_run).
// ---------------------------------------------------------------------------

// `continue_mode` selects breakpoint handling (step mode ignores them).
// Returns true when the caller must stop (always after one group); fills
// `out` with the StepInfo for the group that stopped.
bool DebugSession::drive_group(bool continue_mode, WarpSnapshot* snapshot,
                               DebugStepInfo* out) {
    *out = DebugStepInfo{};
    if (!interp_) {
        out->reason = DebugStopReason::kDone;
        done_ = true;
        return true;
    }
    // Terminal once a fault / limit fired or the launch finished.
    if (terminal_fault_) {
        out->reason =
            terminal_fault_->kind() == FaultKind::kInstructionLimit
                ? DebugStopReason::kLimit
                : DebugStopReason::kFault;
        out->fault = terminal_fault_;
        out->kernel_name = interp_->kernel().symbol_name;
        out->dynamic_instructions = interp_->executed();
        return true;
    }
    if (done_) {
        out->reason = DebugStopReason::kDone;
        out->kernel_name = interp_->kernel().symbol_name;
        out->dynamic_instructions = interp_->executed();
        return true;
    }
    if (interp_->executed() >= limit_) {
        Fault f(FaultKind::kInstructionLimit,
                "debug instruction limit " + std::to_string(limit_) +
                    " reached (state viewable; use set_instruction_limit to "
                    "raise)");
        terminal_fault_ = f;
        out->reason = DebugStopReason::kLimit;
        out->fault = f;
        out->kernel_name = interp_->kernel().symbol_name;
        out->dynamic_instructions = interp_->executed();
        return true;
    }

    ScheduleFilter* elig_ptr = nullptr;
    ScheduleFilter elig;
    if (focus_) {
        elig = [this](std::uint32_t f_cta, std::uint32_t f_warp) {
            return focus_ && f_cta == focus_->first && f_warp == focus_->second;
        };
        elig_ptr = &elig;
    }

    // The pre-exec veto doubles as the warp snapshot point: called exactly
    // once for the group that step_group is about to execute, before any
    // state changes.  False = stop WITHOUT executing.
    PreExecFilter pre = [&](std::uint32_t cta, std::uint32_t warp,
                            std::uint64_t pc, std::uint32_t mask,
                            const DecodedInstruction& inst) -> bool {
        const auto& ctas = interp_->ctas();
        const std::size_t ci = static_cast<std::size_t>(cta);
        if (ci < ctas.size() && snapshot) {
            snapshot_warp(ctas[ci].warps[static_cast<std::size_t>(warp)],
                          snapshot);
        }
        const std::uint32_t gcta =
            (ci < ctas.size()) ? static_cast<std::uint32_t>(ctas[ci].cta_id)
                               : cta;
        out->kernel_name = interp_->kernel().symbol_name;
        out->cta = gcta;
        out->warp = warp;
        out->pc = pc;
        out->active_mask = mask;
        out->instruction = inst;
        if (!interp_->supports(inst)) {
            Fault f(FaultKind::kUnsupportedInstruction,
                    "decode-only instruction '" +
                        std::string(isa::mnemonic_name(inst.mnemonic)) +
                        "' (" + std::string(isa::variant_class_name(
                                                inst.variant_class)) +
                        ") at pc " + hex64(pc) +
                        " is not implemented; debug stopped before executing");
            f.set_kernel(interp_->kernel().symbol_name).set_pc(pc)
                .set_cta(gcta).set_warp(warp).set_active_mask(mask)
                .set_instruction(inst.word)
                .set_mnemonic(isa::mnemonic_name(inst.mnemonic))
                .set_variant(isa::variant_class_name(inst.variant_class));
            out->fault = f;
            out->reason = DebugStopReason::kUnsupported;
            return false;  // stop before executing
        }
        if (continue_mode) {
            // GDB-style step-over: the group at which a breakpoint stopped is
            // exempt until it has executed.  Identity comparison is the public
            // SuspendBp::matches (round 2 re-review Medium-1).
            const bool bypass =
                suspend_bp_ &&
                suspend_bp_->matches(gcta, warp, pc);
            if (!bypass) {
                for (const auto& bp : breakpoints_) {
                    if (!bp.matches(gcta, warp, pc, mask,
                                    isa::mnemonic_name(inst.mnemonic)))
                        continue;
                    out->reason = bp.kind == BreakpointKind::kPc
                                      ? DebugStopReason::kPcBreakpoint
                                      : DebugStopReason::kMnemonicBreakpoint;
                    out->breakpoint_id = bp.id;
                    suspend_bp_ = SuspendBp{gcta, warp, pc};
                    return false;
                }
            }
        }
        return true;
    };

    StepGroupFrame frame;
    if (!interp_->step_group(&frame, nullptr, nullptr, elig_ptr, &pre)) {
        if (frame.focus_blocked) {
            // Blocker (Phase 7 re-review): the launch still has runnable
            // warps, but the warp-step focus filter excluded all of them.
            // This is NOT launch done — the session must stay alive so
            // clearing / re-targeting focus can continue.
            out->reason = DebugStopReason::kFocusBlocked;
            out->kernel_name = interp_->kernel().symbol_name;
            out->dynamic_instructions = interp_->executed();
            return true;
        }
        // Blocker (Phase 7 re-review, round 2): distinguish a clean Done from
        // a STUCK launch.  The normal runner reports barrier deadlock /
        // no-progress as a fault; the debugger must too.  Previously this
        // unconditionally latched done_ + kDone, silently reporting a
        // barrier-deadlocked launch as a clean completion — violating the
        // fault-stop contract.
        switch (interp_->terminal_state()) {
            case ExecutionTerminalState::kBarrierDeadlock: {
                terminal_fault_ = interp_->barrier_deadlock_fault();
                out->reason = DebugStopReason::kFault;
                out->fault = terminal_fault_;
                out->kernel_name = interp_->kernel().symbol_name;
                out->dynamic_instructions = interp_->executed();
                return true;
            }
            case ExecutionTerminalState::kNoProgress: {
                terminal_fault_ = Fault(
                    FaultKind::kNoProgress,
                    "launch has no runnable group and no barrier waiter "
                    "(stalled); not a clean completion");
                out->reason = DebugStopReason::kFault;
                out->fault = terminal_fault_;
                out->kernel_name = interp_->kernel().symbol_name;
                out->dynamic_instructions = interp_->executed();
                return true;
            }
            default:
                break;  // kDone below.
        }
        done_ = true;
        out->reason = DebugStopReason::kDone;
        out->kernel_name = interp_->kernel().symbol_name;
        // Keep whatever the pre callback recorded (usually the last group);
        // for the all-done case there is no group.
        out->dynamic_instructions = interp_->executed();
        return true;
    }
    if (frame.stopped) {
        // out was filled by `pre` (kUnsupported / breakpoint).
        out->dynamic_instructions = interp_->executed();
        return true;
    }
    if (frame.limit_hit) {
        terminal_fault_ =
            frame.fault.value_or(Fault(FaultKind::kInstructionLimit,
                                       "dynamic instruction limit reached"));
        out->reason = DebugStopReason::kLimit;
        out->fault = terminal_fault_;
        out->kernel_name = interp_->kernel().symbol_name;
        const auto& ctas = interp_->ctas();
        const std::size_t ci = frame.cta;
        if (ci < ctas.size())
            out->cta = static_cast<std::uint32_t>(ctas[ci].cta_id);
        out->warp = frame.warp;
        out->pc = frame.pc;
        out->active_mask = frame.mask;
        out->dynamic_instructions = interp_->executed();
        return true;
    }
    if (frame.fault) {
        terminal_fault_ = frame.fault;
        out->reason = DebugStopReason::kFault;
        out->fault = terminal_fault_;
        out->kernel_name = interp_->kernel().symbol_name;
        const auto& ctas = interp_->ctas();
        const std::size_t ci = frame.cta;
        if (ci < ctas.size())
            out->cta = static_cast<std::uint32_t>(ctas[ci].cta_id);
        out->warp = frame.warp;
        out->pc = frame.pc;
        out->active_mask = frame.mask;
        out->dynamic_instructions = interp_->executed();
        return true;
    }
    // Executed without a fault.
    if (frame.executed) {
        const auto& ctas = interp_->ctas();
        const std::size_t ci = frame.cta;
        if (ci < ctas.size()) {
            out->cta = static_cast<std::uint32_t>(ctas[ci].cta_id);
        }
        out->warp = frame.warp;
        out->pc = frame.pc;
        out->active_mask = frame.mask;
        if (suspend_bp_ && suspend_bp_->matches(out->cta, frame.warp,
                                                frame.pc)) {
            suspend_bp_.reset();  // the breakpointed instruction executed
        }
        if (snapshot && ci < ctas.size() &&
            static_cast<std::size_t>(frame.warp) <
                ctas[ci].warps.size()) {
            diff_warp(*snapshot,
                      ctas[ci].warps[static_cast<std::size_t>(frame.warp)],
                      &out->reg_diffs);
        }
        out->accesses = frame.accesses;
        out->reason = DebugStopReason::kStepped;
        // Watchpoints apply to the executed instruction (continue mode).
        if (continue_mode && !watchpoints_.empty()) {
            for (std::size_t i = 0; i < watchpoints_.size(); ++i) {
                const Watchpoint& w = watchpoints_[i];
                std::uint32_t hit_lanes = 0;
                for (const auto& a : frame.accesses) {
                    const std::uint32_t flags =
                        (a.atomic ? static_cast<std::uint32_t>(WK_ATOMIC)
                                  : 0u) |
                        (a.write ? static_cast<std::uint32_t>(WK_WRITE)
                                 : static_cast<std::uint32_t>(WK_READ));
                    if (w.space != a.space) continue;
                    if (!w.hits(a.address, a.width, flags, a.lane, out->cta,
                                out->warp, out->active_mask))
                        continue;
                    hit_lanes |= (1u << (a.lane % 32));
                }
                if (hit_lanes != 0) {
                    WatchHit h;
                    h.watchpoint_id = w.id;
                    h.lanes = hit_lanes;
                    h.space = w.space;
                    h.write = (w.kind & WK_WRITE) != 0;
                    h.atomic = (w.kind & WK_ATOMIC) != 0;
                    h.width = w.size;
                    h.address = w.base;
                    out->watch_hits.push_back(std::move(h));
                }
            }
            if (!out->watch_hits.empty())
                out->reason = DebugStopReason::kWatchpoint;
        }
    }
    out->dynamic_instructions = interp_->executed();
    return true;
}

// ---------------------------------------------------------------------------
// Stepping
// ---------------------------------------------------------------------------

DebugStepInfo DebugSession::step() {
    WarpSnapshot snap;
    DebugStepInfo info;
    drive_group(/*continue_mode=*/false, &snap, &info);
    return info;
}

DebugStepInfo DebugSession::step_n(std::uint64_t n) {
    DebugStepInfo last;
    for (std::uint64_t i = 0; i < n; ++i) {
        last = step();
        if (last.reason != DebugStopReason::kStepped) break;
    }
    return last;
}

DebugStepInfo DebugSession::continue_run() {
    DebugStepInfo last;
    for (;;) {
        WarpSnapshot snap;
        last = DebugStepInfo{};
        drive_group(/*continue_mode=*/true, &snap, &last);
        if (last.reason == DebugStopReason::kStepped ||
            last.reason == DebugStopReason::kWatchpoint) {
            // A watchpoint IS a stop; kStepped keeps looping.
            if (last.reason == DebugStopReason::kWatchpoint) break;
            continue;
        }
        break;  // breakpoint / unsupported / fault / limit / done
    }
    return last;
}

// ---------------------------------------------------------------------------
// Register / memory / barrier / scoreboard inspection + modification
// ---------------------------------------------------------------------------

Status DebugSession::read_gpr(std::uint32_t cta_id, std::uint32_t warp,
                              int lane, int reg, std::uint32_t* out) const {
    if (reg < 0 || reg >= kNumGprs) {
        return Status::failure(
            Error::invalid_argument("gpr index out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    if (lane < 0 || lane >= kLanesPerWarp) {
        return Status::failure(Error::invalid_argument("no such lane"));
    }
    *out = interp_->ctas()[idx.value()].warps[warp].threads[lane].gpr[reg];
    return Status::success();
}

Status DebugSession::write_gpr(std::uint32_t cta_id, std::uint32_t warp,
                               int lane, int reg, std::uint32_t value) {
    if (reg < 0 || reg >= kNumGprs) {
        return Status::failure(
            Error::invalid_argument("gpr index out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    if (lane < 0 || lane >= kLanesPerWarp) {
        return Status::failure(Error::invalid_argument("no such lane"));
    }
    if (reg == kRegRzLocal) {
        return Status::failure(
            Error::invalid_argument("RZ is read-only (always 0)"));
    }
    interp_->ctas()[idx.value()].warps[warp].threads[lane].gpr[reg] = value;
    return Status::success();
}

Status DebugSession::read_ur(std::uint32_t cta_id, std::uint32_t warp,
                             int reg, std::uint32_t* out) const {
    if (reg < 0 || reg >= kNumUrs) {
        return Status::failure(Error::invalid_argument("ur index out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    *out = interp_->ctas()[idx.value()].warps[warp].ur[reg];
    return Status::success();
}

Status DebugSession::write_ur(std::uint32_t cta_id, std::uint32_t warp,
                              int reg, std::uint32_t value) {
    if (reg < 0 || reg >= kNumUrs) {
        return Status::failure(Error::invalid_argument("ur index out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    interp_->ctas()[idx.value()].warps[warp].ur[reg] = value;
    return Status::success();
}

Status DebugSession::read_pred(std::uint32_t cta_id, std::uint32_t warp,
                               int lane, int pred, bool* out) const {
    if (pred < 0 || pred >= 7) {
        return Status::failure(Error::invalid_argument("predicate out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    if (lane < 0 || lane >= kLanesPerWarp) {
        return Status::failure(Error::invalid_argument("no such lane"));
    }
    *out = interp_->ctas()[idx.value()].warps[warp].threads[lane].pred[pred];
    return Status::success();
}

Status DebugSession::write_pred(std::uint32_t cta_id, std::uint32_t warp,
                                int lane, int pred, bool value) {
    if (pred < 0 || pred >= 7) {
        return Status::failure(Error::invalid_argument("predicate out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    if (lane < 0 || lane >= kLanesPerWarp) {
        return Status::failure(Error::invalid_argument("no such lane"));
    }
    interp_->ctas()[idx.value()].warps[warp].threads[lane].pred[pred] = value;
    return Status::success();
}

Status DebugSession::read_upred(std::uint32_t cta_id, std::uint32_t warp,
                                int pred, bool* out) const {
    if (pred < 0 || pred >= kNumUpreds) {
        return Status::failure(Error::invalid_argument("predicate out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    *out = interp_->ctas()[idx.value()].warps[warp].upred[pred];
    return Status::success();
}

Status DebugSession::write_upred(std::uint32_t cta_id, std::uint32_t warp,
                                 int pred, bool value) {
    if (pred < 0 || pred >= kNumUpreds) {
        return Status::failure(Error::invalid_argument("predicate out of range"));
    }
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    interp_->ctas()[idx.value()].warps[warp].upred[pred] = value;
    return Status::success();
}

StatusOr<std::uint64_t> DebugSession::read_pc(std::uint32_t cta_id,
                                              std::uint32_t warp,
                                              int lane) const {
    auto idx = cta_index(cta_id);
    if (!idx.ok())
        return StatusOr<std::uint64_t>::failure(idx.take_error());
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return StatusOr<std::uint64_t>::failure(
            Error::invalid_argument("no such warp"));
    }
    if (lane < 0 || lane >= kLanesPerWarp) {
        return StatusOr<std::uint64_t>::failure(
            Error::invalid_argument("no such lane"));
    }
    return StatusOr<std::uint64_t>::success(
        interp_->ctas()[idx.value()].warps[warp].threads[lane].pc);
}

Status DebugSession::write_pc(std::uint32_t cta_id, std::uint32_t warp,
                              int lane, std::uint64_t pc) {
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return idx.status();
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return Status::failure(Error::invalid_argument("no such warp"));
    }
    if (lane < 0 || lane >= kLanesPerWarp) {
        return Status::failure(Error::invalid_argument("no such lane"));
    }
    const auto& k = interp_->kernel();
    if (pc % 16 != 0 || pc / 16 >= k.predecoded.size()) {
        return Status::failure(Error::invalid_argument(
            "pc 0x" + hex64(pc) + " is not a valid instruction boundary"));
    }
    interp_->ctas()[idx.value()].warps[warp].threads[lane].pc = pc;
    return Status::success();
}

StatusOr<std::uint32_t> DebugSession::read_special(std::uint32_t cta_id,
                                                   std::uint32_t warp,
                                                   int lane,
                                                   SpecialReg sr) const {
    auto idx = cta_index(cta_id);
    if (!idx.ok()) return StatusOr<std::uint32_t>::failure(idx.take_error());
    if (warp >= interp_->ctas()[idx.value()].warps.size()) {
        return StatusOr<std::uint32_t>::failure(
            Error::invalid_argument("no such warp"));
    }
    if (lane < 0 || lane >= kLanesPerWarp) {
        return StatusOr<std::uint32_t>::failure(
            Error::invalid_argument("no such lane"));
    }
    return StatusOr<std::uint32_t>::success(interp_->special_register_value(
        sr, cta_id, warp, lane));
}

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------

namespace {

// Overflow-safe (subtractive) bounds test for [off, off+len) against a
// window of `size` bytes: true when the range lies entirely inside.
bool in_window(std::uint64_t off, std::uint64_t len, std::uint64_t size) {
    return off <= size && len <= size - off;
}

// Resolve a shared/local scope against the live CTAs.
//  - shared: REQUIRES scope.cta (the CTA's shared window).
//  - local : REQUIRES scope.cta + scope.warp (the warp's per-warp local
//            window).  There is NO scope.lane dimension (High-1, round 2
//            re-review): all lanes of a warp share one buffer addressed by
//            raw byte offset; per-thread frames are folded into that offset
//            by the compiler.  Round 3 re-review: the legacy "scope.lane,
//            when set, must be a real lane of the warp" text is dropped — it
//            described a field the API no longer has.
// Returns an index into ctas()/warps or a failure — never a first-match scan.
StatusOr<std::size_t> scope_cta_index(const std::vector<CtaState>& ctas,
                                      const MemoryScope& scope) {
    if (!scope.cta) {
        return StatusOr<std::size_t>::failure(Error::invalid_argument(
            "shared/local access requires scope.cta"));
    }
    for (std::size_t ci = 0; ci < ctas.size(); ++ci) {
        if (static_cast<std::uint32_t>(ctas[ci].cta_id) == *scope.cta) {
            return StatusOr<std::size_t>::success(ci);
        }
    }
    return StatusOr<std::size_t>::failure(
        Error::not_found("CTA " + std::to_string(*scope.cta) +
                         " not in launch"));
}

StatusOr<std::size_t> scope_warp_index(const CtaState& cta,
                                       const MemoryScope& scope) {
    if (!scope.warp) {
        return StatusOr<std::size_t>::failure(Error::invalid_argument(
            "local access requires scope.warp"));
    }
    for (std::size_t wi = 0; wi < cta.warps.size(); ++wi) {
        if (static_cast<std::uint32_t>(cta.warps[wi].warp_id) == *scope.warp) {
            return StatusOr<std::size_t>::success(wi);
        }
    }
    return StatusOr<std::size_t>::failure(
        Error::not_found("warp " + std::to_string(*scope.warp) +
                         " not in CTA " + std::to_string(cta.cta_id)));
}

}  // namespace

Status DebugSession::read_memory(AddressSpace space, std::uint64_t address,
                                 std::uint64_t len,
                                 std::vector<std::uint8_t>* out,
                                 const MemoryScope& scope) const {
    if (!out) return Status::failure(Error::invalid_argument("null out"));
    if (!interp_ || !interp_->memory()) {
        return Status::failure(Error::illegal_state("no memory service"));
    }
    if (space == AddressSpace::kGlobal) {
        if (len == 0) {
            out->clear();
            return Status::success();
        }
        // Bounds-first (subtractive) so an absurd len can never resize-wrap or
        // throw bad_alloc before the service rejects it.
        const std::uint64_t gsize = interp_->memory()->global_size();
        if (gsize > 0 && !in_window(address, len, gsize)) {
            return Status::failure(Error(ErrorCode::kOob,
                                         "global read out of bounds"));
        }
        out->resize(static_cast<std::size_t>(len));
        Status st = interp_->memory()->read_host(
            address, out->data(), static_cast<std::size_t>(len));
        if (st.failed()) {
            out->clear();
            return st;
        }
        return Status::success();
    }
    if (space == AddressSpace::kShared) {
        const auto& ctas = interp_->ctas();
        auto ci = scope_cta_index(ctas, scope);
        if (!ci.ok()) return ci.status();
        const auto& sh = ctas[ci.value()].shared;
        if (!in_window(address, len, sh.size())) {
            return Status::failure(Error(ErrorCode::kOob,
                                         "shared read out of bounds (cta " +
                                             std::to_string(*scope.cta) + ")"));
        }
        out->resize(static_cast<std::size_t>(len));
        std::memcpy(out->data(), sh.data() + static_cast<std::size_t>(address),
                    static_cast<std::size_t>(len));
        return Status::success();
    }
    if (space == AddressSpace::kLocal) {
        const auto& ctas = interp_->ctas();
        auto ci = scope_cta_index(ctas, scope);
        if (!ci.ok()) return ci.status();
        const CtaState& cta = ctas[ci.value()];
        auto wi = scope_warp_index(cta, scope);
        if (!wi.ok()) return wi.status();
        const auto& ws = cta.warps[wi.value()];
        // Round 2 re-review (High-1): local memory in this sim is a PER-WARP
        // window (WarpState::local); there is no scope.lane dimension — all
        // lanes of the warp share the same buffer at this byte offset.
        if (!in_window(address, len, ws.local.size())) {
            return Status::failure(Error(
                ErrorCode::kOob,
                "local read out of bounds (cta " + std::to_string(*scope.cta) +
                    " warp " + std::to_string(*scope.warp) + ")"));
        }
        out->resize(static_cast<std::size_t>(len));
        std::memcpy(out->data(),
                    ws.local.data() + static_cast<std::size_t>(address),
                    static_cast<std::size_t>(len));
        return Status::success();
    }
    if (space == AddressSpace::kConstant) {
        if (len == 0) {
            out->clear();
            return Status::success();
        }
        const std::uint64_t csize = interp_->memory()->constant_size();
        if (!in_window(address, len, csize)) {
            return Status::failure(Error(ErrorCode::kOob,
                                         "constant read out of bounds"));
        }
        out->resize(static_cast<std::size_t>(len));
        Status st = interp_->memory()->read_constant(
            address, out->data(), static_cast<std::size_t>(len));
        if (st.failed()) out->clear();
        return st;
    }
    return Status::failure(Error(ErrorCode::kNotSupported,
                                 "unsupported address space for read_memory"));
}

Status DebugSession::write_memory(AddressSpace space, std::uint64_t address,
                                  const std::vector<std::uint8_t>& bytes,
                                  const MemoryScope& scope) {
    if (!interp_ || !interp_->memory()) {
        return Status::failure(Error::illegal_state("no memory service"));
    }
    if (bytes.empty()) return Status::success();
    if (space == AddressSpace::kGlobal) {
        return interp_->memory()->write_host(address, bytes.data(),
                                             bytes.size());
    }
    if (space == AddressSpace::kConstant) {
        return interp_->memory()->write_constant(address, bytes.data(),
                                                 bytes.size());
    }
    auto& ctas = interp_->ctas();
    if (space == AddressSpace::kShared) {
        auto ci = scope_cta_index(ctas, scope);
        if (!ci.ok()) return ci.status();
        auto& sh = ctas[ci.value()].shared;
        if (!in_window(address, bytes.size(), sh.size())) {
            return Status::failure(Error(ErrorCode::kOob,
                                         "shared write out of bounds (cta " +
                                             std::to_string(*scope.cta) + ")"));
        }
        std::memcpy(sh.data() + static_cast<std::size_t>(address),
                    bytes.data(), bytes.size());
        return Status::success();
    }
    if (space == AddressSpace::kLocal) {
        auto ci = scope_cta_index(ctas, scope);
        if (!ci.ok()) return ci.status();
        CtaState& cta = ctas[ci.value()];
        auto wi = scope_warp_index(cta, scope);
        if (!wi.ok()) return wi.status();
        auto& ws = cta.warps[wi.value()];
        // Round 2 re-review (High-1): no scope.lane — per-warp window.
        if (!in_window(address, bytes.size(), ws.local.size())) {
            return Status::failure(Error(
                ErrorCode::kOob,
                "local write out of bounds (cta " + std::to_string(*scope.cta) +
                    " warp " + std::to_string(*scope.warp) + ")"));
        }
        std::memcpy(ws.local.data() + static_cast<std::size_t>(address),
                    bytes.data(), bytes.size());
        return Status::success();
    }
    return Status::failure(Error(ErrorCode::kNotSupported,
                                 "unsupported address space for write_memory"));
}

StatusOr<std::map<std::uint32_t, CtaState::NamedBarrier>>
DebugSession::barriers(std::uint32_t cta_id) const {
    auto idx = cta_index(cta_id);
    if (!idx.ok()) {
        return StatusOr<std::map<std::uint32_t, CtaState::NamedBarrier>>::failure(
            idx.take_error());
    }
    return StatusOr<std::map<std::uint32_t, CtaState::NamedBarrier>>::success(
        interp_->ctas()[idx.value()].barriers);
}

StatusOr<std::uint64_t> DebugSession::pending_groups() const {
    if (!interp_ || !interp_->memory()) {
        return StatusOr<std::uint64_t>::failure(
            Error::illegal_state("no memory service"));
    }
    return StatusOr<std::uint64_t>::success(
        interp_->memory()->pending_groups());
}

StatusOr<std::size_t> DebugSession::pending_ops(std::uint64_t group) const {
    if (!interp_ || !interp_->memory()) {
        return StatusOr<std::size_t>::failure(
            Error::illegal_state("no memory service"));
    }
    return StatusOr<std::size_t>::success(
        interp_->memory()->pending_ops(group));
}

StatusOr<DecodedInstruction> DebugSession::decode_at(std::uint64_t pc) const {
    if (!interp_) {
        return StatusOr<DecodedInstruction>::failure(
            Error::illegal_state("no interpreter"));
    }
    const auto& pre = interp_->kernel().predecoded;
    if (pc % 16 != 0 || pc / 16 >= pre.size()) {
        return StatusOr<DecodedInstruction>::failure(Error::invalid_argument(
            "pc 0x" + hex64(pc) + " is not a valid instruction boundary"));
    }
    if (!pre[pc / 16].unique) {
        return StatusOr<DecodedInstruction>::failure(
            Error(ErrorCode::kDecodeIllegal,
                  "word at pc 0x" + hex64(pc) + ": " + pre[pc / 16].reason));
    }
    return StatusOr<DecodedInstruction>::success(*pre[pc / 16].inst);
}

// ---------------------------------------------------------------------------
// State report
// ---------------------------------------------------------------------------

std::string DebugSession::state_report() const {
    std::ostringstream os;
    if (!interp_) {
        os << "(no session)\n";
        return os.str();
    }
    os << "# kernel " << interp_->kernel().symbol_name
       << "  executed=" << interp_->executed()
       << "  limit=" << limit_
       << (done_ ? "  [done]" : "")
       << (terminal_fault_ ? "  [faulted]" : "") << "\n";
    if (terminal_fault_) {
        os << "# fault: " << to_string(terminal_fault_->kind()) << " — "
           << terminal_fault_->message() << "\n";
    }
    const auto& ctas = interp_->ctas();
    std::ostringstream pending;
    pending << "pending_groups=" << interp_->memory()->pending_groups() << " {";
    const std::uint64_t ng = interp_->memory()->pending_groups();
    for (std::uint64_t g = 0; g < ng; ++g) {
        if (g) pending << ",";
        pending << g << ":" << interp_->memory()->pending_ops(g);
    }
    pending << "}";
    os << "# scoreboard " << pending.str() << "\n";
    for (const auto& c : ctas) {
        os << "CTA " << c.cta_id << " (shared=" << c.shared.size()
           << "B scheduler_tick=" << c.scheduler_tick << ")\n";
        for (const auto& w : c.warps) {
            os << "  W" << w.warp_id
               << (w.done ? " done" : "")
               << (w.waiting_barrier >= 0 ? " bar-wait" : "")
               << " active=0x" << std::hex << std::setw(8)
               << std::setfill('0') << w.active_lanes << std::dec
               << " ur[0]=" << hex64(w.ur[0])
               << " up0=" << (w.upred[0] ? 1 : 0) << "\n";
            for (int u = 0; u < kNumUrs; ++u) {
                if (w.ur[static_cast<std::size_t>(u)] != 0) {
                    os << "    UR" << u << "=" << hex64(w.ur[u]) << "\n";
                }
            }
            for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                const ThreadState& t = w.threads[static_cast<std::size_t>(lane)];
                os << "    L" << std::setw(2) << lane << " pc=0x" << std::hex
                   << t.pc << std::dec
                   << (t.active ? "" : " inactive")
                   << (t.exited ? " exited" : "")
                   << " P:";
                for (int p = 0; p < 7; ++p)
                    os << (t.pred[static_cast<std::size_t>(p)] ? "1" : "0");
                os << " R0..R7:";
                for (int r = 0; r < 8; ++r)
                    os << " " << hex64(t.gpr[static_cast<std::size_t>(r)]);
                os << "\n";
            }
            if (!w.sync_stack.empty()) {
                os << "    sync_stack:";
                for (const auto& e : w.sync_stack)
                    os << " {join=0x" << std::hex << e.reconverge_pc
                       << std::dec << " ret=0x" << std::hex << e.return_pc
                       << std::dec << " pend=0x" << std::hex << e.pending_lanes
                       << std::dec << "}";
                os << "\n";
            }
        }
        if (!c.barriers.empty()) {
            for (const auto& [bid, b] : c.barriers) {
                os << "  barrier B" << bid << " expected=" << b.expected
                   << " armed=" << (b.armed ? 1 : 0)
                   << " arrived_warps=" << b.arrived.size() << "\n";
            }
        }
    }
    return os.str();
}

}  // namespace semu