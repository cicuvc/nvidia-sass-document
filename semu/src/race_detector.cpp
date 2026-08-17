// Data-race detector (Phase 6 Step 2D).
//
// FastTrack-style interval shadow: every writer/reader records a vector-clock
// SNAPSHOT at the access; happens-before is a directed test on those
// snapshots, never on a mutable live clock.  WAW (write/write), RAW
// (read-after-write) and WAR (write-after-read) are each checked by comparing
// the new access against the interval's writer and every reader.

#include <semu/race_detector.hpp>

#include <algorithm>
#include <sstream>

namespace semu {

namespace {

// Stable serialization of an actor + access for dedup keys and JSON.
std::string actor_str(const RaceAccess& a) {
    return "l" + std::to_string(a.actor().launch) + ":sm" +
           std::to_string(a.actor().sm) + ":c" + std::to_string(a.actor().cta) +
           ":w" + std::to_string(a.actor().warp) + ":L" +
           std::to_string(a.actor().lane);
}

bool is_release_order(const std::string& o) {
    return o == "release" || o == "acq_rel" || o == "sc" || o == "strong";
}
bool is_acquire_order(const std::string& o) {
    return o == "acquire" || o == "acq_rel" || o == "sc" || o == "strong";
}

}  // namespace

std::string classify_order_scope(const std::string& sem,
                                 const std::string& sco) {
    // Supported: relaxed/weak with any scope; acquire/release/acq_rel/sc/
    // strong with any device scope the model recognizes (cta/sm/vc/gpu/sys
    // or the default nosco).  MMIO ordering and unknown orders/scopes ->
    // unsupported.  The scope is meaningful: the release/acquire clock merge
    // is scoped per (location, scope) domain, and an unrecognized scope is
    // not something the HB model can honor.
    const std::string o = sem.empty() ? "relaxed" : sem;
    const std::string s = sco;
    if (o == "WEAK" || o == "weak" || o == "relaxed") return "supported";
    if (o == "MMIO" || o == "mmio") return "race-analysis-unsupported";
    if (o == "STRONG" || o == "strong" || o == "acq_rel" || o == "acquire" ||
        o == "release" || o == "sc") {
        const bool known_scope =
            s.empty() || s == "nosco" || s == "cta" || s == "sm" ||
            s == "vc" || s == "gpu" || s == "sys";
        return known_scope ? "supported" : "race-analysis-unsupported";
    }
    return "race-analysis-unsupported";
}

// Directed happens-before test between two accesses with their clock
// snapshots.  `prior -> current` iff:
//   - same lane: program order (instruction ids strictly increase)
//   - same warp: program order across dynamic instructions; lanes of ONE
//     dynamic instruction (same id) are concurrent participants
//   - otherwise: current's snapshot dominates prior's (vector clock)
bool RaceDetector::happens_before(const RaceAccess& prior,
                                  const HbClock& prior_clock,
                                  const RaceAccess& current,
                                  const HbClock& current_clock,
                                  std::string* why) const {
    const RaceActor pa = prior.actor();
    const RaceActor ca = current.actor();
    if (pa == ca) {
        if (prior.instruction < current.instruction) {
            if (why) *why = "same-lane program order";
            return true;
        }
        if (why) *why = "later instruction of same lane";
        return false;
    }
    if (pa.sm == ca.sm && pa.cta == ca.cta && pa.warp == ca.warp) {
        if (prior.instruction < current.instruction) {
            if (why) *why = "same-warp program order";
            return true;
        }
        // Equal instruction ids: the two lanes are concurrent participants of
        // one dynamic warp instruction.
        if (why) *why = "concurrent lanes of one warp instruction";
        return false;
    }
    if (current_clock.dominates(prior_clock)) {
        if (why) *why = "vector clock: prior visible to current via sync chain";
        return true;
    }
    if (why) *why = "no happens-before edge (no barrier/atomic/fence sync)";
    return false;
}

RaceDetector::ReleaseKey RaceDetector::key_of(const RaceAccess& a) const {
    ReleaseKey k;
    k.space = a.space;
    k.domain = a.space == AddressSpace::kShared ? a.cta : a.alloc_id.id;
    // Global releases are keyed by the CURRENT generation (queried) so a
    // reused VA never aliases a prior allocation's release clock.
    k.gen = a.space == AddressSpace::kGlobal ? current_generation(a.alloc_id)
                                             : a.generation;
    k.begin = a.byte_begin;
    k.end = a.byte_end;
    return k;
}

std::string RaceDetector::dedup_key(const RaceAccess& a, const RaceAccess& b,
                                    std::uint64_t ob,
                                    std::uint64_t oe) const {
    // Canonical actor order: a reversed observation of the same pair must
    // produce the same key (Medium fix) so it dedups into one report.
    const std::string sa = actor_str(a);
    const std::string sb = actor_str(b);
    const std::string first = sa < sb ? sa : sb;
    const std::string second = sa < sb ? sb : sa;
    return first + "<->" + second + ":" + std::to_string(ob) + "-" +
           std::to_string(oe) + ":" +
           std::string(a.space == AddressSpace::kShared ? "shared" : "global");
}

void RaceDetector::report(const RaceAccess& first, const RaceAccess& second,
                          std::uint64_t ob, std::uint64_t oe,
                          const std::string& why,
                          std::vector<RaceReport>* out) {
    RaceReport r;
    r.first = first;
    r.second = second;
    r.overlap_begin = ob;
    r.overlap_end = oe;
    r.reason = why.empty() ? "no happens-before" : why;
    r.sync_chain = "none";
    r.key = dedup_key(first, second, ob, oe);
    auto it = reports_.find(r.key);
    if (it != reports_.end()) {
        it->second.occurrence++;
    } else {
        r.occurrence = 1;
        reports_[r.key] = r;
        out->push_back(r);
    }
}

void RaceDetector::check_interval(const RaceAccess& access,
                                  const HbClock& clock,
                                  const ShadowInterval& iv, std::uint64_t ob,
                                  std::uint64_t oe,
                                  std::vector<RaceReport>* out) {
    // Compatible atomics: a new atomic over the SAME byte range whose recorded
    // writer is also atomic is exempt from the RAW/WAW check (both are
    // linearized RMWs and do not race).  The exemption is scoped STRICTLY to
    // the atomic↔atomic WRITER pair over the same byte range — it must NOT
    // cover a plain (non-atomic) read, and must NOT skip the WAR check against
    // the interval's non-atomic readers, nor short-circuit the whole interval.
    //
    // An atomic write does NOT magically make an unsynchronized plain access
    // legal: atomic A write X -> actor B unsynchronized plain read X must
    // still be reported as an A/B RAW (the plain read is not ordered after the
    // RMW absent a happens-before edge), and that plain read between two
    // atomics must surface a B/C WAR on a later atomic write C.  Only when BOTH
    // the recorded writer and the new access are atomic over the same range is
    // a race-free linearization guaranteed.  When a real release/acquire
    // happens-before exists, the directed vector clock eliminates the report —
    // it is never the type-based exemption's job to excuse a missing HB edge.
    const bool writer_exempt =
        iv.has_write && iv.last_write.is_atomic && access.is_atomic &&
        access.byte_begin == iv.last_write.byte_begin &&
        access.byte_end == iv.last_write.byte_end;

    // RAW / WAW: the interval's writer must happen-before the new access.
    // The HB edge is DIRECTED prior -> current.  A reverse edge (current ->
    // prior) is never accepted: the recorded writer/reader was observed first
    // (replay is sorted by (cta, ordinal)), so a reverse test would hide real
    // races whenever the dynamic instruction ids are not monotonic in replay
    // order (cross-CTA merge, out-of-order detector input, wrong input).
    if (iv.has_write && !writer_exempt) {
        std::string why;
        if (!happens_before(iv.last_write, iv.writer_clock, access, clock,
                            &why)) {
            report(iv.last_write, access, ob, oe, why, out);
        }
    }

    // WAR: a new write vs every recorded reader (directed reader -> write).
    if (access.is_write) {
        for (const auto& [ractor, rr] : iv.readers) {
            (void)ractor;
            const RaceAccess& racc = rr.first;
            const HbClock& rclock = rr.second;
            std::string why;
            if (!happens_before(racc, rclock, access, clock, &why)) {
                report(racc, access, ob, oe, why, out);
            }
        }
    }
}

void RaceDetector::launch() {
    std::lock_guard<std::mutex> lk(mutex_);
    clocks_.clear();
    release_clocks_.clear();
    global_shadow_.clear();
    shared_shadow_.clear();
}

void RaceDetector::reclaim_cta(std::uint32_t cta) {
    std::lock_guard<std::mutex> lk(mutex_);
    shared_shadow_.erase(cta);
    // Drop clocks and release clocks for this CTA's actors.
    for (auto it = clocks_.begin(); it != clocks_.end();) {
        if (it->first.cta == cta) it = clocks_.erase(it);
        else ++it;
    }
    for (auto it = release_clocks_.begin(); it != release_clocks_.end();) {
        if (it->first.space == AddressSpace::kShared && it->first.domain == cta) {
            it = release_clocks_.erase(it);
        } else {
            ++it;
        }
    }
}

void RaceDetector::reclaim_allocation(AllocationId id) {
    std::lock_guard<std::mutex> lk(mutex_);
    generations_[id.id]++;  // bump generation; old shadow is stale
    // Drop every global shadow interval for this allocation (any generation)
    // so a reused VA never aliases the previous allocation's history.
    for (auto it = global_shadow_.begin(); it != global_shadow_.end();) {
        if (it->first.first == id.id) it = global_shadow_.erase(it);
        else ++it;
    }
    for (auto it = release_clocks_.begin(); it != release_clocks_.end();) {
        if (it->first.space == AddressSpace::kGlobal &&
            it->first.domain == id.id) {
            it = release_clocks_.erase(it);
        } else {
            ++it;
        }
    }
}

void RaceDetector::cta_barrier(std::uint32_t cta, std::uint32_t sm,
                               const std::vector<std::uint32_t>& warps) {
    std::lock_guard<std::mutex> lk(mutex_);
    // Merge clocks of all participating warps' lanes (actor sm = the CTA's
    // SM, matching the accesses the interpreter records).
    HbClock merged;
    for (std::uint32_t w : warps) {
        for (std::uint32_t lane = 0; lane < kRaceLanesPerWarp; ++lane) {
            RaceActor a{0, sm, cta, w, lane};
            auto it = clocks_.find(a);
            if (it != clocks_.end()) merged.merge(it->second);
        }
    }
    // Acquire the merged clock into every participating warp.
    for (std::uint32_t w : warps) {
        for (std::uint32_t lane = 0; lane < kRaceLanesPerWarp; ++lane) {
            RaceActor a{0, sm, cta, w, lane};
            clocks_[a].merge(merged);
        }
    }
}

void RaceDetector::named_barrier(std::uint32_t cta, std::uint32_t sm,
                                 const std::vector<std::uint32_t>& warps) {
    cta_barrier(cta, sm, warps);
}

void RaceDetector::fence(std::uint32_t cta, std::uint32_t sm,
                         std::uint32_t warp, const std::string& scope) {
    // Fences alone establish no HB edge (only combined with communication).
    // Record a marker so the actor's subsequent release/acquire atomics can
    // attribute ordering through it; the atomics themselves carry the clock
    // merge.  The scope is kept for diagnostics on the sync chain.
    (void)scope;
    std::lock_guard<std::mutex> lk(mutex_);
    // A fence orders this actor's own subsequent accesses after its prior
    // ones (already guaranteed by program order); nothing cross-actor.
    for (std::uint32_t lane = 0; lane < kRaceLanesPerWarp; ++lane) {
        RaceActor a{0, sm, cta, warp, lane};
        clocks_[a];  // materialize so a later barrier/atomic merge has it
    }
}

void RaceDetector::atomic_rmw(const RaceAccess& access) {
    // Observe the access itself (an atomic is a read+write; compatible
    // same-address atomics are exempted inside check_interval).
    observe(access);

    // Unsupported order/scope: the access is still recorded/flagged but the
    // model must NOT silently build release/acquire edges on it.
    if (access.order_scope_ok != "supported") return;

    std::lock_guard<std::mutex> lk(mutex_);
    const RaceActor a = access.actor();
    const HbClock& clock = clocks_[a];
    const ReleaseKey key = key_of(access);
    if (is_release_order(access.mem_order)) {
        // Publish this actor's clock (everything before the atomic in program
        // order) to the location's release clock.  Records the releasing
        // actor's location + scope so the acquire side can apply scope
        // visibility.
        ReleaseRecord rec;
        rec.actor = a;
        rec.scope = access.scope;
        rec.clock = clock;
        release_clocks_[key].push_back(std::move(rec));
    }
    if (is_acquire_order(access.mem_order)) {
        // Merge every release at this location whose scope is visible to the
        // acquiring actor AND whose releasing actor lies within the acquire's
        // own scope (PTX §8.7 morally-strong: both operations specify a scope
        // that includes the thread executing the other).  A release scope
        // that is too small for the acquirer (e.g. release.cta seen from a
        // different CTA) or an acquire scope too small for the releaser must
        // NOT establish HB (High-1).
        auto it = release_clocks_.find(key);
        if (it != release_clocks_.end()) {
            for (const auto& rec : it->second) {
                RaceAccess rel = access;
                rel.sm = rec.actor.sm;
                rel.cta = rec.actor.cta;
                rel.scope = rec.scope;
                if (scope_visible(rel, a) && scope_visible(access, rec.actor)) {
                    clocks_[a].merge(rec.clock);
                }
            }
        }
    }
}

// Scope visibility (High-1): a scope is the set of threads an operation may
// interact with (PTX §8.5).  Two operations synchronize only when EACH
// operation's scope includes the thread executing the other (§8.7 morally
// strong): a release.cta cannot be observed from a different CTA and a
// release.gpu cannot be observed by a cta-scoped acquire in a different CTA.
bool RaceDetector::scope_visible(const RaceAccess& op,
                                 const RaceActor& other) const {
    const std::string& s = op.scope;
    if (s == "sys") return true;
    if (s == "gpu" || s == "vc") return true;  // whole launch / device
    if (s == "sm") return op.sm == other.sm;
    if (s == "cta" || s == "nosco") return op.cta == other.cta;
    return false;  // unknown scope: claims no visibility
}

std::vector<RaceReport> RaceDetector::observe(const RaceAccess& access) {
    std::lock_guard<std::mutex> lk(mutex_);
    std::vector<RaceReport> out;
    RaceActor a = access.actor();

    // Resolve the current generation for a global allocation (query, so an
    // address reused after reclaim gets a fresh shadow domain).
    RaceAccess acc = access;
    if (acc.space == AddressSpace::kGlobal) {
        acc.generation = current_generation(acc.alloc_id);
    }

    // Snapshot the actor's clock, then advance it with this access.
    HbClock clock = clocks_[a];
    clock.tick(a);
    clocks_[a] = clock;

    auto& shadow = acc.space == AddressSpace::kShared
                       ? shared_shadow_[acc.cta]
                       : global_shadow_[{acc.alloc_id.id, acc.generation}];

    // True interval split around [begin, end) (Blocker-1).  The access's
    // covered range is cut at the boundaries of every overlapping interval;
    // the leftover head/tail fragments keep the ORIGINAL writer/readers.  A
    // READ must preserve the overlapped writer and every existing reader and
    // only add the current reader (a read must never drop a writer — that
    // would hide a later WAW).  A WRITE replaces the covered sub-interval's
    // writer and clears its readers — but only AFTER the RAW/WAW/WAR checks
    // have seen the old state.  Region covered by no existing interval gets a
    // fresh interval (write -> new writer; read -> just the current reader).
    std::vector<std::pair<std::uint64_t, ShadowInterval>> replacement;
    std::uint64_t pos = acc.byte_begin;
    for (auto it = shadow.begin(); it != shadow.end();) {
        ShadowInterval& iv = it->second;
        if (iv.end <= acc.byte_begin) {
            ++it;
            continue;
        }
        if (acc.byte_end <= iv.begin) break;  // sorted; no more overlaps
        const std::uint64_t ob = std::max(acc.byte_begin, iv.begin);
        const std::uint64_t oe = std::min(acc.byte_end, iv.end);
        check_interval(acc, clock, iv, ob, oe, &out);
        // Head fragment [iv.begin, ob): original contents.
        if (iv.begin < ob) {
            ShadowInterval head = iv;
            head.end = ob;
            replacement.emplace_back(iv.begin, std::move(head));
        }
        // Gap region [pos, ob): not covered by any existing interval.
        if (pos < ob) {
            ShadowInterval gap;
            gap.begin = pos;
            gap.end = ob;
            if (acc.is_write) {
                gap.has_write = true;
                gap.last_write = acc;
                gap.writer_clock = clock;
            } else {
                gap.readers[a] = {acc, clock};
            }
            replacement.emplace_back(pos, std::move(gap));
        }
        // Covered region [ob, oe): write replaces writer/readers; read
        // preserves writer + readers and adds itself.
        ShadowInterval cov;
        cov.begin = ob;
        cov.end = oe;
        if (acc.is_write) {
            cov.has_write = true;
            cov.last_write = acc;
            cov.writer_clock = clock;
        } else {
            cov.has_write = iv.has_write;
            cov.last_write = iv.last_write;
            cov.writer_clock = iv.writer_clock;
            cov.readers = iv.readers;
            cov.readers[a] = {acc, clock};
        }
        replacement.emplace_back(ob, std::move(cov));
        pos = oe;
        // Tail fragment [oe, iv.end): original contents.
        if (oe < iv.end) {
            ShadowInterval tail = iv;
            tail.begin = oe;
            replacement.emplace_back(oe, std::move(tail));
        }
        it = shadow.erase(it);
    }
    // Trailing gap [pos, acc.byte_end): no existing interval covers it.
    if (pos < acc.byte_end) {
        ShadowInterval gap;
        gap.begin = pos;
        gap.end = acc.byte_end;
        if (acc.is_write) {
            gap.has_write = true;
            gap.last_write = acc;
            gap.writer_clock = clock;
        } else {
            gap.readers[a] = {acc, clock};
        }
        replacement.emplace_back(pos, std::move(gap));
    }
    for (auto& p : replacement) shadow[p.first] = std::move(p.second);
    return out;
}

std::vector<RaceReport> RaceDetector::reports() const {
    std::lock_guard<std::mutex> lk(mutex_);
    std::vector<RaceReport> out;
    out.reserve(reports_.size());
    for (const auto& [k, r] : reports_) out.push_back(r);
    return out;
}

std::string RaceDetector::reports_to_json() const {
    std::lock_guard<std::mutex> lk(mutex_);
    std::ostringstream o;
    o << "[";
    bool first = true;
    for (const auto& [k, r] : reports_) {
        if (!first) o << ",";
        first = false;
        o << "{\"key\":\"" << r.key << "\",\"count\":" << r.occurrence
          << ",\"overlap\":[" << r.overlap_begin << "," << r.overlap_end
          << "],\"reason\":\"" << r.reason << "\",\"sync\":\"" << r.sync_chain
          << "\",\"a\":{\"pc\":" << r.first.pc << ",\"insn\":\""
          << r.first.mnemonic << "\",\"kind\":\""
          << (r.first.is_write ? "write" : "read")
          << "\",\"actor\":\"" << actor_str(r.first) << "\",\"order\":\""
          << r.first.mem_order << "\",\"scope\":\"" << r.first.scope
          << "\",\"order_scope_ok\":\"" << r.first.order_scope_ok
          << "\",\"atomic\":" << (r.first.is_atomic ? "true" : "false")
          << "},\"b\":{\"pc\":" << r.second.pc << ",\"insn\":\""
          << r.second.mnemonic << "\",\"kind\":\""
          << (r.second.is_write ? "write" : "read")
          << "\",\"actor\":\"" << actor_str(r.second) << "\",\"order\":\""
          << r.second.mem_order << "\",\"scope\":\"" << r.second.scope
          << "\",\"order_scope_ok\":\"" << r.second.order_scope_ok
          << "\",\"atomic\":" << (r.second.is_atomic ? "true" : "false")
          << "}}";
    }
    o << "]";
    return o.str();
}

}  // namespace semu
