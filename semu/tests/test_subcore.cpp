// Subcore scheduler + L1TEX trace-only contracts (Phase 6 Step 2B).
//
//   - warp -> subcore mapping is stable (warp%4 default)
//   - each subcore preserves its own program order (issue sequence)
//   - 4 subcores do NOT impose a whole-SM total order
//   - subcore issue is pure bookkeeping: never affects functional values
//   - prediction perturbation (estimator returns 1 / real / +N) must not
//     change functional results — the estimator is trace-only.

#include <semu/exec/subcore_scheduler.hpp>

#include <cstdio>
#include <string>
#include <vector>

#include "test_framework.hpp"

using semu::SmL1TexState;
using semu::SubcoreId;
using semu::Mod4SubcoreMapper;
using semu::issue_on_subcore;
using semu::subcore_trace_line;

namespace {

Mod4SubcoreMapper mapper;

}  // namespace

// warp%4 mapping is stable and covers all 4 subcores.
TEST(subcore_warp_mapping_stable) {
    CHECK(mapper.map(0).id == 0);
    CHECK(mapper.map(1).id == 1);
    CHECK(mapper.map(2).id == 2);
    CHECK(mapper.map(3).id == 3);
    CHECK(mapper.map(4).id == 0);
    CHECK(mapper.map(17).id == 1);
    CHECK(mapper.name() == std::string("warp%4"));
}

// Per-subcore program order: issues to the same subcore are monotonic; issues
// to different subcores may interleave freely (no whole-SM total order).
TEST(subcore_program_order_per_subcore) {
    SmL1TexState sm;
    sm.sm_id = 0;
    // Warps 0..3 -> subcores 0..3.  Issue warp0, warp1, warp0, warp2.
    auto a = issue_on_subcore(sm, mapper, 0);  // sc0
    auto b = issue_on_subcore(sm, mapper, 1);  // sc1
    auto c = issue_on_subcore(sm, mapper, 0);  // sc0 (after a)
    auto d = issue_on_subcore(sm, mapper, 2);  // sc2
    CHECK(a.subcore.id == 0 && b.subcore.id == 1 && c.subcore.id == 0 &&
          d.subcore.id == 2);
    // sc0: a then c -> c.event_id > a.event_id (program order).
    CHECK(c.event_id > a.event_id);
    // sc1 and sc2 independent: no cross-subcore ordering required.
    // Subcore-local sequences increment.
    CHECK(c.subcore_seq > a.subcore_seq);
    // Global event ids are unique and monotonic (stable tie sequence).
    CHECK(a.event_id < b.event_id && b.event_id < c.event_id &&
          c.event_id < d.event_id);
}

// The trace line lists each subcore's issue list separately; it does not
// merge them into one total order.
TEST(subcore_trace_keeps_subcores_separate) {
    SmL1TexState sm;
    sm.sm_id = 1;
    issue_on_subcore(sm, mapper, 0);
    issue_on_subcore(sm, mapper, 1);
    issue_on_subcore(sm, mapper, 0);
    issue_on_subcore(sm, mapper, 3);
    const std::string line = subcore_trace_line(sm);
    CHECK(line.find("sm1 {") == 0);
    // sc0 has 2 issues, sc1 has 1, sc2 has 0, sc3 has 1.
    CHECK(line.find("sc0:[1,2]") != std::string::npos);
    CHECK(line.find("sc1:[1]") != std::string::npos);
    CHECK(line.find("sc3:[1]") != std::string::npos);
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-subcore");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu subcore tests\n");
    }
    return failures == 0 ? 0 : 1;
}
