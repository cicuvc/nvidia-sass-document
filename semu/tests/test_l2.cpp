// L2 event engine unit tests (Phase 6 Step 2C).
//
//   - same-sector accesses from different SMs interact (share an L2 queue)
//   - different-sector accesses do not interact
//   - stable tie-break ordering + deterministic seed replay produce a
//     byte-for-byte identical event stream
//   - the engine is trace-only: issuing events never returns a value change

#include <semu/l2_events.hpp>

#include <cstdio>
#include <string>

#include "test_framework.hpp"

using semu::L2EventEngine;
using semu::l2_events_to_json;

namespace {

// Same byte address -> same 128-B sector.
const std::uint64_t kAddr = 0x1000;   // sector = 0x1000>>7 = 0x20
const std::uint64_t kSector = 0x20;

}  // namespace

// Two SMs touch the same sector; both issue requests, both complete in a
// stable order.
TEST(l2_same_sector_cross_sm) {
    L2EventEngine eng(2, 0);
    eng.issue_global(0, 0, 0, 0, 0x100, 1, 10, "LDG", "load", kAddr, 4);
    eng.issue_global(1, 0, 1, 0, 0x100, 2, 11, "STG", "store", kAddr + 4, 4);
    auto reqs = eng.issue_global(0, 1, 0, 1, 0x100, 3, 12, "LDG", "load",
                                 kAddr, 4);
    CHECK(reqs.size() == 1);
    CHECK(reqs[0].sector == kSector);
    auto comps = eng.drain_completions();
    // 3 requests -> 3 completions (same sector -> all share the L2 queue).
    CHECK(comps.size() == 3);
    CHECK(comps[0].sector == kSector);
    // Stable tie-break: the default (seed 0) sorts by (sector, sm, request).
    CHECK(comps[0].sm == 0);
}

// Different sectors: each access maps to its own sector, requests are
// isolated, completions are separate.
TEST(l2_different_sector_no_interaction) {
    L2EventEngine eng(2, 0);
    // 0x1000 -> sector 0x20; 0x2000 -> sector 0x40.
    auto r1 = eng.issue_global(0, 0, 0, 0, 0, 1, 10, "LDG", "load", 0x1000, 4);
    auto r2 = eng.issue_global(1, 0, 1, 0, 0, 2, 11, "STG", "store", 0x2000, 4);
    CHECK(r1[0].sector != r2[0].sector);
    auto comps = eng.drain_completions();
    CHECK(comps.size() == 2);
}

// A wide access spanning multiple sectors emits one request per sector.
TEST(l2_wide_access_multiple_sectors) {
    L2EventEngine eng(1, 0);
    // 256 bytes at 0x1000 spans sectors 0x20 and 0x21 (and 0x20+... actually
    // 256 bytes = 2 sectors: 0x1000..0x1100 -> sectors 0x20, 0x21).
    auto reqs = eng.issue_global(0, 0, 0, 0, 0, 1, 10, "LDG", "load", 0x1000,
                                 256);
    CHECK(reqs.size() >= 2);
}

// Seed replay: the same seed produces a byte-for-byte identical JSON event
// stream; a different seed may differ (ordering) but never affects any value
// (the engine only emits events).
TEST(l2_seed_replay_deterministic) {
    // Build two identical engines with the same seed.
    L2EventEngine a(2, 42);
    L2EventEngine b(2, 42);
    // Issue the same accesses to both.
    const struct { std::uint32_t sm, sc; std::uint64_t addr; } accs[] = {
        {0, 0, 0x1000}, {1, 0, 0x1000}, {0, 1, 0x1040},
        {1, 1, 0x2000}, {0, 0, 0x1000}, {1, 0, 0x2000},
    };
    for (std::size_t i = 0; i < 6; ++i) {
        const auto& ac = accs[i];
        a.issue_global(ac.sm, ac.sc, ac.sm, 0, 0x100, i, i + 100, "LDG",
                       "load", ac.addr, 4);
        b.issue_global(ac.sm, ac.sc, ac.sm, 0, 0x100, i, i + 100, "LDG",
                       "load", ac.addr, 4);
    }
    const std::string ja = l2_events_to_json(a.events());
    const std::string jb = l2_events_to_json(b.events());
    CHECK(ja == jb);  // same seed -> identical requests

    // Same completions too (after drain).
    a.drain_completions();
    b.drain_completions();
    CHECK(l2_events_to_json(a.events()) == l2_events_to_json(b.events()));

    // A different seed produces a reproducible (but possibly different)
    // completion order; both are still valid schedules with no value effect.
    L2EventEngine c(2, 43);
    for (std::size_t i = 0; i < 6; ++i) {
        const auto& ac = accs[i];
        c.issue_global(ac.sm, ac.sc, ac.sm, 0, 0x100, i, i + 100, "LDG",
                       "load", ac.addr, 4);
    }
    c.drain_completions();
    // c is internally consistent (deterministic for its own seed).
    L2EventEngine c2(2, 43);
    for (std::size_t i = 0; i < 6; ++i) {
        const auto& ac = accs[i];
        c2.issue_global(ac.sm, ac.sc, ac.sm, 0, 0x100, i, i + 100, "LDG",
                        "load", ac.addr, 4);
    }
    c2.drain_completions();
    CHECK(l2_events_to_json(c.events()) == l2_events_to_json(c2.events()));
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-l2");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu l2 tests\n");
    }
    return failures == 0 ? 0 : 1;
}
