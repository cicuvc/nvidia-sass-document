// L0 unit tests: mbarrier logical model (Phase 9).
#include <semu/mbarrier.hpp>

#include <cstdio>

#include "test_framework.hpp"

using namespace semu;

TEST(mbarrier_init_arrive_phase_flip) {
    // init(2) via the canonical init word ((0x100000-2)<<11)<<32 | (0x100000-2)<<1
    const std::uint64_t word =
        ((0x100000ULL - 2) << 11) << 32 | (0x100000ULL - 2) << 1;
    MbarrierState s = MbarrierState::from_init_word(word);
    CHECK(s.initialized);
    CHECK(s.expected == 2);
    CHECK(s.pending == 2);
    CHECK(s.pending_tx == 0);
    CHECK(s.phase == 0);
    // phasechk(0) before any arrival: phase 0 NOT complete -> false.
    auto p0 = mbarrier_phasechk(s, 0);
    CHECK(p0.ok);
    CHECK(!p0.predicate);
    // 1 arrival: pending 1, still phase 0.
    auto a1 = mbarrier_arrive(&s, 1, 0, false);
    CHECK(a1.ok);
    CHECK(!a1.completion.completed);
    CHECK(mbarrier_phasechk(s, 0).predicate == false);
    // 2nd arrival: phase completes, parity flips.
    auto a2 = mbarrier_arrive(&s, 1, 0, false);
    CHECK(a2.ok);
    CHECK(a2.completion.completed);
    CHECK(a2.completion.new_phase == 1);
    CHECK(s.phase == 1);
    CHECK(s.pending == 2);  // reloaded
    CHECK(mbarrier_phasechk(s, 0).predicate == true);   // phase 0 completed
    CHECK(mbarrier_phasechk(s, 1).predicate == false);  // phase 1 not completed
    // 2 more arrivals -> phase 1 completes.
    mbarrier_arrive(&s, 1, 0, false);
    auto a4 = mbarrier_arrive(&s, 1, 0, false);
    CHECK(a4.completion.completed);
    CHECK(s.phase == 0);
    CHECK(mbarrier_phasechk(s, 1).predicate == true);
    CHECK(mbarrier_phasechk(s, 0).predicate == false);
}

TEST(mbarrier_expect_tx_blocks_completion) {
    const std::uint64_t word =
        ((0x100000ULL - 1) << 11) << 32 | (0x100000ULL - 1) << 1;
    MbarrierState s = MbarrierState::from_init_word(word);
    // expect_tx(128) (A0TR adds).
    auto e = mbarrier_arrive(&s, 0, 128, /*tx_is_complete=*/false);
    CHECK(e.ok);
    CHECK(s.pending_tx == 128);
    // arrive: pending 0 but tx 128 -> NOT complete.
    auto a = mbarrier_arrive(&s, 1, 0, false);
    CHECK(a.ok);
    CHECK(!a.completion.completed);
    CHECK(mbarrier_phasechk(s, 0).predicate == false);
    // complete_tx(128) drains -> phase completes.
    auto c = mbarrier_arrive(&s, 0, 128, /*tx_is_complete=*/true);
    CHECK(c.ok);
    CHECK(s.pending_tx == 0);
    CHECK(c.completion.completed);
    CHECK(mbarrier_phasechk(s, 0).predicate == true);
}

TEST(mbarrier_tx_underflow_corrupts) {
    const std::uint64_t word =
        ((0x100000ULL - 1) << 11) << 32 | (0x100000ULL - 1) << 1;
    MbarrierState s = MbarrierState::from_init_word(word);
    // complete_tx(64) with 0 pending underflows: the op itself does NOT trap,
    // but the barrier is corrupted and the NEXT mbarrier op on it traps.
    auto r = mbarrier_arrive(&s, 0, 64, /*tx_is_complete=*/true);
    CHECK(r.ok);            // no trap on the underflow op itself
    CHECK(!r.fault);
    CHECK(s.corrupted);
    auto next = mbarrier_arrive(&s, 1, 0, false);
    CHECK(next.fault);      // the next op traps
    CHECK(mbarrier_phasechk(s, 0).fault);
}

TEST(mbarrier_init0_immediately_complete) {
    // init(0): word = (0x100000<<11)<<32 | (0x100000<<1); pending 0.
    const std::uint64_t word =
        (0x100000ULL << 11) << 32 | (0x100000ULL << 1);
    MbarrierState s = MbarrierState::from_init_word(word);
    CHECK(s.pending == 0);
    CHECK(s.expected == 0);
    // Phase 0 is immediately complete -> parity flips to 1.
    CHECK(s.phase == 1);
    CHECK(mbarrier_phasechk(s, 0).predicate == true);   // phase 0 completed
    CHECK(mbarrier_phasechk(s, 1).predicate == false);  // phase 1 not completed
    // A subsequent arrive on the immediately-complete barrier traps.
    auto a = mbarrier_arrive(&s, 1, 0, false);
    CHECK(a.fault);
}

TEST(mbarrier_invalidate_stops_completion) {
    const std::uint64_t word =
        ((0x100000ULL - 1) << 11) << 32 | (0x100000ULL - 1) << 1;
    MbarrierState s = MbarrierState::from_init_word(word);
    mbarrier_invalidate(&s);
    CHECK(s.invalid);
    CHECK(mbarrier_phasechk(s, 0).predicate == false);
    // arrive on an invalidated barrier faults.
    auto a = mbarrier_arrive(&s, 1, 0, false);
    CHECK(a.fault);
}

TEST(mbarrier_uninitialized_faults) {
    MbarrierState s;  // default: not initialized
    CHECK(mbarrier_phasechk(s, 0).fault);
    auto a = mbarrier_arrive(&s, 1, 0, false);
    CHECK(a.fault);
}

TEST(mbarrier_encode_roundtrip) {
    const std::uint64_t word =
        ((0x100000ULL - 3) << 11) << 32 | (0x100000ULL - 3) << 1;
    MbarrierState s = MbarrierState::from_init_word(word);
    // encode() keeps count + phase bits observed-consistent.
    const std::uint64_t enc = s.encode();
    CHECK(((enc >> 1) & 0xFFFFF) == 0x100000ULL - 3);
    CHECK(((enc >> 63) & 1) == 0);
}

int main() {
    int failures = semu_test::run_all("semu-mbarrier");
    if (failures == 0)
        std::fprintf(stdout, "[  PASSED  ] all mbarrier tests\n");
    return failures == 0 ? 0 : 1;
}
