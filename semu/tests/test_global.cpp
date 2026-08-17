// Global LDG/STG coalescing / sector-line model unit tests (Phase 8).
//
// Golden cases: contiguous, strided, broadcast, misaligned, and 32-B
// sector / 128-B line crossings.  L1 data-bank and tag-bank are reported as
// SEPARATE counters.

#include <semu/global_model.hpp>

#include <cstdio>
#include <vector>

#include "test_framework.hpp"

using semu::shared_bank::LaneAccess;
using semu::global_model::estimate;
using semu::global_model::kSectorBytes;
using semu::global_model::kLineBytes;

namespace {

std::vector<LaneAccess> make(std::uint64_t base, std::uint64_t stride,
                             std::uint32_t width, std::uint32_t mask) {
    std::vector<LaneAccess> l(32);
    for (int i = 0; i < 32; ++i) {
        l[i].lane = static_cast<std::uint32_t>(i);
        l[i].base = base + stride * static_cast<std::uint64_t>(i);
        l[i].len = width;
        l[i].active = (mask >> i) & 1u;
    }
    return l;
}

}  // namespace

// Contiguous 4-B: 128 lane-requested/unique-useful bytes, 4 sectors, 1 line,
// 1 data-bank pass, efficiency 1.0.
TEST(global_contiguous) {
    auto l = make(0, 4, 4, 0xffffffffu);
    auto r = estimate(l.data(), 4);
    CHECK(r.active_lanes == 32);
    CHECK(r.lane_requested_bytes == 128);
    CHECK(r.unique_useful_bytes == 128);
    CHECK(r.duplicate_reuse_bytes == 0);
    CHECK(r.coalescing_efficiency == 1.0);
    CHECK(r.sectors.size() == 4);  // bytes 0..127 -> sectors 0..3
    CHECK(r.lines.size() == 1);    // one 128-B line
    CHECK(r.data_bank_passes == 1);
    CHECK(r.data_bank_conflicts == 0);
    CHECK(r.tag_bank_passes == 1);
}

// Strided-by-8 (4-B words): 32 distinct bytes still, 2 data-bank passes,
// 0 conflicts.  Words 0..30 sit in line 0 and words 32..62 in line 1; each
// line sees 16 distinct even banks, so under the cross-line split (High-2)
// each line is its own conflict group and no bank is repeated within a line
// (the pre-fix golden of 16 merged words_per_bank across lines).
TEST(global_strided) {
    auto l = make(0, 8, 4, 0xffffffffu);
    auto r = estimate(l.data(), 4);
    CHECK(r.lane_requested_bytes == 128);
    CHECK(r.unique_useful_bytes == 128);
    CHECK(r.duplicate_reuse_bytes == 0);
    CHECK(r.data_bank_passes == 2);
    CHECK(r.data_bank_conflicts == 0);
}

// Broadcast: all lanes hit the same 4 bytes -> 1 data-bank pass, 0 data-bank
// conflicts.  The byte accounting is explicitly denominated (High-1):
// lane_requested = 128 (what the warp asked for), unique_useful = 4 (distinct
// bytes), duplicate_reuse = 124 (bytes requested by 32 lanes), and
// coalescing_efficiency = 4/32 = 0.125 because a whole 32-B sector is
// transferred for 4 useful bytes (never 32.0 — the old golden that compared
// the union against the lane sum).
TEST(global_broadcast) {
    auto l = make(0x1000, 0, 4, 0xffffffffu);
    auto r = estimate(l.data(), 4);
    CHECK(r.lane_requested_bytes == 128);
    CHECK(r.unique_useful_bytes == 4);
    CHECK(r.duplicate_reuse_bytes == 124);
    CHECK(r.broadcast_reuse_factor == 32.0);
    CHECK(r.coalescing_efficiency == 0.125);  // 4 unique useful / 32 fetched
    CHECK(r.sectors.size() == 1);
    CHECK(r.sectors[0] == 0x80);  // 0x1000/32
    CHECK(r.lines.size() == 1);
    CHECK(r.lines[0] == 0x20);  // 0x1000/128
    CHECK(r.sector_fetch_bytes == 32);
    CHECK(r.sector_overfetch_bytes == 28);  // 32 - 4
    CHECK(r.line_fill_bytes == 128);
    CHECK(r.line_overfetch_bytes == 124);  // 128 - 4
    CHECK(r.data_bank_passes == 1);
    CHECK(r.data_bank_conflicts == 0);
}

// Misaligned (base 0x1004, lanes 0..15): crosses 32-B sector boundaries
// (3 sectors) while staying inside one 128-B line.
TEST(global_misaligned) {
    auto l = make(0x1004, 4, 4, 0x0000ffffu);
    auto r = estimate(l.data(), 4);
    CHECK(r.lane_requested_bytes == 16 * 4);
    CHECK(r.unique_useful_bytes == 64);
    CHECK(r.sectors.size() == 3);  // 0x1004..0x1043 -> sectors 128..130
    CHECK(r.lines.size() == 1);    // 0x1000..0x1043 -> line 32
    CHECK(r.lines[0] == 0x20);
    CHECK(r.data_bank_passes == 1);
    CHECK(r.data_bank_conflicts == 0);
}

// 16-B access at 0x1078 crosses both a 32-B sector boundary and a 128-B line
// boundary: two sectors and two lines from a single lane.  The data-bank pass
// count splits the lane's range into per-line fragments (High-2): line 32
// serves words {0x106,0x107} and line 33 serves {0x108,0x109}, so the two
// lines form ONE pass each -> data_bank_passes == 2.
TEST(global_sector_line_crossing) {
    std::vector<LaneAccess> l(32);
    l[0].lane = 0;
    l[0].base = 0x1078;
    l[0].len = 16;
    l[0].active = true;
    auto r = estimate(l.data(), 16);
    CHECK(r.active_lanes == 1);
    CHECK(r.lane_requested_bytes == 16);
    CHECK(r.unique_useful_bytes == 16);
    CHECK(r.sectors.size() == 2);  // 0x1078..0x1087 -> sectors 131, 132
    CHECK(r.lines.size() == 2);    // 0x1078..0x1087 -> lines 32, 33
    CHECK(r.lines[0] == 0x20 && r.lines[1] == 0x21);
    CHECK(r.data_bank_passes == 2);  // one pass per line fragment
    CHECK(r.data_bank_conflicts == 0);
}

// Cross-line conflict separation (High-2): two lanes in DIFFERENT 128-B lines
// that touch the SAME data banks with DIFFERENT words must NOT be counted as a
// bank conflict — different lines never share data banks, so each line forms
// its own pass/conflict group.  The buggy implementation merged words_per_bank
// across lines and reported 2 conflicts here.
TEST(global_cross_line_bank_no_conflict) {
    std::vector<LaneAccess> l(32);
    // 0x1078 (line 0x20): words 0x106, 0x107 -> banks 6, 7.
    l[0].lane = 0; l[0].base = 0x1078; l[0].len = 4; l[0].active = true;
    // 0x1198 (line 0x22): words 0x466, 0x467 -> banks 6, 7 (same banks,
    // different words, DIFFERENT line).
    l[1].lane = 1; l[1].base = 0x1198; l[1].len = 4; l[1].active = true;
    auto r = estimate(l.data(), 4);
    CHECK(r.lines.size() == 2);
    CHECK(r.data_bank_passes == 2);      // one pass per line
    CHECK(r.data_bank_conflicts == 0);   // cross-line banks never conflict
}

// Partial mask: 8 lanes contiguous -> 1 sector, 1 line, 1 pass.
TEST(global_partial_mask) {
    auto l = make(0, 4, 4, 0x000000ffu);
    auto r = estimate(l.data(), 4);
    CHECK(r.active_lanes == 8);
    CHECK(r.lane_requested_bytes == 32);
    CHECK(r.unique_useful_bytes == 32);
    CHECK(r.sectors.size() == 1);
    CHECK(r.data_bank_passes == 1);
}

// var/size sanity: width 8 wide contiguous covers 2 words per lane.
TEST(global_width8) {
    auto l = make(0, 8, 8, 0x0000ffffu);
    auto r = estimate(l.data(), 8);
    CHECK(r.lane_requested_bytes == 16 * 8);
    CHECK(r.unique_useful_bytes == 128);
    CHECK(r.lines.size() == 1);
}

// Model version exposed through JSON.
TEST(global_model_version) {
    auto l = make(0, 8, 4, 0xffffffffu);
    auto r = estimate(l.data(), 4);
    CHECK(r.model_version == semu::global_model::kGlobalModelVersion);
    CHECK(r.to_json().find("data_bank_passes") != std::string::npos);
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-global-model");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu global-model tests\n");
    }
    return failures == 0 ? 0 : 1;
}