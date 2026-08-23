// UnifiedV1Estimator — C++ port of the selector-free unified L1TEX model.
//
// Mirrors `unified_model.py` (version "unified-v1") and `sched_sim.formation`
// exactly so the C++ and Python oracles agree field-by-field on every frozen
// fixture.  Phase 8 extends it with the LDGSTS profiler counters (TWf, Sectors,
// TagConf, TSetAcc, SharedConf, GlobalConf) plus per-field confidence.
// This file must stay a pure function component: no MemoryService,
// no worker/scheduler state, no memory model.

#include <semu/memory/l1tex_model.hpp>

#include <algorithm>
#include <set>
#include <sstream>
#include <string>
#include <tuple>

namespace semu::l1tex {
namespace {

// Token bank hash used to order read-service passes (sched_sim.tbk).
//   tbk(l) = (l ^ (l>>2) ^ (l>>4) ^ (l>>6) ^ (l>>8)) & 3
int tbk(int l) { return (l ^ (l >> 2) ^ (l >> 4) ^ (l >> 6) ^ (l >> 8)) & 3; }

// Greedy conflict-free write-wave count (unified_model._write_wave_count).
int write_wave_count(const std::vector<int>& lanes,
                     const std::vector<std::set<int>>& write_banks) {
    std::vector<int> remaining = lanes;
    int waves = 0;
    while (!remaining.empty()) {
        std::set<int> used;
        std::vector<int> take;
        for (int lane : remaining) {
            const auto& banks = write_banks[static_cast<std::size_t>(lane)];
            bool conflict = false;
            for (int b : banks) {
                if (used.count(b)) { conflict = true; break; }
            }
            if (!conflict) {
                for (int b : banks) used.insert(b);
                take.push_back(lane);
            }
        }
        for (int lane : take) {
            remaining.erase(
                std::remove(remaining.begin(), remaining.end(), lane),
                remaining.end());
        }
        ++waves;
    }
    return waves;
}

// Frozen formation (sched_sim.formation).  Everything the unified model and
// the Phase 8 LDGSTS counters derive from.
struct Formation {
    std::vector<int> lanes;
    std::vector<int> tags;              // distinct 128-B line indices
    std::map<int, int> twf;             // line -> token wave id
    int twf_count = 0;                  // number of token waves (TWf)
    std::map<int, std::vector<int>> groups;   // token id -> lanes
    std::map<int, int> read_cycle;      // lane -> read pass index
    int read_passes = 0;                // R
    std::vector<std::set<int>> read_banks;   // per-lane read bank spans
    std::vector<std::set<int>> write_banks;  // per-lane write bank spans
    std::vector<std::vector<std::uint32_t>> read_words;   // per-lane read words
    std::vector<std::vector<std::uint32_t>> write_words;  // per-lane write words
    int nwords = 1;
    int gl = 32;
};

Formation form(const std::uint32_t goff[32], const std::uint32_t soff[32],
               int element_width, std::uint32_t mask) {
    Formation f;
    f.nwords = element_width / 4;
    f.gl = element_width == 4 ? 32 : element_width == 8 ? 16 : 8;
    for (int t = 0; t < 32; ++t) {
        if ((mask >> t) & 1u) f.lanes.push_back(t);
    }
    if (f.lanes.empty()) return f;

    // Distinct tags (128-B lines) a lane touches.
    for (int l : f.lanes) {
        for (std::uint32_t tag = goff[l] / 128;
             tag <= (goff[l] + static_cast<std::uint32_t>(element_width) - 1) / 128;
             ++tag) {
            if (std::find(f.tags.begin(), f.tags.end(), static_cast<int>(tag)) ==
                f.tags.end()) {
                f.tags.push_back(static_cast<int>(tag));
            }
        }
    }

    // Greedy T-stage coloring by token bank.
    {
        std::vector<int> rem = f.tags;
        int w = 0;
        while (!rem.empty()) {
            std::set<int> used;
            std::vector<int> take;
            for (int tg : rem) {
                const int b = tbk(tg);
                if (!used.count(b)) {
                    used.insert(b);
                    take.push_back(tg);
                }
            }
            for (int tg : take) {
                f.twf[tg] = w;
                rem.erase(std::remove(rem.begin(), rem.end(), tg), rem.end());
            }
            ++w;
        }
        f.twf_count = w;
    }

    // Seal lanes into tokens.
    for (int l : f.lanes) f.groups[l / f.gl].push_back(l);

    // Per-token greedy read-service passes, ordered by (twf[goff//128], lane).
    {
        int pass = 0;
        for (const auto& [gi, token_lanes] : f.groups) {
            (void)gi;
            std::vector<int> remaining = token_lanes;
            while (!remaining.empty()) {
                std::set<int> used;
                std::vector<int> pas;
                std::sort(remaining.begin(), remaining.end(),
                          [&](int a, int b) {
                              const int ta = f.twf.at(static_cast<int>(
                                  goff[a] / 128));
                              const int tb = f.twf.at(static_cast<int>(
                                  goff[b] / 128));
                              if (ta != tb) return ta < tb;
                              return a < b;
                          });
                for (int t : remaining) {
                    std::set<int> rb;
                    for (int k = 0; k < f.nwords; ++k) {
                        rb.insert(static_cast<int>((goff[t] / 4 + k) % 32));
                    }
                    bool conflict = false;
                    for (int b : rb) {
                        if (used.count(b)) { conflict = true; break; }
                    }
                    if (!conflict) {
                        for (int b : rb) used.insert(b);
                        pas.push_back(t);
                    }
                }
                for (int t : pas) {
                    remaining.erase(
                        std::remove(remaining.begin(), remaining.end(), t),
                        remaining.end());
                }
                for (int t : pas) f.read_cycle[t] = pass;
                ++pass;
            }
        }
        f.read_passes = pass;
    }

    // Per-lane read/write bank spans + word lists.
    f.read_banks.resize(32);
    f.write_banks.resize(32);
    f.read_words.resize(32);
    f.write_words.resize(32);
    for (int l : f.lanes) {
        for (int k = 0; k < f.nwords; ++k) {
            const std::uint32_t rw = goff[l] / 4 + static_cast<std::uint32_t>(k);
            const std::uint32_t ww = soff[l] / 4 + static_cast<std::uint32_t>(k);
            f.read_banks[static_cast<std::size_t>(l)].insert(
                static_cast<int>(rw % 32));
            f.write_banks[static_cast<std::size_t>(l)].insert(
                static_cast<int>(ww % 32));
            f.read_words[static_cast<std::size_t>(l)].push_back(rw);
            f.write_words[static_cast<std::size_t>(l)].push_back(ww);
        }
    }
    return f;
}

}  // namespace

int token_of(int lane, int element_width) {
    const int gl = element_width == 4 ? 32 : element_width == 8 ? 16 : 8;
    return lane / gl;
}

UnifiedEstimate UnifiedV1Estimator::estimate(
    const std::uint32_t goff[32], const std::uint32_t soff[32],
    int element_width, std::uint32_t mask) const {
    UnifiedEstimate result;
    const Formation f = form(goff, soff, element_width, mask);
    if (f.lanes.empty()) return result;

    // Per-token SharedWf = read_waves + write_waves - largest_joint_fiber.
    int token_id = 0;
    for (const auto& [gi, token_lanes] : f.groups) {
        (void)gi;
        std::set<int> rc;
        for (int l : token_lanes) rc.insert(f.read_cycle.at(l));
        const int read_waves = static_cast<int>(rc.size());
        const int write_waves = write_wave_count(token_lanes, f.write_banks);
        std::map<std::tuple<std::vector<int>, std::vector<int>>, int> fibers;
        int overlap = 0;
        for (int l : token_lanes) {
            std::vector<int> rb(f.read_banks[static_cast<std::size_t>(l)].begin(),
                                f.read_banks[static_cast<std::size_t>(l)].end());
            std::vector<int> wb(f.write_banks[static_cast<std::size_t>(l)].begin(),
                                f.write_banks[static_cast<std::size_t>(l)].end());
            auto key = std::make_tuple(rb, wb);
            int& c = fibers[key];
            ++c;
            if (c > overlap) overlap = c;
        }
        TokenStat ts;
        ts.token = token_id++;
        ts.lanes = static_cast<int>(token_lanes.size());
        ts.read_wf = read_waves;
        ts.write_wf = write_waves;
        ts.overlap_wf = overlap;
        ts.shared_wf = read_waves + write_waves - overlap;
        result.token_stats.push_back(ts);
        result.read_wf += read_waves;
        result.write_wf += write_waves;
        result.overlap_wf += overlap;
        result.shared_wf += ts.shared_wf;
    }
    result.tokens = static_cast<int>(result.token_stats.size());
    return result;
}

UnifiedEstimate UnifiedV1Estimator::estimate(
    const std::vector<std::uint32_t>& goff,
    const std::vector<std::uint32_t>& soff, int element_width,
    std::uint32_t mask) const {
    if (goff.size() != 32 || soff.size() != 32) {
        return UnifiedEstimate{};
    }
    std::uint32_t g[32], s[32];
    for (int i = 0; i < 32; ++i) {
        g[i] = goff[static_cast<std::size_t>(i)];
        s[i] = soff[static_cast<std::size_t>(i)];
    }
    return estimate(g, s, element_width, mask);
}

std::string UnifiedEstimate::to_json() const {
    std::ostringstream o;
    o << "{\"SharedWf\":" << shared_wf << ",\"ReadWf\":" << read_wf
      << ",\"WriteWf\":" << write_wf << ",\"OverlapWf\":" << overlap_wf
      << ",\"Tokens\":" << tokens << ",\"TokenStats\":[";
    for (std::size_t i = 0; i < token_stats.size(); ++i) {
        if (i) o << ",";
        const auto& t = token_stats[i];
        o << "{\"Token\":" << t.token << ",\"Lanes\":" << t.lanes
          << ",\"ReadWf\":" << t.read_wf << ",\"WriteWf\":" << t.write_wf
          << ",\"OverlapWf\":" << t.overlap_wf << ",\"SharedWf\":"
          << t.shared_wf << "}";
    }
    o << "]}";
    return o.str();
}

const char* confidence_name(Confidence c) {
    switch (c) {
        case Confidence::kExactArchitectural: return "exact-architectural";
        case Confidence::kExactEmpirical: return "exact-empirical";
        case Confidence::kApproximate: return "approximate";
        default: return "unsupported";
    }
}

LdgstsEstimate UnifiedV1Estimator::estimate_ldgsts(
    const std::uint32_t goff[32], const std::uint32_t soff[32],
    int element_width, std::uint32_t mask,
    const std::string& cache_policy) const {
    LdgstsEstimate r;
    r.cache_policy = cache_policy.empty() ? "default" : cache_policy;
    r.applicability =
        "unified-v1 (unified_model.py): per sealed 128-B token "
        "SharedWf = read_waves + write_waves - largest_joint_fiber.  Exact on "
        "the frozen affine / near-linear / equality / token-accumulator probe "
        "domains (arch/l1tex shared_bank_conflicts.md §4.6): a FULL warp with "
        "a structured SOURCE and a structured DESTINATION (constant stride or "
        "broadcast on both sides).  A scattered destination is approximate "
        "even when the source is affine; random traffic is approximate; .cg "
        "bypass and miss-path suppression are unsupported.";

    r.base = estimate(goff, soff, element_width, mask);
    const Formation f = form(goff, soff, element_width, mask);

    // Pure architectural counts.
    r.twf = f.twf_count;
    r.tag_conf = f.twf_count > 0 ? f.twf_count - 1 : 0;
    r.tset_acc = static_cast<int>(f.tags.size());
    {
        std::set<std::uint32_t> secs;
        for (int l : f.lanes) {
            for (std::uint32_t s = goff[l] / 32;
                 s <= (goff[l] + static_cast<std::uint32_t>(element_width) - 1) / 32;
                 ++s) {
                secs.insert(s);
            }
        }
        r.sectors = static_cast<int>(secs.size());
    }

    // Conflict counts (per-token, per-bank distinct-word counts).  The read
    // side (L1/global data banks) and the write side (shared banks) are
    // SEPARATE counters and are never merged.
    for (const auto& [gi, token_lanes] : f.groups) {
        (void)gi;
        std::map<std::uint32_t, std::set<std::uint32_t>> rw;
        std::map<std::uint32_t, std::set<std::uint32_t>> ww;
        for (int l : token_lanes) {
            for (std::uint32_t w : f.read_words[static_cast<std::size_t>(l)]) {
                rw[w % 32].insert(w);
            }
            for (std::uint32_t w : f.write_words[static_cast<std::size_t>(l)]) {
                ww[w % 32].insert(w);
            }
        }
        for (const auto& [bank, words] : rw) {
            (void)bank;
            if (words.size() >= 2) {
                r.global_conf += static_cast<int>(words.size()) - 1;
            }
        }
        for (const auto& [bank, words] : ww) {
            (void)bank;
            if (words.size() >= 2) {
                r.shared_conf += static_cast<int>(words.size()) - 1;
            }
        }
    }

    // Confidence per SIM_PLAN §5 + shared_bank_conflicts.md scope.
    if (r.cache_policy == "cg") {
        // .cg bypasses L1: the L1-read -> shared-write service model and the
        // bank/tag service counters do not apply.
        r.shared_wf_confidence = Confidence::kUnsupported;
        r.conflict_confidence = Confidence::kUnsupported;
    } else {
        // Structured = full warp with a structured SOURCE AND a structured
        // DESTINATION (constant stride or broadcast on each side): the
        // domains the unified model is exact on (§4.6 structured sweep
        // tables).  Round-2 H2: a scattered destination is NEVER upgraded to
        // exact by a source-side affine — the applicability declares
        // "scattered 8/16 B destinations ... approximate", and the frozen
        // exact tables only cover structured patterns on BOTH sides.
        bool full = mask == 0xFFFFFFFFu;
        bool g_stride = true, s_stride = true;
        bool g_equal = true, s_equal = true;
        for (int i = 1; i < 32; ++i) {
            if (goff[i] - goff[i - 1] != goff[1] - goff[0]) g_stride = false;
            if (soff[i] - soff[i - 1] != soff[1] - soff[0]) s_stride = false;
            if (goff[i] != goff[0]) g_equal = false;
            if (soff[i] != soff[0]) s_equal = false;
        }
        const bool g_structured = g_stride || g_equal;
        const bool s_structured = s_stride || s_equal;
        const bool structured = full && g_structured && s_structured;
        r.shared_wf_confidence =
            structured ? Confidence::kExactEmpirical : Confidence::kApproximate;
        // Conflict counters are definitional (not hardware-validated beyond
        // the corpus fields); never exact.
        r.conflict_confidence = Confidence::kApproximate;
    }
    return r;
}

std::string LdgstsEstimate::to_json() const {
    std::ostringstream o;
    o << "{\"model_version\":\"" << model_version
      << "\",\"cache_policy\":\"" << cache_policy << "\","
      << base.to_json().substr(1, base.to_json().size() - 2)
      << ",\"TWf\":" << twf << ",\"TagConf\":" << tag_conf
      << ",\"TSetAcc\":" << tset_acc << ",\"Sectors\":" << sectors
      << ",\"SharedConf\":" << shared_conf << ",\"GlobalConf\":" << global_conf
      << ",\"SharedWfConfidence\":\"" << confidence_name(shared_wf_confidence)
      << "\",\"CountConfidence\":\"" << confidence_name(count_confidence)
      << "\",\"ConflictConfidence\":\""
      << confidence_name(conflict_confidence)
      << "\",\"applicability\":\"" << applicability << "\"}";
    return o.str();
}

}  // namespace semu::l1tex
