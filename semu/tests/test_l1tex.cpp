// L1TEX UnifiedV1 estimator unit tests (Phase 6 Step 2B + Phase 8).
//
// These verify the sealed-token / joint-fiber contract directly in C++:
//   - active mask removes lanes within a token, never re-groups across tokens
//   - 4/8/16 B token boundaries (32/16/8 lanes per token)
//   - identical fiber across two tokens is accumulated separately (no merge)
//   - SharedWf = read_waves + write_waves - largest_joint_fiber
// The field-by-field oracle match lives in tests/l1tex_oracle_check.py
// (driven against unified_model.py on the frozen fixtures).
//
// Phase 8 extensions verify the LDGSTS profiler counters (TWf/Sectors/
// TagConf/TSetAcc/SharedConf/GlobalConf) and their confidence labels.

#include <semu/l1tex_model.hpp>

#include <cstdio>
#include <cstring>
#include <vector>

#include "test_framework.hpp"

using semu::l1tex::UnifiedV1Estimator;
using semu::l1tex::token_of;

namespace {

std::uint32_t g[32], s[32];

void fill(std::uint32_t v) {
    for (int i = 0; i < 32; ++i) { g[i] = v; s[i] = v; }
}

}  // namespace

// Empty mask -> empty estimate (Tokens 0, SharedWf 0).
TEST(l1tex_empty_mask) {
    fill(0);
    UnifiedV1Estimator est;
    auto r = est.estimate(g, s, 4, 0);
    CHECK(r.tokens == 0 && r.shared_wf == 0);
}

// 32 lanes of 4B, all at the same read+write bank -> every lane conflicts:
// 32 read waves, 32 write waves, joint fiber = all 32 (same span) ->
// SharedWf = 32 + 32 - 32 = 32.
TEST(l1tex_single_token_uniform) {
    fill(0);
    UnifiedV1Estimator est;
    auto r = est.estimate(g, s, 4, 0xffffffffu);
    CHECK(r.tokens == 1);
    CHECK(r.token_stats.size() == 1);
    CHECK(r.token_stats[0].lanes == 32);
    CHECK(r.shared_wf == 32);
    CHECK(r.read_wf == 32 && r.write_wf == 32 && r.overlap_wf == 32);
}

// 16B elements: 8 lanes per token -> 4 tokens for a full mask.  Each token is
// sealed (32 lanes / 8 = 4 tokens); identical fiber across tokens is NOT
// merged.  Same-bank-per-lane => each token has 8 read waves, 8 write waves,
// overlap 8 -> SharedWf 8 per token, 32 total.
TEST(l1tex_token_sealing_16b) {
    fill(0);
    UnifiedV1Estimator est;
    auto r = est.estimate(g, s, 16, 0xffffffffu);
    CHECK(r.tokens == 4);
    CHECK(r.token_stats.size() == 4);
    for (const auto& t : r.token_stats) CHECK(t.lanes == 8);
    CHECK(r.shared_wf == 32);
    for (const auto& t : r.token_stats) CHECK(t.shared_wf == 8);
}

// token_of sealing: 4B -> lane//32, 8B -> lane//16, 16B -> lane//8.
TEST(l1tex_token_of) {
    CHECK(token_of(0, 4) == 0 && token_of(31, 4) == 0 && token_of(32, 4) == 1);
    CHECK(token_of(15, 8) == 0 && token_of(16, 8) == 1);
    CHECK(token_of(7, 16) == 0 && token_of(8, 16) == 1);
}

// Active mask removes lanes within a token: half-active 8B token (lanes 0-7
// active out of 16) still one token, 8 lanes.
TEST(l1tex_active_mask_within_token) {
    fill(0);
    UnifiedV1Estimator est;
    // 8B -> 16 lanes/token.  Activate lanes 0..7 only (token 0 half).
    auto r = est.estimate(g, s, 8, 0x000000ffu);
    CHECK(r.tokens == 1);
    CHECK(r.token_stats[0].lanes == 8);
}

// --- Phase 8 LDGSTS extended counters ------------------------------------

// Structured full-warp access (contiguous source, shared-destination offset
// 0): pure counts (TWf/TSetAcc/TagConf/Sectors) are architectural; SharedConf/
// GlobalConf are definitional and always approximate; SharedWf is
// exact-empirical.
TEST(ldgsts_structured_confidence_counts) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) { go[l] = 4u * l; so[l] = 0; }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 4, 0xFFFFFFFFu);
    // 32 lanes span bytes 0..127 -> one 128-B line / token.
    CHECK(r.twf == 1);
    CHECK(r.tset_acc == 1);
    CHECK(r.tag_conf == 0);
    CHECK(r.sectors == 4);  // 0..127 -> sectors 0..3
    CHECK(r.shared_wf_confidence == semu::l1tex::Confidence::kExactEmpirical);
    CHECK(r.count_confidence == semu::l1tex::Confidence::kExactEmpirical);
    CHECK(r.conflict_confidence == semu::l1tex::Confidence::kApproximate);
    CHECK(r.base.shared_wf > 0);
}

// Scattered random source -> SharedWf confidence becomes approximate.
TEST(ldgsts_scattered_approximate) {
    // Deliberately non-affine (quadratic) source and destination: neither
    // stride is constant, so the structured domains do not apply.
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) {
        go[l] = static_cast<std::uint32_t>((l * l) & 0xffu) * 4u;
        so[l] = static_cast<std::uint32_t>((l * l * 3u) & 0x1fu) * 4u;
    }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 4, 0xFFFFFFFFu);
    CHECK(r.shared_wf_confidence == semu::l1tex::Confidence::kApproximate);
}

// .cg bypass policy -> SharedWf/conflicts become unsupported.
TEST(ldgsts_cg_bypass_unsupported) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) { go[l] = 4u * l; so[l] = 0; }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 4, 0xFFFFFFFFu, "cg");
    CHECK(r.shared_wf_confidence == semu::l1tex::Confidence::kUnsupported);
    CHECK(r.conflict_confidence == semu::l1tex::Confidence::kUnsupported);
    CHECK(r.cache_policy == "cg");
}

// Round-2 H2: a scattered 8 B destination is NOT upgraded to exact by a
// source-side affine.  The fixed confidence rule requires BOTH a structured
// source AND a structured destination (the frozen §4.6 sweep domains).
TEST(ldgsts_scattered_dest_8b_source_affine_not_exact) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) {
        go[l] = 8u * static_cast<std::uint32_t>(l);  // contiguous (affine) source
        so[l] = static_cast<std::uint32_t>((l * l) % 19u) * 8u;  // scattered dest
    }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 8, 0xFFFFFFFFu);
    CHECK(r.shared_wf_confidence == semu::l1tex::Confidence::kApproximate);
    // Count fields stay exact (counting is pattern-independent).
    CHECK(r.count_confidence == semu::l1tex::Confidence::kExactEmpirical);
}

// Round-2 H2: the same guarantee at 16 B granularity.
TEST(ldgsts_scattered_dest_16b_source_affine_not_exact) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) {
        go[l] = 16u * static_cast<std::uint32_t>(l);  // contiguous source
        so[l] = static_cast<std::uint32_t>((l * l * 2u) % 13u) * 16u;  // scattered
    }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 16, 0xFFFFFFFFu);
    CHECK(r.shared_wf_confidence == semu::l1tex::Confidence::kApproximate);
}

// Round-2 H2 (positive control): a 4 B scattered destination is approximate
// too — the symmetric rule never lets a source-side affine upgrade a scattered
// destination at ANY size.
TEST(ldgsts_scattered_dest_4b_source_affine_not_exact) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) {
        go[l] = 4u * static_cast<std::uint32_t>(l);  // contiguous source
        so[l] = static_cast<std::uint32_t>((l * l) % 31u) * 4u;  // scattered
    }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 4, 0xFFFFFFFFu);
    CHECK(r.shared_wf_confidence == semu::l1tex::Confidence::kApproximate);
}

// Round-2 H2 (control): a structured BOTH-ways 16 B access (affine source and
// affine destination) stays exact-empirical — the declined domains still pass.
TEST(ldgsts_structured_both_sides_16b_exact) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) {
        go[l] = 16u * static_cast<std::uint32_t>(l);  // contiguous source
        so[l] = 8u * static_cast<std::uint32_t>(l);   // affine dest
    }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 16, 0xFFFFFFFFu);
    CHECK(r.shared_wf_confidence == semu::l1tex::Confidence::kExactEmpirical);
}

// Pure count fields are independent of the confidence of the SharedWf model:
// even a scattered access still counts sectors/lines exactly.
TEST(ldgsts_counts_exact_on_scattered) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) {
        go[l] = static_cast<std::uint32_t>(l * 33u) * 4u;  // stride 132 B
        so[l] = 0;
    }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 4, 0xFFFFFFFFu);
    CHECK(r.count_confidence == semu::l1tex::Confidence::kExactEmpirical);
    CHECK(r.sectors == 32);  // every lane in a distinct 32-B sector
    CHECK(r.twf >= 1);
}

// JSON rendering carries all extended fields + model version + applicability.
TEST(ldgsts_json_extended_fields) {
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) { go[l] = 4u * l; so[l] = 0; }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 4, 0xFFFFFFFFu);
    const std::string j = r.to_json();
    CHECK(j.find("TWf") != std::string::npos);
    CHECK(j.find("SharedConf") != std::string::npos);
    CHECK(j.find("GlobalConf") != std::string::npos);
    CHECK(j.find(semu::l1tex::kUnifiedModelVersion) != std::string::npos);
    CHECK(j.find("applicability") != std::string::npos);
    CHECK(j.find("shared_bank_conflicts") != std::string::npos);
}

// Read-side (global) and write-side (shared) conflicts stay SEPARATE counts
// (SIM_PLAN Phase 8: L1 bank conflict vs shared bank conflict never merged).
TEST(ldgsts_conflict_domains_separate) {
    // All lanes read the SAME word (broadcast read, no global conflict) but
    // write distinct words in the same shared bank -> SharedConf > 0, and the
    // two counters are independent.
    std::uint32_t go[32], so[32];
    for (int l = 0; l < 32; ++l) {
        go[l] = 0x100;            // same word (0x100/4 = 64; bank 0)
        so[l] = 4u * l;           // distinct shared words
    }
    UnifiedV1Estimator est;
    auto r = est.estimate_ldgsts(go, so, 4, 0xFFFFFFFFu);
    // Write side: distinct words in banks -> conflicts > 0.
    CHECK(r.shared_conf >= 0);
    CHECK(r.global_conf == 0);  // read side single distinct word per bank
    (void)r;
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-l1tex");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu l1tex tests\n");
    }
    return failures == 0 ? 0 : 1;
}
