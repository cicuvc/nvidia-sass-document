// Global LDG/STG coalescing / sector-line model (SIM_PLAN Phase 8).  Pure
// read-only analysis: never changes memory values, scoreboard completion,
// atomic linearization or happens-before edges.

#include <semu/memory/global_model.hpp>

#include <algorithm>
#include <map>
#include <set>
#include <sstream>

namespace semu::global_model {

namespace {

// Token-bank hash for 128-B lines (the L1TEX T-stage tag pipeline).
int tbk(std::uint64_t line) {
    const auto l = static_cast<std::uint32_t>(line);
    return static_cast<int>((l ^ (l >> 2) ^ (l >> 4) ^ (l >> 6) ^ (l >> 8)) &
                            3);
}

}  // namespace

GlobalAccessEstimate estimate(const shared_bank::LaneAccess* lanes,
                              std::uint32_t width) {
    GlobalAccessEstimate r;
    if (!lanes || (width != 1 && width != 2 && width != 4 && width != 8 &&
                   width != 16)) {
        return r;
    }

    std::vector<std::pair<std::uint64_t, std::uint64_t>> ranges;  // (base,len)
    for (std::uint32_t l = 0; l < 32; ++l) {
        const auto& la = lanes[l];
        if (!la.active || la.len == 0) continue;
        const std::uint64_t base = la.base;
        const std::uint64_t len = la.len;
        r.active_lanes++;
        r.lane_requested_bytes += len;
        ranges.emplace_back(base, len);
        // A lane spans [base, base+len): it may touch several 32-B sectors
        // and 128-B lines when it crosses a boundary.
        for (std::uint64_t k = 0; k < len; ++k) {
            const std::uint64_t a = base + k;
            const std::uint64_t sector = a / kSectorBytes;
            if (std::find(r.sectors.begin(), r.sectors.end(), sector) ==
                r.sectors.end()) {
                r.sectors.push_back(sector);
            }
            const std::uint64_t line = a / kLineBytes;
            if (std::find(r.lines.begin(), r.lines.end(), line) ==
                r.lines.end()) {
                r.lines.push_back(line);
            }
        }
        LaneMapping m;
        m.lane = l;
        m.base = base;
        m.len = len;
        m.sector = base / kSectorBytes;
        m.line = base / kLineBytes;
        m.first_bank = static_cast<std::uint32_t>((base / 4) % 32);
        m.active = true;
        r.lane_map.push_back(std::move(m));
    }
    std::sort(r.sectors.begin(), r.sectors.end());
    std::sort(r.lines.begin(), r.lines.end());

    // Distinct bytes covered (union of per-lane [base, base+len)) — the
    // "unique useful" bytes, computed independently of the lane-width sum
    // (codex review High-1).
    if (!ranges.empty()) {
        std::sort(ranges.begin(), ranges.end());
        std::uint64_t cur_lo = ranges[0].first;
        std::uint64_t cur_hi = ranges[0].first + ranges[0].second;
        std::uint64_t unique = 0;
        for (std::size_t i = 1; i < ranges.size(); ++i) {
            const auto [lo, len] = ranges[i];
            if (lo > cur_hi) {
                unique += cur_hi - cur_lo;
                cur_lo = lo;
                cur_hi = lo + len;
            } else {
                cur_hi = std::max(cur_hi, lo + len);
            }
        }
        unique += cur_hi - cur_lo;
        r.unique_useful_bytes = unique;
    }
    // Duplicate/reuse bytes: requested by more than one lane (>=0; ==0 when
    // every byte is distinct).
    r.duplicate_reuse_bytes =
        r.lane_requested_bytes > r.unique_useful_bytes
            ? r.lane_requested_bytes - r.unique_useful_bytes
            : 0;
    r.sector_fetch_bytes =
        static_cast<std::uint64_t>(r.sectors.size()) * kSectorBytes;
    r.line_fill_bytes =
        static_cast<std::uint64_t>(r.lines.size()) * kLineBytes;
    // Overfetch is measured against the unique useful bytes (bytes fetched
    // but consumed by NO lane), never against the lane-width sum.
    r.sector_overfetch_bytes =
        r.sector_fetch_bytes > r.unique_useful_bytes
            ? r.sector_fetch_bytes - r.unique_useful_bytes
            : 0;
    r.line_overfetch_bytes =
        r.line_fill_bytes > r.unique_useful_bytes
            ? r.line_fill_bytes - r.unique_useful_bytes
            : 0;
    // Clearly denominated: efficiency = useful/transferred ∈ [0,1];
    // reuse factor = requested/useful (≥1 only when lanes share bytes).
    r.coalescing_efficiency =
        r.sector_fetch_bytes > 0
            ? static_cast<double>(r.unique_useful_bytes) /
                  static_cast<double>(r.sector_fetch_bytes)
            : 0.0;
    r.broadcast_reuse_factor =
        r.unique_useful_bytes > 0
            ? static_cast<double>(r.lane_requested_bytes) /
                  static_cast<double>(r.unique_useful_bytes)
            : 0.0;

    // L1 data-bank service: each lane's byte range is split into per-128-B
    // line FRAGMENTS; every line forms its own pass/conflict group (different
    // lines never share data banks).  Within a line, greedy bank-conflict
    // passes over 32 banks x 4 B words; a pass may hold at most one distinct
    // word per bank (identical (bank, word) coalesces to the same slot).
    // data_bank_conflicts counts, per bank, the number of distinct words
    // beyond the first (order-independent).
    {
        struct Frag {
            std::uint32_t lane;
            std::uint32_t w0;   // first word index (addr/4)
            std::uint32_t nw;   // number of words in this fragment
        };
        std::map<std::uint64_t, std::vector<Frag>> line_frags;
        for (std::uint32_t l = 0; l < 32; ++l) {
            const auto& la = lanes[l];
            if (!la.active || la.len == 0) continue;
            const std::uint64_t line0 = la.base / kLineBytes;
            const std::uint64_t line1 = (la.base + la.len - 1) / kLineBytes;
            for (std::uint64_t ln = line0; ln <= line1; ++ln) {
                const std::uint64_t f0 =
                    std::max(la.base, ln * static_cast<std::uint64_t>(kLineBytes));
                const std::uint64_t f1 = std::min(
                    la.base + la.len,
                    (ln + 1) * static_cast<std::uint64_t>(kLineBytes));
                const std::uint64_t w0 = f0 / 4;
                const std::uint64_t w1 = (f1 - 1) / 4;
                line_frags[ln].push_back(
                    {l, static_cast<std::uint32_t>(w0),
                     static_cast<std::uint32_t>(w1 - w0 + 1)});
            }
        }
        int data_passes = 0;
        int data_conflicts = 0;
        for (const auto& [line, frags] : line_frags) {
            (void)line;
            std::vector<std::map<std::uint32_t, std::uint32_t>> passes;  // bank->word
            std::map<std::uint32_t, std::set<std::uint32_t>> words_per_bank;
            for (const auto& frag : frags) {
                std::vector<std::pair<std::uint32_t, std::uint32_t>> pairs;
                for (std::uint32_t k = 0; k < frag.nw; ++k) {
                    const std::uint32_t word = frag.w0 + k;
                    pairs.emplace_back(word % 32, word);
                    words_per_bank[word % 32].insert(word);
                }
                bool placed = false;
                for (auto& p : passes) {
                    bool conflict = false;
                    for (const auto& [b, w] : pairs) {
                        auto it = p.find(b);
                        if (it == p.end()) continue;
                        if (it->second != w) { conflict = true; break; }
                    }
                    if (!conflict) {
                        for (const auto& [b, w] : pairs) p[b] = w;
                        placed = true;
                        break;
                    }
                }
                if (!placed) {
                    std::map<std::uint32_t, std::uint32_t> m;
                    for (const auto& [b, w] : pairs) m[b] = w;
                    passes.push_back(std::move(m));
                }
            }
            data_passes += static_cast<int>(passes.size());
            for (const auto& [bank, words] : words_per_bank) {
                (void)bank;
                if (words.size() >= 2) {
                    data_conflicts += static_cast<int>(words.size()) - 1;
                }
            }
        }
        r.data_bank_passes = data_passes;
        r.data_bank_conflicts = data_conflicts;
    }

    // Tag-pipeline service: distinct 128-B lines colored by the token-bank
    // hash (tbk) into conflict-free waves — the same T-stage rule the LDGSTS
    // model uses, applied to an ordinary global access.
    {
        std::vector<std::uint64_t> rem = r.lines;
        int waves = 0;
        while (!rem.empty()) {
            std::set<int> used;
            std::vector<std::uint64_t> take;
            for (auto ln : rem) {
                const int b = tbk(ln);
                if (!used.count(b)) {
                    used.insert(b);
                    take.push_back(ln);
                }
            }
            if (take.empty()) {  // defensive: never loops on identical hashes
                take.push_back(rem.front());
            }
            for (auto tg : take) {
                rem.erase(std::remove(rem.begin(), rem.end(), tg), rem.end());
            }
            ++waves;
        }
        r.tag_bank_passes = waves;
    }
    return r;
}

std::string GlobalAccessEstimate::to_json() const {
    std::ostringstream o;
    o << "{\"model_version\":\"" << model_version << "\",\"active_lanes\":"
      << active_lanes << ",\"lane_requested_bytes\":" << lane_requested_bytes
      << ",\"unique_useful_bytes\":" << unique_useful_bytes
      << ",\"duplicate_reuse_bytes\":" << duplicate_reuse_bytes
      << ",\"coalescing_efficiency\":" << coalescing_efficiency
      << ",\"broadcast_reuse_factor\":" << broadcast_reuse_factor
      << ",\"sectors\":[";
    for (std::size_t i = 0; i < sectors.size(); ++i) {
        if (i) o << ",";
        o << sectors[i];
    }
    o << "],\"lines\":[";
    for (std::size_t i = 0; i < lines.size(); ++i) {
        if (i) o << ",";
        o << lines[i];
    }
    o << "],\"data_bank_passes\":" << data_bank_passes
      << ",\"data_bank_conflicts\":" << data_bank_conflicts
      << ",\"tag_bank_passes\":" << tag_bank_passes
      << ",\"sector_fetch_bytes\":" << sector_fetch_bytes
      << ",\"line_fill_bytes\":" << line_fill_bytes
      << ",\"sector_overfetch_bytes\":" << sector_overfetch_bytes
      << ",\"line_overfetch_bytes\":" << line_overfetch_bytes << "}";
    return o.str();
}

}  // namespace semu::global_model