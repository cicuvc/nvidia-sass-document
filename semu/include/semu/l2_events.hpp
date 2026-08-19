#pragma once

// Event-based L2 layer (SIM_PLAN Phase 6 Step 2C).
//
// Independent component: cross-SM global accesses (L1 misses), writebacks and
// global atomics interact through L2 request/completion events.  This is
// TRACE-ONLY — it never changes functional memory values, scoreboard
// completion, atomic linearization, or happens-before edges.  Functional
// value is fully decoupled from event scheduling.
//
// Deterministic contract:
//   - each SM issues L2 requests in a stable per-SM order
//   - cross-SM serialization uses a stable tie-break (SM id, then per-SM
//     issue sequence)
//   - a fixed seed produces a byte-for-byte reproducible completion schedule
//     (seed replay) via a deterministic RNG; a different seed may reorder
//     completions but never changes the functional result.
//
// Sector addressing: a global byte address maps to a 128-byte sector index
// (addr >> 7).  Two SMs touching the same sector interact at L2; different
// sectors do not.  For each global access the engine records one L2Request
// per distinct sector touched, then an L2Completion per sector in the
// deterministic serialized order.

#include <cstdint>
#include <map>
#include <mutex>
#include <random>
#include <string>
#include <vector>

#include <semu/memory_events.hpp>

namespace semu {

// An L2 request (per sector of one global access).
struct L2Request {
    std::uint64_t request_id = 0;
    std::uint64_t parent_event_id = 0;  // L1TexIssue that missed L1
    std::uint64_t instruction = 0;
    std::uint32_t sm = 0;
    std::uint32_t subcore = 0;
    std::uint32_t cta = 0;
    std::uint32_t warp = 0;
    std::uint64_t pc = 0;
    std::string mnemonic;
    std::string request_kind;  // load / store / atomic / writeback
    std::uint64_t sector = 0;  // 128-B sector index
    std::uint64_t addr = 0;    // first byte of the access
    std::uint64_t len = 0;     // access byte length
};

// An L2 completion for one request (functional no-op).
struct L2Completion {
    std::uint64_t completion_id = 0;
    std::uint64_t request_id = 0;
    std::uint64_t parent_event_id = 0;
    std::uint32_t sm = 0;
    std::uint32_t subcore = 0;
    std::uint64_t sector = 0;
    std::uint64_t completion_seq = 0;  // stable global L2 order
    std::string tie_reason;            // e.g. "sm:subcore:seq"
};

// Deterministic, trace-only L2 event engine.
class L2EventEngine {
public:
    // `simulated_sm_count`: how many SMs share this L2.
    // `seed`: deterministic replay seed (0 = natural insertion order).
    L2EventEngine(std::uint32_t simulated_sm_count = 1,
                  std::uint64_t seed = 0);

    // Record a global access.  `request_kind` ∈ {load, store, atomic,
    // writeback}.  Splits into one request per distinct 128-B sector and
    // queues it for completion.  Trace-only.  Returns the issued requests.
    // Thread-safe (a launch-level engine is shared by parallel workers so
    // request/completion/event ids stay globally unique).
    std::vector<L2Request> issue_global(
        std::uint32_t sm, std::uint32_t subcore, std::uint32_t cta,
        std::uint32_t warp, std::uint64_t pc, std::uint64_t instruction,
        std::uint64_t parent_event_id, const std::string& mnemonic,
        const std::string& request_kind, std::uint64_t addr,
        std::uint64_t len);

    // Deterministic completion order (stable tie-break, seed-replayable).
    // Drains all queued completions.  Returns them in serialized order.
    // Thread-safe.
    std::vector<L2Completion> drain_completions();

    // Access to the raw event stream (L2Request/L2Completion as MemoryEvents)
    // for trace/reporting.  Populated by issue_global/drain_completions.
    const std::vector<MemoryEvent>& events() const { return events_; }
    std::vector<MemoryEvent>& events() { return events_; }

    // Reset for a fresh deterministic replay (same seed -> same schedule).
    void reset();

    std::uint64_t next_request_id() { return ++request_id_; }

private:
    mutable std::mutex mutex_;
    [[maybe_unused]] std::uint32_t sm_count_;  // reserved SM count (unused)
    std::uint64_t seed_;
    std::mt19937_64 rng_;
    std::uint64_t request_id_ = 0;
    std::uint64_t completion_id_ = 0;
    std::uint64_t event_id_ = 0;
    std::map<std::uint64_t, std::vector<L2Request>> pending_;  // sector -> requests
    std::map<std::uint32_t, std::uint64_t> sm_issue_;          // sm -> issue count
    std::vector<MemoryEvent> events_;
};

// Stable JSON rendering of the L2 event stream (byte-for-byte reproducible
// for a given seed).
std::string l2_events_to_json(const std::vector<MemoryEvent>& events);

}  // namespace semu
