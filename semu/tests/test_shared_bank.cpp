// Shared-memory LDS/STS bank-conflict model unit tests (Phase 8).
//
// Golden cases: stride 1/2/4/8/16/32/33, broadcast, partial mask, and
// 32/64/128-bit loads/stores.  The classic rule is bank=(byte/4)%32, two
// lanes conflict iff they hit the same bank with DIFFERENT words; identical
// (bank, word) is a broadcast/coalesce, never a conflict.

#include <semu/shared_bank.hpp>

#include <cstdio>
#include <vector>

#include "test_framework.hpp"

using semu::shared_bank::estimate;
using semu::shared_bank::kSharedBankModelVersion;

namespace {

// Lane l accesses byte `stride*l` (or broadcast `base` for all lanes).
std::vector<std::uint64_t> strided(std::uint64_t stride, std::uint64_t base) {
    std::vector<std::uint64_t> b(32);
    for (int l = 0; l < 32; ++l) b[l] = base + stride * static_cast<std::uint64_t>(l);
    return b;
}

}  // namespace

// Stride 1 (consecutive 4-B words): all 32 banks distinct -> 1 pass, 0
// conflicts, 0 broadcasts.
TEST(shared_bank_stride1) {
    auto b = strided(4, 0);
    auto r = estimate(b.data(), 4, 0xffffffffu, false);
    CHECK(r.passes == 1);
    CHECK(r.conflict_count == 0);
    CHECK(r.broadcast_count == 0);
    CHECK(r.active_lanes == 32);
}

// Stride 2: each bank hit by two lanes -> 2 passes, conflicts present.
TEST(shared_bank_stride2) {
    auto b = strided(8, 0);
    auto r = estimate(b.data(), 4, 0xffffffffu, false);
    CHECK(r.passes == 2);
    CHECK(r.conflict_count > 0);
}

// Stride 4 -> 4 passes; stride 8 -> 8 passes; stride 16 -> 16 passes;
// stride 32 (all lanes on bank 0, distinct words) -> 32 passes.
TEST(shared_bank_stride_power_of_two) {
    auto b4 = strided(16, 0);
    CHECK(estimate(b4.data(), 4, 0xffffffffu, false).passes == 4);
    auto b8 = strided(32, 0);
    CHECK(estimate(b8.data(), 4, 0xffffffffu, false).passes == 8);
    auto b16 = strided(64, 0);
    CHECK(estimate(b16.data(), 4, 0xffffffffu, false).passes == 16);
    auto b32 = strided(128, 0);
    CHECK(estimate(b32.data(), 4, 0xffffffffu, false).passes == 32);
}

// Stride 33: 33*base, bank=(33*word)%32 = lane%32 -> 32 distinct banks, one
// pass.
TEST(shared_bank_stride33) {
    auto b = strided(33, 0);
    auto r = estimate(b.data(), 4, 0xffffffffu, false);
    CHECK(r.passes == 1);
    CHECK(r.conflict_count == 0);
}

// Broadcast: all lanes hit the same word -> 1 pass, no conflicts, every
// non-first lane coalesces.
TEST(shared_bank_broadcast) {
    std::vector<std::uint64_t> b(32, 0x400);
    auto r = estimate(b.data(), 4, 0xffffffffu, false);
    CHECK(r.passes == 1);
    CHECK(r.conflict_count == 0);
    CHECK(r.broadcast_count == 31);
}

// Partial mask: stride-2 restricted to lanes 0..15 -> each bank hit once,
// 1 pass.
TEST(shared_bank_partial_mask) {
    auto b = strided(8, 0);
    auto r = estimate(b.data(), 4, 0x0000ffffu, false);
    CHECK(r.active_lanes == 16);
    CHECK(r.passes == 1);
    CHECK(r.conflict_count == 0);
}

// 64-bit: half-warp groups, consecutive 8-B words -> each half-warp covers
// all 32 banks once -> 2 passes total.
TEST(shared_bank_width64) {
    auto b = strided(8, 0);
    auto r = estimate(b.data(), 8, 0xffffffffu, false);
    CHECK(r.passes == 2);
    CHECK(r.conflict_count == 0);
}

// 128-bit: quarter-warp groups, consecutive 16-B words -> 4 passes total.
TEST(shared_bank_width128) {
    auto b = strided(16, 0);
    auto r = estimate(b.data(), 16, 0xffffffffu, false);
    CHECK(r.passes == 4);
    CHECK(r.conflict_count == 0);
}

// 64-bit broadcast: two lanes, same 8-B base -> 1 pass, no conflict.
TEST(shared_bank_width64_broadcast) {
    std::vector<std::uint64_t> b(32, 0x200);
    auto r = estimate(b.data(), 8, 0x00000003u, false);
    CHECK(r.passes == 1);
    CHECK(r.conflict_count == 0);
}

// Store direction: same geometry as loads; is_write flag is recorded.
TEST(shared_bank_write_flag) {
    auto b = strided(4, 0);
    auto r = estimate(b.data(), 4, 0xffffffffu, true);
    CHECK(r.is_write);
    CHECK(r.passes == 1);
    CHECK(r.conflict_count == 0);
}

// Conflict reason chain: stride-2 load, bank 0 is hit by lanes 0 and 16.
// The deferred lane's conflict names the exact bank, both words, and the
// earlier pass/lane.
TEST(shared_bank_conflict_reason_chain) {
    auto b = strided(8, 0);  // stride 2 -> bank=(2*lane)%32
    auto r = estimate(b.data(), 4, 0xffffffffu, false);
    bool saw_bank0 = false;
    for (const auto& c : r.conflicts) {
        if (c.bank == 0) saw_bank0 = true;
        CHECK(c.lane_a != c.lane_b);
        CHECK(c.word_a != c.word_b);
        CHECK(c.bank < 32);
        CHECK(c.pass_a < r.passes);
        CHECK(c.reason.find("bank " + std::to_string(c.bank)) !=
              std::string::npos);
    }
    CHECK(saw_bank0);
    CHECK(r.conflicts.size() >= 16);  // 16 banks each with one conflict
}

// Model version is stable and exposed.
TEST(shared_bank_model_version) {
    std::vector<std::uint64_t> b(32, 0);
    auto r = estimate(b.data(), 4, 0xffffffffu, false);
    CHECK(r.model_version == kSharedBankModelVersion);
    CHECK(r.to_json().find(kSharedBankModelVersion) != std::string::npos);
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-shared-bank");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu shared-bank tests\n");
    }
    return failures == 0 ? 0 : 1;
}
