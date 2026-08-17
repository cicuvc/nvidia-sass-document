// Event-based L2 layer (Phase 6 Step 2C).  Trace-only: never changes
// functional memory values, scoreboard completion, atomic linearization, or
// happens-before edges.  A launch-level engine may be shared by parallel
// workers (High-3): issue/completion are mutex-guarded so request/
// completion/event ids stay globally unique.

#include <semu/l2_events.hpp>

#include <algorithm>
#include <sstream>

namespace semu {

L2EventEngine::L2EventEngine(std::uint32_t simulated_sm_count,
                             std::uint64_t seed)
    : sm_count_(simulated_sm_count > 0 ? simulated_sm_count : 1),
      seed_(seed),
      rng_(seed != 0 ? seed : 0x5eedULL) {}

void L2EventEngine::reset() {
    std::lock_guard<std::mutex> lk(mutex_);
    rng_.seed(seed_ != 0 ? seed_ : 0x5eedULL);
    request_id_ = 0;
    completion_id_ = 0;
    event_id_ = 0;
    pending_.clear();
    sm_issue_.clear();
    events_.clear();
}

std::vector<L2Request> L2EventEngine::issue_global(
    std::uint32_t sm, std::uint32_t subcore, std::uint32_t cta,
    std::uint32_t warp, std::uint64_t pc, std::uint64_t instruction,
    std::uint64_t parent_event_id, const std::string& mnemonic,
    const std::string& request_kind, std::uint64_t addr, std::uint64_t len) {
    std::lock_guard<std::mutex> lk(mutex_);
    std::vector<L2Request> out;
    // Distinct 128-B sectors covered by [addr, addr+len).  Bounded by `len`
    // (Medium: never iterates past a wrapped addr+len).
    std::vector<std::uint64_t> sectors;
    for (std::uint64_t n = 0; n < len; ++n) {
        const std::uint64_t a = addr + n;
        const std::uint64_t sec = a >> 7;
        if (std::find(sectors.begin(), sectors.end(), sec) == sectors.end()) {
            sectors.push_back(sec);
        }
    }
    const std::uint64_t issue = sm_issue_[sm]++;
    (void)issue;
    for (std::uint64_t sec : sectors) {
        L2Request r;
        r.request_id = ++request_id_;
        r.parent_event_id = parent_event_id;
        r.instruction = instruction;
        r.sm = sm;
        r.subcore = subcore;
        r.cta = cta;
        r.warp = warp;
        r.pc = pc;
        r.mnemonic = mnemonic;
        r.request_kind = request_kind;
        r.sector = sec;
        r.addr = addr;
        r.len = len;
        pending_[sec].push_back(r);

        // Record as a MemoryEvent (L2Request).
        MemoryEvent ev;
        ev.kind = MemoryEventKind::kL2Request;
        ev.event_id = ++event_id_;
        ev.request_id = r.request_id;
        ev.parent_event_id = parent_event_id;
        ev.instruction = instruction;
        ev.sm = sm;
        ev.subcore = subcore;
        ev.cta = cta;
        ev.warp = warp;
        ev.pc = pc;
        ev.mnemonic = mnemonic;
        ev.request_kind = request_kind;
        ev.sector = sec;
        ev.sectors = sectors;
        events_.push_back(ev);
        out.push_back(r);
    }
    return out;
}

std::vector<L2Completion> L2EventEngine::drain_completions() {
    std::lock_guard<std::mutex> lk(mutex_);
    // Deterministic serialized order: iterate sectors ascending, and within a
    // sector the requests in insertion (per-SM) order.  This is the stable
    // tie-break (sector, then SM issue order).  When a seed is set, we apply
    // a stable permutation derived from the RNG so replay is reproducible but
    // not trivially sorted.
    std::vector<L2Request> all;
    for (auto& [sec, reqs] : pending_) {
        (void)sec;
        for (auto& r : reqs) all.push_back(r);
    }
    if (seed_ != 0) {
        // Stable Fisher-Yates over the sector-ordered request list using the
        // seeded RNG: same seed -> same completion order.
        for (std::size_t i = all.size(); i > 1; --i) {
            std::uniform_int_distribution<std::size_t> d(0, i - 1);
            std::swap(all[i - 1], all[d(rng_)]);
        }
    } else {
        // Deterministic default: sort by (sector, sm, per-sm issue order).
        std::stable_sort(all.begin(), all.end(),
                         [](const L2Request& a, const L2Request& b) {
                             if (a.sector != b.sector) return a.sector < b.sector;
                             if (a.sm != b.sm) return a.sm < b.sm;
                             return a.request_id < b.request_id;
                         });
    }
    std::vector<L2Completion> out;
    for (const auto& r : all) {
        L2Completion c;
        c.completion_id = ++completion_id_;
        c.request_id = r.request_id;
        c.parent_event_id = r.parent_event_id;
        c.sm = r.sm;
        c.subcore = r.subcore;
        c.sector = r.sector;
        c.completion_seq = out.size() + 1;
        c.tie_reason = "sector" + std::to_string(r.sector) + ":sm" +
                       std::to_string(r.sm) + ":seq" +
                       std::to_string(r.request_id);
        out.push_back(c);

        MemoryEvent ev;
        ev.kind = MemoryEventKind::kL2Completion;
        ev.event_id = ++event_id_;
        ev.request_id = r.request_id;
        ev.parent_event_id = r.parent_event_id;
        ev.instruction = r.instruction;
        ev.sm = r.sm;
        ev.subcore = r.subcore;
        ev.cta = r.cta;
        ev.warp = r.warp;
        ev.pc = r.pc;
        ev.mnemonic = r.mnemonic;
        ev.request_kind = r.request_kind;
        ev.sector = r.sector;
        ev.issue_tick = c.completion_seq;
        ev.tie_reason = c.tie_reason;
        events_.push_back(ev);
    }
    pending_.clear();
    return out;
}

std::string l2_events_to_json(const std::vector<MemoryEvent>& events) {
    std::ostringstream o;
    o << "[";
    for (std::size_t i = 0; i < events.size(); ++i) {
        const auto& e = events[i];
        if (i) o << ",";
        o << "{\"id\":" << e.event_id
          << ",\"kind\":"
          << static_cast<int>(e.kind)
          << ",\"parent\":" << e.parent_event_id
          << ",\"sm\":" << e.sm
          << ",\"subcore\":" << e.subcore
          << ",\"sector\":" << e.sector
          << ",\"kind_name\":\"" << e.request_kind
          << "\",\"mnemonic\":\"" << e.mnemonic
          << "\",\"seq\":" << e.issue_tick
          << ",\"tie\":\"" << e.tie_reason << "\"}";
    }
    o << "]";
    return o.str();
}

}  // namespace semu
