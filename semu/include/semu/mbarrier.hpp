#pragma once

// Shared-memory mbarrier logical model (SIM_PLAN Phase 9 subset).
//
// The mbarrier is a 64-bit word in shared memory at a barrier address.  Its
// bit layout (authoritative, Phase 9 subset fix):
//
//   bit0       reserved
//   bits[1:20]  Expected  (int20 two's complement of the per-phase arrival
//                          count, i.e. init(n) stores (0x100000 - n) & 0xFFFFF)
//   bits[21:41] tx        (int21 outstanding transaction bytes; expect_tx sets
//                          it toward -bytes, TMA complete_tx adds bytes back)
//   bit42       Lock      (over-arrival / deadlock sticky bit)
//   bits[43:62] Arrive    (int20 two's complement of the remaining arrivals in
//                          the current phase)
//   bit63       Phase     (current phase parity)
//
// Observations (verified on sm_120, notes/sm90/instr/syncs.md and
// tests/asm_construct/test_mbarrier.py; Phase 9 subset unit/interp tests):
//
//   init(n)    -> phase 0 expects n arrivals; pending arrivals = n; pending
//                 tx = 0.  init(0) writes a word with bit63 already SET, so
//                 phase 0 is immediately complete (the parity reads as 1).
//   arrive     -> pending arrivals -= 1; when the pending arrivals reach 0
//                 AND the pending tx reaches 0 the phase completes: the
//                 parity bit flips and the arrival count reloads to n.
//   arrive     -> arriving when the current phase's arrivals are already
//                 satisfied (over-arrival) sets the Lock bit and FAULTS the
//                 op (the barrier is permanently stuck; verified boundary:
//                 init(0) then arrive traps).
//   expect_tx  -> pending tx += k (A0TR / A1TR tx part).
//   complete_tx-> pending tx -= k; an underflow (> pending) corrupts the
//                 barrier: the op itself does not trap but the NEXT mbarrier
//                 op on it traps.
//   A phase completes only when BOTH the arrivals and the tx drain to zero.
//   phasechk(parity P) is TRUE iff the phase with parity P has completed,
//   i.e. iff the current phase parity != P.  On a Locked / CCTL.IV barrier
//   the phase never completes (predicate stays false) / phasechk returns
//   false.  On a corrupted barrier the next op faults.
//
// The module keeps the LOGICAL fields (expected / pending / pending_tx /
// phase / locked / invalid) authoritative and provides encode/decode so the
// word can be mirrored back to shared memory for observability (SYNCS.LD /
// LDS); the functional behavior is driven by the logical fields.

#include <cstdint>
#include <string>

namespace semu {

// Encoding constants (authoritative Phase 9 subset bit layout).
constexpr std::uint64_t kMbarrierPhaseBit = 1ULL << 63;
constexpr std::uint64_t kMbarrierLockBit = 1ULL << 42;

struct MbarrierState {
    bool initialized = false;
    bool invalid = false;   // CCTL.IV: stops completing; phasechk false
    bool corrupted = false; // complete_tx underflow (next op traps)
    bool locked = false;    // over-arrival: barrier permanently stuck
    std::uint32_t expected = 0;    // arrivals needed per phase (n)
    std::uint32_t pending = 0;     // remaining arrivals in current phase
    std::uint64_t pending_tx = 0;  // outstanding tx bytes
    std::uint32_t phase = 0;       // current phase parity (0/1)

    // Encode the logical state to the shared 64-bit word per the
    // authoritative layout above.
    std::uint64_t encode() const {
        std::uint64_t w = 0;
        const std::uint64_t expected_field =
            (static_cast<std::uint64_t>(0x100000) - expected) & 0xFFFFF;
        const std::uint64_t arrive_field =
            (static_cast<std::uint64_t>(0x100000) - pending) & 0xFFFFF;
        w |= expected_field << 1;
        w |= (pending_tx & 0x1FFFFF) << 21;
        if (locked) w |= kMbarrierLockBit;
        w |= arrive_field << 43;
        if (phase) w |= kMbarrierPhaseBit;
        return w;
    }

    // Seed from an init word written by mbarrier.init (SYNCS.EXCH.64 / a
    // plain STS.32 pair).  The count field at bits[1:20] is the complement
    // form, so expected = (0x100000 - field) & 0xFFFFF.  At initialization
    // the arrival count starts equal to the expected count and no tx is
    // outstanding; the parity comes from bit63.  init(0) stores a word whose
    // bit63 is already SET (0x100000 << 43 has bit63 high), so the parity of
    // the immediately-complete phase 0 reads as 1 — no extra flip is needed.
    static MbarrierState from_init_word(std::uint64_t w) {
        MbarrierState s;
        s.initialized = true;
        s.invalid = false;
        s.corrupted = false;
        s.locked = (w >> 42) & 1;
        const std::uint64_t count_field = (w >> 1) & 0xFFFFF;
        const std::uint64_t expected =
            (static_cast<std::uint64_t>(0x100000) - count_field) & 0xFFFFF;
        s.expected = static_cast<std::uint32_t>(expected);
        s.pending = s.expected;
        s.pending_tx = 0;
        s.phase = (w >> 63) & 1;
        return s;
    }
};

// A completed-phase notification (produced by arrive/complete_tx/expect_tx
// when a phase flips).  Consumers (the debugger / profiler / interpreter)
// use it to report async completion.
struct MbarrierCompletion {
    bool completed = false;   // a phase completed on this op
    std::uint32_t new_phase = 0;
};

// One mbarrier's operation outcomes: the resulting predicate (phasechk) or
// the token (arrive returns the OLD state word), plus any phase flip.
struct MbarrierResult {
    bool ok = false;             // op succeeded (no trap)
    bool fault = false;          // structured fault (uninitialized / corrupt
                                 // / over-arrival / invalidated)
    std::string error;           // fault message when fault
    std::uint64_t old_word = 0;  // arrive token / phasechk reads
    bool predicate = false;      // phasechk result
    MbarrierCompletion completion;
};

// Apply one arrival: `inc` arrivals (+1 or +R) and `tx_delta` tx bytes
// (A1TR: +R; A1T0: 0; ART0: +R arrivals only; A0TR/A0TX: tx only).  The
// `is_complete_tx` flag selects complete_tx (subtract) vs expect_tx (add).
// Returns the token (old word) and any phase flip.  `word` is the CURRENT
// shared word (state seed).
MbarrierResult mbarrier_arrive(MbarrierState* s, std::uint32_t inc,
                               std::uint64_t tx_delta, bool tx_is_complete);

// phasechk / try_wait.parity: `parity` is the PTX parity (0/1); returns
// predicate = (current phase != parity) when the barrier is valid and
// initialized, false when invalid/locked, fault when uninitialized/corrupted.
MbarrierResult mbarrier_phasechk(const MbarrierState& s, std::uint32_t parity);

// CCTL.IV invalidate.
void mbarrier_invalidate(MbarrierState* s);

std::string describe_mbarrier(const MbarrierState& s);

}  // namespace semu