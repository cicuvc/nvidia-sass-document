#pragma once

// Happens-before vector clock (SIM_PLAN Phase 6 Step 2D).
//
// A sparse vector clock tracks the happens-before partial order between
// actors.  An actor is identified by (space, cta, warp, lane) — for shared
// accesses the CTA-scope is the domain; for global accesses the whole launch
// (cta + sm) is the domain.  HB edges come ONLY from the ISA synchronization
// semantics:
//   - lane program order (a lane's accesses are ordered)
//   - CTA barrier (release + acquire merge)
//   - named barrier / mbarrier
//   - fences (combined with a matching communication op)
//   - atomics with matching memory order + scope
//   - kernel launch / completion boundaries
//
// Control-flow convergence, sharing a host worker, or accidental scheduling
// order never establish HB.

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace semu {

// A logical actor (the finest unit of ordering the race detector tracks).
struct RaceActor {
    std::uint32_t launch = 0;
    std::uint32_t sm = 0;
    std::uint32_t cta = 0;
    std::uint32_t warp = 0;
    std::uint32_t lane = 0;  // 0..31; 0xffffffff = "warp-wide" (uniform)
    bool operator<(const RaceActor& o) const {
        if (launch != o.launch) return launch < o.launch;
        if (sm != o.sm) return sm < o.sm;
        if (cta != o.cta) return cta < o.cta;
        if (warp != o.warp) return warp < o.warp;
        return lane < o.lane;
    }
    bool operator==(const RaceActor& o) const = default;
};

// Sparse vector clock: maps actor id -> epoch.  An empty map is "bottom".
class HbClock {
public:
    // Bump this actor's own epoch (program order advance).
    void tick(RaceActor actor);
    // Merge another clock into this one (release/acquire on a barrier).
    void merge(const HbClock& other);
    // This actor observes a release from `other` (acquire side of a
    // communication); merge.
    void acquire(RaceActor actor, const HbClock& other);
    // True when `actor`'s epoch here is >= the epoch recorded in `other` for
    // the same actor — used to test whether this clock "knows about" other.
    bool dominates(const HbClock& other) const;
    // Accessor.
    std::uint64_t epoch(RaceActor actor) const;
    // Serialize (for diagnostics / JSON reports).
    std::string to_string() const;

private:
    std::map<RaceActor, std::uint64_t> clock_;
};

}  // namespace semu
