// Shared-memory LDS/STS bank-conflict model (SIM_PLAN Phase 8).  Pure
// read-only analysis: never changes memory values, scoreboard completion,
// atomic linearization or happens-before edges.

#include <semu/shared_bank.hpp>

#include <algorithm>
#include <map>
#include <set>
#include <sstream>

namespace semu::shared_bank {

namespace {

struct LaneWords {
    std::uint32_t lane = 0;
    std::uint64_t base = 0;
    std::uint64_t len = 0;
    std::vector<std::uint32_t> banks;  // one bank per word
    std::vector<std::uint32_t> words;  // word index = byte_address / 4
};

// One pass of one lane group: the lanes served + the claimed (bank, word)
// map used for conflict checks.
struct Pass {
    std::vector<std::uint32_t> lanes;
    std::map<std::uint32_t, std::uint32_t> claimed;  // bank -> word
};

}  // namespace

SharedAccessEstimate estimate(const std::vector<LaneAccess>& lanes,
                              std::uint32_t width, bool is_write) {
    SharedAccessEstimate r;
    r.is_write = is_write;
    r.element_width = width;
    r.lane_bank.assign(32, 0);

    if (width != 4 && width != 8 && width != 16) return r;

    // Lane-group partition: 4 B whole warp, 8 B half warp, 16 B quarter warp.
    const int gl = width == 4 ? 32 : width == 8 ? 16 : 8;
    const int nwords = static_cast<int>(width / 4);

    // Collect active lanes in id order.
    std::vector<LaneWords> act;
    for (std::uint32_t l = 0; l < 32; ++l) {
        if (l >= lanes.size()) break;
        const auto& la = lanes[l];
        if (!la.active || la.len != width) continue;
        LaneWords lw;
        lw.lane = l;
        lw.base = la.base;
        lw.len = la.len;
        const std::uint64_t w0 = la.base / 4;
        for (int k = 0; k < nwords; ++k) {
            const std::uint32_t word = static_cast<std::uint32_t>(w0 + k);
            lw.words.push_back(word);
            lw.banks.push_back(word % 32);
        }
        act.push_back(std::move(lw));
        r.lane_bank[static_cast<std::size_t>(l)] =
            lw.banks.empty() ? 0 : lw.banks[0];
    }
    if (act.empty()) return r;
    r.active_lanes = static_cast<std::uint32_t>(act.size());

    // Per-group pass formation.
    const int ngroups = 32 / gl;
    std::vector<std::vector<Pass>> groups(static_cast<std::size_t>(ngroups));

    for (int gi = 0; gi < ngroups; ++gi) {
        const std::uint32_t lo = static_cast<std::uint32_t>(gi * gl);
        const std::uint32_t hi = lo + static_cast<std::uint32_t>(gl);
        std::vector<LaneWords> group;
        for (const auto& lw : act) {
            if (lw.lane >= lo && lw.lane < hi) group.push_back(lw);
        }
        if (group.empty()) continue;
        auto& passes = groups[static_cast<std::size_t>(gi)];

        // Greedy placement in lane-id order.  A lane joins the first pass
        // where none of its (bank, word) pairs collides with a DIFFERENT word
        // already claimed on that bank; an identical (bank, word) is a
        // broadcast/coalesce and never blocks placement.
        for (const auto& lw : group) {
            bool placed = false;
            for (auto& p : passes) {
                bool conflict = false;
                for (std::size_t i = 0; i < lw.banks.size(); ++i) {
                    auto it = p.claimed.find(lw.banks[i]);
                    if (it == p.claimed.end()) continue;
                    if (it->second != lw.words[i]) {
                        conflict = true;
                        break;
                    }
                    ++r.broadcast_count;  // identical (bank, word)
                }
                if (!conflict) {
                    p.lanes.push_back(lw.lane);
                    for (std::size_t i = 0; i < lw.banks.size(); ++i) {
                        p.claimed[lw.banks[i]] = lw.words[i];
                    }
                    placed = true;
                    break;
                }
            }
            if (!placed) {
                Pass np;
                np.lanes.push_back(lw.lane);
                for (std::size_t i = 0; i < lw.banks.size(); ++i) {
                    np.claimed[lw.banks[i]] = lw.words[i];
                }
                passes.push_back(std::move(np));
            }
        }
    }

    // Assemble pass detail + conflict reason chains.  Passes are numbered
    // globally across groups (a group's pass i is a distinct service event),
    // matching the LSU lane-group model.
    std::uint32_t pass_global = 0;
    std::vector<std::pair<int, int>> pass_loc;  // (group, pass) per global id
    for (int gi = 0; gi < ngroups; ++gi) {
        auto& passes = groups[static_cast<std::size_t>(gi)];
        for (std::size_t p = 0; p < passes.size(); ++p) {
            PassDetail pd;
            pd.pass = pass_global;
            pass_loc.emplace_back(gi, static_cast<int>(p));
            std::set<std::uint32_t> banks;
            for (auto ln : passes[p].lanes) {
                pd.lanes.push_back(ln);
                for (const auto& kv : passes[p].claimed) banks.insert(kv.first);
            }
            // Keep the distinct bank list (not per-lane) for reporting.
            for (const auto& kv : passes[p].claimed) {
                banks.insert(kv.first);
            }
            for (auto b : banks) pd.banks.push_back(b);
            r.passes_detail.push_back(std::move(pd));
            ++pass_global;
        }
    }
    r.passes = pass_global;

    // Conflict edges: a lane placed in pass p was deferred because of a bank
    // it shares (with a different word) with some lane in an earlier pass.
    // For each deferred lane emit one Conflict per distinct (bank, first
    // blocking pass) with the reason chain.
    for (int gi = 0; gi < ngroups; ++gi) {
        auto& passes = groups[static_cast<std::size_t>(gi)];
        // lane -> (pass index, lane index)
        std::map<std::uint32_t, std::pair<std::size_t, std::size_t>> loc;
        for (std::size_t p = 0; p < passes.size(); ++p) {
            for (std::size_t i = 0; i < passes[p].lanes.size(); ++i) {
                loc[passes[p].lanes[i]] = {p, i};
            }
        }
        for (std::size_t p = 1; p < passes.size(); ++p) {
            for (auto lb : passes[p].lanes) {
                const LaneWords* lw = nullptr;
                for (const auto& g : act) {
                    if (g.lane == lb) { lw = &g; break; }
                }
                if (!lw) continue;
                // Earliest pass that blocks this lane.
                for (std::uint32_t q = 0; q < p; ++q) {
                    for (auto la : passes[q].lanes) {
                        const LaneWords* other = nullptr;
                        for (const auto& g : act) {
                            if (g.lane == la) { other = &g; break; }
                        }
                        if (!other) continue;
                        for (std::size_t i = 0; i < lw->banks.size(); ++i) {
                            for (std::size_t j = 0; j < other->banks.size();
                                 ++j) {
                                if (lw->banks[i] != other->banks[j]) continue;
                                if (lw->words[i] == other->words[j]) continue;
                                Conflict c;
                                c.bank = lw->banks[i];
                                c.lane_a = other->lane;
                                c.word_a = other->words[j];
                                c.lane_b = lw->lane;
                                c.word_b = lw->words[i];
                                c.pass_a = q;
                                c.reason =
                                    "lane " + std::to_string(c.lane_b) +
                                    " (word " + std::to_string(c.word_b) +
                                    ") collides with lane " +
                                    std::to_string(c.lane_a) + " (word " +
                                    std::to_string(c.word_a) + ") in bank " +
                                    std::to_string(c.bank) + " (pass " +
                                    std::to_string(q) + ") -> deferred to pass " +
                                    std::to_string(p);
                                r.conflicts.push_back(std::move(c));
                                ++r.conflict_count;
                            }
                        }
                    }
                }
            }
        }
    }
    return r;
}

SharedAccessEstimate estimate(const std::uint64_t base[32],
                              std::uint32_t width, std::uint32_t mask,
                              bool is_write) {
    std::vector<LaneAccess> lanes(32);
    for (std::uint32_t l = 0; l < 32; ++l) {
        lanes[l].lane = l;
        lanes[l].base = base[l];
        lanes[l].len = width;
        lanes[l].active = (mask >> l) & 1u;
    }
    return estimate(lanes, width, is_write);
}

std::string SharedAccessEstimate::to_json() const {
    std::ostringstream o;
    o << "{\"model_version\":\"" << model_version
      << "\",\"is_write\":" << (is_write ? "true" : "false")
      << ",\"element_width\":" << element_width
      << ",\"active_lanes\":" << active_lanes
      << ",\"passes\":" << passes
      << ",\"conflicts\":" << conflict_count
      << ",\"broadcasts\":" << broadcast_count
      << ",\"passes_detail\":[";
    for (std::size_t i = 0; i < passes_detail.size(); ++i) {
        if (i) o << ",";
        o << "{\"pass\":" << passes_detail[i].pass << ",\"lanes\":[";
        for (std::size_t j = 0; j < passes_detail[i].lanes.size(); ++j) {
            if (j) o << ",";
            o << passes_detail[i].lanes[j];
        }
        o << "],\"banks\":[";
        for (std::size_t j = 0; j < passes_detail[i].banks.size(); ++j) {
            if (j) o << ",";
            o << passes_detail[i].banks[j];
        }
        o << "]}";
    }
    o << "],\"conflicts\":[";
    for (std::size_t i = 0; i < conflicts.size(); ++i) {
        if (i) o << ",";
        o << "{\"bank\":" << conflicts[i].bank
          << ",\"lane_a\":" << conflicts[i].lane_a
          << ",\"word_a\":" << conflicts[i].word_a
          << ",\"lane_b\":" << conflicts[i].lane_b
          << ",\"word_b\":" << conflicts[i].word_b
          << ",\"pass_a\":" << conflicts[i].pass_a
          << ",\"reason\":\"" << conflicts[i].reason << "\"}";
    }
    o << "]}";
    return o.str();
}

}  // namespace semu::shared_bank
