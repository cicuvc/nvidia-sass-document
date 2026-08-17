// Happens-before vector clock (Phase 6 Step 2D).

#include <semu/hb_clock.hpp>

#include <sstream>

namespace semu {

void HbClock::tick(RaceActor actor) {
    clock_[actor] = epoch(actor) + 1;
}

void HbClock::merge(const HbClock& other) {
    for (const auto& [a, e] : other.clock_) {
        if (e > epoch(a)) clock_[a] = e;
    }
}

void HbClock::acquire(RaceActor actor, const HbClock& other) {
    tick(actor);
    merge(other);
}

std::uint64_t HbClock::epoch(RaceActor actor) const {
    auto it = clock_.find(actor);
    return it == clock_.end() ? 0 : it->second;
}

bool HbClock::dominates(const HbClock& other) const {
    for (const auto& [a, e] : other.clock_) {
        if (epoch(a) < e) return false;
    }
    return true;
}

std::string HbClock::to_string() const {
    std::ostringstream o;
    o << "{";
    bool first = true;
    for (const auto& [a, e] : clock_) {
        if (!first) o << ",";
        first = false;
        o << "(" << a.launch << "," << a.sm << "," << a.cta << "," << a.warp
          << "," << a.lane << "):" << e;
    }
    o << "}";
    return o.str();
}

}  // namespace semu
