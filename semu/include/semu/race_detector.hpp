#pragma once

// FROZEN (SIM_PLAN Phase 10): the race-detector report schema (RaceReport /
// RaceAccess / reports_to_json) is stable — a deterministic execution's
// report is byte-for-byte reproducible.  It consumes the event stream
// (kEventStreamVersion, api.hpp) but never feeds back into execution.

// Data-race detector (SIM_PLAN Phase 6 Step 2D).
//
// Happens-before based: two overlapping byte ranges with at least one write
// race unless happens-before is provable.  Shadow state:
//   - shared: keyed by CTA allocation (cta-scoped; reclaimed when the CTA
//     ends)
//   - global: keyed by (allocation id, generation, byte range), shared across
//     SMs; generation prevents address-reuse confusion after free/reallocate
//
// HB edges come only from the ISA synchronization semantics (lane program
// order, warp program order, CTA/named barrier, fences combined with a
// matching communication, atomics with matching order+scope, kernel
// launch/completion).  Control-flow convergence, host worker affinity, and
// accidental scheduling never establish HB.
//
// The core is a FastTrack-style interval shadow:
//   - every writer/reader records the actor's vector-clock SNAPSHOT taken at
//     the access (never a mutable clock that later sync would retroactively
//     change the ordering of)
//   - a directed happens-before test `prior -> current` is
//       same actor   : prior.instruction < current.instruction (lane program order)
//       same warp    : prior.instruction < current.instruction (warp program order;
//                      a single dynamic instruction's lanes are concurrent)
//       otherwise    : current_clock.dominates(prior_clock)  (vector clock)
//   - WAW (new write vs interval writer), RAW (new read vs interval writer)
//     and WAR (new write vs every recorded reader) are each checked; a bare
//     write-vs-last_write comparison misses WAR.
//   - atomics with a matching order+scope publish/merge a per-location
//     release clock (release store publishes; acquire/strong load merges).
//   - unsupported memory-order/scope combinations are marked
//     `race-analysis-unsupported`, not silently race-free.
//
// Reports carry both sides (PC/instruction/kind/actor/overlap/atomic/order/
// scope), the observed sync chain and why no HB.  Duplicate reports are
// deduplicated with a stable, actor-order-canonical key + occurrence count.
//
// The shadow memory is thread-safe (mutex) — it is the race detector's own
// protection, not a substitute for ThreadSanitizer (TSan checks the host
// implementation, not the simulated device program).

#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <vector>

#include <semu/hb_clock.hpp>
#include <semu/memory.hpp>

namespace semu {
constexpr int kRaceLanesPerWarp = 32;

// One observed access (a dynamic warp memory instruction covering a byte
// range).
struct RaceAccess {
    std::uint64_t instruction = 0;   // dynamic instruction id
    std::uint64_t pc = 0;
    std::string mnemonic;
    AddressSpace space = AddressSpace::kGlobal;
    // Domain identity: global -> allocation id + generation; shared -> cta id.
    AllocationId alloc_id;
    std::uint64_t generation = 0;
    std::uint32_t cta = 0;
    std::uint32_t sm = 0;
    std::uint32_t warp = 0;
    std::uint32_t lane = 0;          // 0..31; 0xffffffff = warp-uniform
    std::uint64_t byte_begin = 0;    // interior offset within the allocation
    std::uint64_t byte_end = 0;      // exclusive
    bool is_write = false;
    bool is_atomic = false;
    std::string atomic_op;           // e.g. "add", "exch" ("" when not atomic)
    std::string mem_order;           // "relaxed", "acquire", "release",
                                     // "acq_rel", "sc", "mmio", ...
    std::string scope;               // "nosco", "cta", "sm", "vc", "gpu", "sys"
    std::string order_scope_ok;      // "supported" / "race-analysis-unsupported"
    RaceActor actor() const {
        return RaceActor{0, sm, cta, warp, lane};
    }
};

// A race report (both sides + context).
struct RaceReport {
    RaceAccess first;
    RaceAccess second;
    std::uint64_t overlap_begin = 0;  // overlapping byte range
    std::uint64_t overlap_end = 0;    // exclusive
    std::string reason;               // why no happens-before
    std::string sync_chain;           // observed synchronization (or "none")
    std::uint64_t occurrence = 1;     // dedup count
    std::string key;                  // stable dedup key (canonical actor order)
};

// One shadow interval: a byte range that was written (writer + its clock
// snapshot) plus every reader (access + clock snapshot).  The clock
// snapshots are what the directed happens-before tests compare — never the
// detector's live mutable clock.
struct ShadowInterval {
    std::uint64_t begin = 0;
    std::uint64_t end = 0;
    bool has_write = false;
    RaceAccess last_write;                    // most recent writer covering the
                                              // whole interval
    HbClock writer_clock;                     // writer's clock snapshot
    // readers: actor -> (access, clock snapshot at the read).
    std::map<RaceActor, std::pair<RaceAccess, HbClock>> readers;
};

class RaceDetector {
public:
    // Observe one access.  Returns newly-detected races (already merged into
    // the report set).  Thread-safe.
    std::vector<RaceReport> observe(const RaceAccess& access);

    // Enable/disable (off = no shadow allocation, no reports).
    void set_enabled(bool e) { enabled_ = e; }
    bool enabled() const { return enabled_; }

    // CTA barrier / named barrier: merge clocks of participating warps in a
    // CTA (establishes HB across those warps for subsequent accesses).
    // `sm` must match the sm the CTA's accesses carry (actor identity).
    void cta_barrier(std::uint32_t cta, std::uint32_t sm,
                     const std::vector<std::uint32_t>& warps);
    void named_barrier(std::uint32_t cta, std::uint32_t sm,
                       const std::vector<std::uint32_t>& warps);

    // Fence: no standalone HB edge (per spec: only combined with matching
    // communication).  Recorded for diagnostics and combined with a
    // subsequent release store / acquire load on the same actor.
    void fence(std::uint32_t cta, std::uint32_t sm, std::uint32_t warp,
               const std::string& scope);

    // Atomic with order+scope: a release store publishes the actor's clock
    // to the location's release clock; an acquire / strong load merges it.
    // Unsupported order/scope combos are flagged.  Also observes the access
    // itself (an atomic RMW is a read+write; compatible same-address atomics
    // do not race each other).
    void atomic_rmw(const RaceAccess& access);

    // Kernel launch boundary: reset to a fresh launch epoch.
    void launch();

    // Reclaim all shadow for a finished CTA (shared domain).
    void reclaim_cta(std::uint32_t cta);

    // Reclaim an allocation (global) — bumps its generation and drops stale
    // shadow so a reused VA never aliases a previous allocation's history.
    void reclaim_allocation(AllocationId id);

    // All reports (deduped, stable order).  Thread-safe snapshot.
    std::vector<RaceReport> reports() const;

    // Serialize reports as stable JSON (byte-for-byte deterministic for the
    // same execution).
    std::string reports_to_json() const;

private:
    // A per-location release-clock domain: (space, cta|alloc, gen, byte
    // range).  Scope is NOT part of the key — multiple actors may release to
    // the same location under different scopes, and an acquire filters the
    // location's records by scope compatibility (High-1) instead of failing
    // to find them because the scope strings differ.
    struct ReleaseKey {
        AddressSpace space = AddressSpace::kGlobal;
        std::uint64_t domain = 0;  // cta (shared) or alloc id (global)
        std::uint64_t gen = 0;     // allocation generation (global)
        std::uint64_t begin = 0;
        std::uint64_t end = 0;
        bool operator<(const ReleaseKey& o) const {
            if (space != o.space) return static_cast<int>(space) < static_cast<int>(o.space);
            if (domain != o.domain) return domain < o.domain;
            if (gen != o.gen) return gen < o.gen;
            if (begin != o.begin) return begin < o.begin;
            return end < o.end;
        }
    };

    // One release to a location: the releasing actor's clock snapshot at the
    // release plus the releasing actor's location and scope, which the
    // acquire-side scope-compatibility test needs to know whether the release
    // is visible to it.
    struct ReleaseRecord {
        RaceActor actor{};
        std::string scope;   // releasing access's scope
        HbClock clock;
    };

    mutable std::mutex mutex_;
    bool enabled_ = false;
    // Global shadow: (alloc_id, generation) -> (byte_begin -> intervals).
    using GlobalKey = std::pair<std::uint64_t, std::uint64_t>;
    std::map<GlobalKey,
             std::map<std::uint64_t, ShadowInterval>> global_shadow_;
    // Shared shadow: cta -> (byte_begin -> intervals).
    std::map<std::uint32_t,
             std::map<std::uint64_t, ShadowInterval>> shared_shadow_;
    // Per-actor live clocks.
    std::map<RaceActor, HbClock> clocks_;
    // Per-location release clocks (atomic release/acquire).  A location may
    // hold releases from several actors/scopes; an acquire merges the ones
    // whose scope is visible to it.
    std::map<ReleaseKey, std::vector<ReleaseRecord>> release_clocks_;
    // Global allocation generations (alloc_id -> current generation).
    std::map<std::uint64_t, std::uint64_t> generations_;
    // Reports keyed by stable dedup key.
    std::map<std::string, RaceReport> reports_;

    HbClock& actor_clock(RaceActor a) { return clocks_[a]; }
    std::uint64_t current_generation(AllocationId id) const {
        auto it = generations_.find(id.id);
        return it == generations_.end() ? 0 : it->second;
    }
    // Directed happens-before test: does `prior` (with its clock snapshot)
    // happen-before `current` (with its clock snapshot)?
    bool happens_before(const RaceAccess& prior, const HbClock& prior_clock,
                        const RaceAccess& current,
                        const HbClock& current_clock,
                        std::string* why) const;
    // Check one overlapping interval against a new access (RAW/WAW/WAR).
    void check_interval(const RaceAccess& access, const HbClock& clock,
                        const ShadowInterval& iv, std::uint64_t ob,
                        std::uint64_t oe,
                        std::vector<RaceReport>* out);
    void report(const RaceAccess& first, const RaceAccess& second,
                std::uint64_t ob, std::uint64_t oe, const std::string& why,
                std::vector<RaceReport>* out);
    ReleaseKey key_of(const RaceAccess& a) const;
    std::string dedup_key(const RaceAccess& a, const RaceAccess& b,
                          std::uint64_t ob, std::uint64_t oe) const;
    // True when an access with `scope` performed by `op` is visible to
    // `other` (PTX §8.5: a scope is the set of threads the operation may
    // interact with).  "nosco" is treated as CTA-local, "vc" as device-local.
    bool scope_visible(const RaceAccess& op, const RaceActor& other) const;
};

// Parse a SASS memory-order/scope string into (order, scope).  Returns
// "race-analysis-unsupported" for combinations the HB model does not yet
// implement.
std::string classify_order_scope(const std::string& sem,
                                 const std::string& sco);

}  // namespace semu
