// mbarrier logical model (SIM_PLAN Phase 9 subset).

#include <semu/tensor/mbarrier.hpp>

#include <sstream>

namespace semu {

MbarrierResult mbarrier_arrive(MbarrierState* s, std::uint32_t inc,
                               std::uint64_t tx_delta,
                               bool tx_is_complete) {
    MbarrierResult r;
    r.ok = true;
    if (!s || !s->initialized) {
        r.fault = true;
        r.error = "mbarrier not initialized";
        return r;
    }
    if (s->corrupted) {
        r.fault = true;
        r.error =
            "mbarrier corrupted (tx underflow on a prior complete_tx)";
        return r;
    }
    if (s->invalid) {
        r.fault = true;
        r.error = "mbarrier invalidated (CCTL.IV)";
        return r;
    }
    r.old_word = s->encode();
    // A Locked barrier (over-arrival in a prior phase) stays permanently
    // stuck: further ops are no-ops and the phase never completes again.
    if (s->locked) return r;

    // complete_tx subtracts; expect_tx adds.  A subtraction larger than the
    // pending count underflows the field and CORRUPTS the barrier (verified
    // boundary: the op itself does not trap but the NEXT mbarrier op on it
    // traps).
    if (tx_delta) {
        if (tx_is_complete) {
            if (tx_delta > s->pending_tx) {
                s->pending_tx = 0;
                s->corrupted = true;
                r.error =
                    "mbarrier tx underflow (negative complete_tx)";
                return r;  // ok=true: this op does not trap
            }
            s->pending_tx -= tx_delta;
        } else {
            s->pending_tx += tx_delta;
        }
    }
    // Over-arrival (arriving after the current phase's arrival count is
    // already satisfied) sets the Lock bit and faults the op: the barrier is
    // permanently stuck.  Verified boundary: init(0) then arrive traps.
    if (inc) {
        if (inc > s->pending) {
            s->locked = true;
            r.fault = true;
            r.error = "mbarrier over-arrival (arrivals already complete)";
            return r;
        }
        s->pending -= inc;
    }

    // Phase completion: pending arrivals == 0 AND pending tx == 0.
    if (s->pending == 0 && s->pending_tx == 0) {
        s->phase ^= 1;
        s->pending = s->expected;  // reload for the next phase
        r.completion.completed = true;
        r.completion.new_phase = s->phase;
    }
    return r;
}

MbarrierResult mbarrier_phasechk(const MbarrierState& s,
                                 std::uint32_t parity) {
    MbarrierResult r;
    r.ok = true;
    if (!s.initialized) {
        r.fault = true;
        r.error = "mbarrier not initialized";
        return r;
    }
    if (s.corrupted) {
        r.fault = true;
        r.error =
            "mbarrier corrupted (tx underflow on a prior complete_tx)";
        return r;
    }
    r.old_word = s.encode();
    // Inval / Locked: the barrier stops completing; phasechk stays false.
    if (s.invalid || s.locked) {
        r.predicate = false;
        return r;
    }
    r.predicate = (s.phase != (parity & 1));
    return r;
}

void mbarrier_invalidate(MbarrierState* s) {
    if (s) s->invalid = true;
}

std::string describe_mbarrier(const MbarrierState& s) {
    std::ostringstream os;
    if (!s.initialized) return "uninitialized";
    os << "expected=" << s.expected << " pending=" << s.pending
       << " tx=" << s.pending_tx << " phase=" << s.phase
       << (s.invalid ? " INVALID" : "")
       << (s.locked ? " LOCKED(over-arrival)" : "")
       << (s.corrupted ? " CORRUPTED(tx-underflow)" : "");
    return os.str();
}

}  // namespace semu