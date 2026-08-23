// sm120 baseline interpreter -- control flow: BRA/BRX/JMP/JMX/BSSY/BSYNC/EXIT/BAR/DEPBAR/LDGDEPBAR/ELECT.
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
std::optional<std::uint64_t> Interpreter::branch_target(
    const DecodedInstruction& inst, std::uint64_t pc,
    ThreadState& t) const {
    const isa::Mnemonic m = inst.mnemonic;
    std::int64_t target_s = 0;
    if (m == isa::Mnemonic::kBRA || m == isa::Mnemonic::kJMP) {
        // Target read from the concrete struct fields by opcode: BRA
        // {2-op 0x947, 3-op 0x1547/0x1947}, JMP {2-op 0x94a, 3-op
        // 0x1550/0x194a} (uniform-pred / UR-target forms).
        std::int64_t imm = 0;
        const std::uint16_t op2 = semu::opcode_of(inst.word.lo, inst.word.hi);
        if (op2 == 0x1547 || op2 == 0x1947) {
            imm = shape::operand_value_as_i64(
                static_cast<const shape::DecodedBRA3_0*>(&inst)->sImm);
        } else if (op2 == 0x1550 || op2 == 0x194a) {
            imm = shape::operand_value_as_i64(
                static_cast<const shape::DecodedJMP3_0*>(&inst)->Sa);
        } else if (op2 == 0x947) {
            imm = shape::operand_value_as_i64(
                static_cast<const shape::DecodedBRA2*>(&inst)->sImm);
        } else {  // 0x94a (JMP 2-op)
            imm = shape::operand_value_as_i64(
                static_cast<const shape::DecodedJMP2*>(&inst)->Sa);
        }
        if (m == isa::Mnemonic::kBRA) {
            const std::int64_t disp = imm;
            std::int64_t scaled;
            if (!checked_mul4(disp, &scaled)) return std::nullopt;
            // pc + 16 + scaled (checked).
            std::int64_t base;
            if (!checked_add(static_cast<std::int64_t>(pc), 16, &base))
                return std::nullopt;
            if (!checked_add(base, scaled, &target_s)) return std::nullopt;
        } else {
            // JMP absolute: Sa*4 (55-bit field, SCALE 4).  Real targets are
            // small positive kernel offsets; a value that sign-extends
            // negative (huge unsigned) is rejected below, matching the old
            // INT64_MAX guard.
            if (imm < 0) return std::nullopt;
            if (!checked_mul4(imm, &target_s)) return std::nullopt;
        }
    } else if (m == isa::Mnemonic::kBRX || m == isa::Mnemonic::kJMX) {
        // BRX/JMX use a 64-bit register pair Ra:R(a+1) (verified:
        // test_brx target = next_pc + sign-extended(Ra:R(a+1)) + off*4).
        const std::uint64_t rv =
            (m == isa::Mnemonic::kBRX)
                ? shape::operand_value_as_i64(
                      static_cast<const shape::DecodedBRX3*>(&inst)->Ra)
                : shape::operand_value_as_i64(
                      static_cast<const shape::DecodedJMX3*>(&inst)->Ra);
        const int rlo = static_cast<int>(rv);
        const std::uint64_t low = (rlo == kRegRz) ? 0 : read_reg(t, rlo);
        const std::uint64_t high =
            (rlo == kRegRz || rlo + 1 > kNumGprs - 1) ? 0
            : read_reg(t, rlo + 1);
        const std::uint64_t pair = low | (high << 32);
        // pair is the raw 64-bit displacement (two's complement).
        const std::int64_t disp = static_cast<std::int64_t>(pair);
        const std::int64_t off_v =
            (m == isa::Mnemonic::kBRX)
                ? shape::operand_value_as_i64(
                      static_cast<const shape::DecodedBRX3*>(&inst)->Ra_offset)
                : shape::operand_value_as_i64(
                      static_cast<const shape::DecodedJMX3*>(&inst)->Ra_offset);
        std::int64_t scaled;
        if (!checked_mul4(off_v, &scaled)) return std::nullopt;
        std::int64_t base = (m == isa::Mnemonic::kBRX)
            ? static_cast<std::int64_t>(pc) + 16
            : static_cast<std::int64_t>(pc);
        if (!checked_add(base, disp, &base)) return std::nullopt;
        if (!checked_add(base, scaled, &target_s)) return std::nullopt;
    } else if (m == isa::Mnemonic::kBSSY) {
        // BSSY target is Sa*4 absolute (30-bit field, no PC add).
        const auto& d = *static_cast<const shape::DecodedBSSY3*>(&inst);
        const std::int64_t sav = shape::operand_value_as_i64(d.Sa);
        if (sav < 0) return std::nullopt;
        if (!checked_mul4(sav, &target_s)) return std::nullopt;
    } else {
        return std::nullopt;
    }
    if (target_s % 16 != 0) return std::nullopt;
    if (target_s < 0 || target_s >= static_cast<std::int64_t>(kernel_.text_size))
        return std::nullopt;
    return static_cast<std::uint64_t>(target_s);
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
    // Barrier register (Bn) from the barReg operand role; BSYNC must match it.
    const auto& d = *static_cast<const shape::DecodedBSSY3*>(&inst);
    const auto barreg = static_cast<std::uint32_t>(
        shape::operand_value_as_i64(d.barReg));
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
    const auto& d = *static_cast<const shape::DecodedBSYNC2*>(&inst);
    const auto barreg = static_cast<std::uint32_t>(
        shape::operand_value_as_i64(d.barReg));
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

Status Interpreter::do_bar(WarpState& w, const DecodedInstruction& inst,
                           std::uint32_t mask, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    (void)mask;
    (void)pc;
    (void)fault;
    // BAR.SYNC n: all participating warps arrive at barrier n; the warp
    // waits (suspended) until every warp in the CTA has arrived.

    // BAR3 (RED/SCAN forms) vs BAR2 (ARV/SYNC forms): the barrier-id field is
    // a typed member of the concrete struct — select by variant class.
    const bool is_bar3 =
        inst.variant_class == isa::VariantClass::kbar__RED_II_optionalCount_II ||
        inst.variant_class == isa::VariantClass::kbar__RED_IR_optionalCount_IR ||
        inst.variant_class == isa::VariantClass::kbar__RED_RI_optionalCount_RI ||
        inst.variant_class == isa::VariantClass::kbar__RED_RR_RR ||
        inst.variant_class == isa::VariantClass::kbar__RED_dfrBlk_II_optionalCount_II ||
        inst.variant_class == isa::VariantClass::kbar__RED_dfrBlk_IR_optionalCount_IR ||
        inst.variant_class == isa::VariantClass::kbar__RED_dfrBlk_RI_optionalCount_RI ||
        inst.variant_class == isa::VariantClass::kbar__RED_dfrBlk_RR_RR ||
        inst.variant_class == isa::VariantClass::kbar__SCAN_II_II ||
        inst.variant_class == isa::VariantClass::kbar__SCAN_IR_IR ||
        inst.variant_class == isa::VariantClass::kbar__SCAN_RI_RI ||
        inst.variant_class == isa::VariantClass::kbar__SCAN_RR_RR;
    const std::uint64_t bid =
        is_bar3
            ? static_cast<std::uint64_t>(
                  static_cast<const shape::DecodedBAR3*>(&inst)->barname)
            : static_cast<std::uint64_t>(
                  static_cast<const shape::DecodedBAR2*>(&inst)->barname);
    CtaState& cta = ctas_[w.local_cta_id];
    auto& bar = cta.barriers[bid];
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
            if (ws.waiting_barrier == static_cast<int>(bid)) {
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
    w.waiting_barrier = static_cast<int>(bid);
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
}  // namespace

void Interpreter::do_ldgdepbar(WarpState& w, const DecodedInstruction& inst,
                               std::uint64_t pc) {
    (void)w;
    (void)pc;
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    if (!cta.async_open.copies.empty() || cta.async_open.committed_bytes > 0) {
        // Seal into the committed group list (observable async state).
        cta.async_groups.push_back(cta.async_open);
        const auto wr = inst.schedule.dst_wr_sb;
        if (wr < static_cast<int>(cta.sb_group_count.size())) {
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
    // Roles: 3-op [sbidx, cnt|URb, scoreboard_list] (+le); 1-op
    // [scoreboard_list]; 0-op all (le only).
    std::uint64_t le = 0, sbidx = 0, cnt = 0;
    if (inst.variant_class == isa::VariantClass::kdepbar__LE ||
        inst.variant_class == isa::VariantClass::kdepbar_ur_) {
        // DEPBAR3: depbar_ur_ (_0: [sbidx,URb,..]) vs depbar__LE
        // (_1: [sbidx,cnt,..]); both carry `le`; the count role is the
        // second field.
        if (inst.variant_class == isa::VariantClass::kdepbar_ur_) {
            const auto& d = *static_cast<const shape::DecodedDEPBAR3_0*>(&inst);
            le = static_cast<std::uint64_t>(d.le);
            sbidx = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(d.sbidx));
            cnt = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(d.URb));
        } else {  // kdepbar__LE
            const auto& d = *static_cast<const shape::DecodedDEPBAR3_1*>(&inst);
            le = static_cast<std::uint64_t>(d.le);
            sbidx = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(d.sbidx));
            cnt = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(d.cnt));
        }
    } else if (inst.variant_class == isa::VariantClass::kdepbar__noLE) {
        const auto& d = *static_cast<const shape::DecodedDEPBAR1*>(&inst);
        (void)d;
    } else {  // kdepbar_all_
        const auto& d = *static_cast<const shape::DecodedDEPBAR0*>(&inst);
        le = static_cast<std::uint64_t>(d.le);
    }
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    if (le && sbidx < cta.sb_group_count.size()) {
        // Drain (seal->complete) groups until SBn s count <= cnt.  The copies
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

Status Interpreter::do_elect(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst) {
    // ELECT Pu, URd, Pp: leader election — lowest active lane with Pp.
    // Roles: [Pu, URd, <Pp|URa>] (the third role is Pp on the Pp form,
    // URa on the source form).
    const shape::OperandValue* pu = nullptr;
    const shape::OperandValue* urd = nullptr;
    const shape::OperandValue* src = nullptr;
    if (inst.variant_class == isa::VariantClass::kelect_Pp_) {
        const auto& d = *static_cast<const shape::DecodedELECT3_0*>(&inst);
        pu = &d.Pu; urd = &d.URd; src = &d.Pp;
    } else {
        const auto& d = *static_cast<const shape::DecodedELECT3_1*>(&inst);
        pu = &d.Pu; urd = &d.URd; src = &d.URa;
    }
    const bool has_pp =
        static_cast<shape::OperandKind>(src->kind) ==
        shape::OperandKind::kPredicate;
    const std::uint64_t r =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(*urd));
    int leader = -1;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        const ThreadState& t = w.threads[lane];
        bool p = false;
        if (has_pp) read_pred_ov(t, *src, &p);
        if (p) { leader = lane; break; }
    }
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        const bool is_leader = (lane == leader);
        write_pred_ov(t, *pu, is_leader);
        // URd = leader lane id for all lanes.
        if (r < kNumUrs)
            w.ur[r] = static_cast<std::uint32_t>(leader);
    }
    return Status::success();
}


}  // namespace semu
