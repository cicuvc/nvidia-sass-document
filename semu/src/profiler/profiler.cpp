// Memory profiler (SIM_PLAN Phase 8).  Subscribes to the backend-neutral
// memory event stream and produces the per-PC/variant/kernel/space report with
// the L1TEX hierarchy and L2 aggregate.  Pure read-only analysis: never
// changes memory values, scoreboard completion, atomic linearization or
// happens-before edges.

#include <semu/profiler/profiler.hpp>

#include <algorithm>
#include <array>
#include <cstdio>
#include <sstream>

namespace semu::profiler {

namespace {

// Unified JSON string escaping (codex review Medium-2): every string rendered
// into the report JSON goes through this helper so kernel/mnemonic/reason/
// applicability values with quotes, backslashes or control characters never
// corrupt the document.
std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof buf, "\\u%04x",
                                  static_cast<unsigned>(c));
                    out += buf;
                } else {
                    out += static_cast<char>(c);
                }
        }
    }
    return out;
}

// Stable aggregate key: space | mnemonic | variant | cache_policy | pc
// (deterministic map order).  The variant class is part of the key (codex
// review High-3) so distinct encoding variants never merge; cache_policy is
// included so an LDGSTS .BYPASS/.cg event (variant class ldgsts__RR32U, policy
// "cg") forms its own entry instead of overwriting the default-policy one —
// the confidence contract demands the two never blend.
std::string key_of(const std::string& space, const std::string& mnemonic,
                   const std::string& variant, const std::string& cache_policy,
                   std::uint64_t pc) {
    std::ostringstream o;
    o << space << "|" << mnemonic << "|" << variant << "|" << cache_policy
      << "@" << pc;
    return o.str();
}

const char* space_name(EventAddressSpace s) {
    switch (s) {
        case EventAddressSpace::kShared: return "shared";
        case EventAddressSpace::kConstant: return "constant";
        case EventAddressSpace::kLocal: return "local";
        default: return "global";
    }
}

}  // namespace

MemoryProfiler::MemoryProfiler(std::string kernel, std::uint32_t sm_count)
    : kernel_(std::move(kernel)), sm_count_(sm_count > 0 ? sm_count : 1) {}

void MemoryProfiler::add_event(const MemoryEvent& ev) { events_.push_back(ev); }

void MemoryProfiler::add_events(const std::vector<MemoryEvent>& evs) {
    for (const auto& ev : evs) events_.push_back(ev);
}

void MemoryProfiler::accumulate_shared(const MemoryEvent& ev,
                                       AggregateEntry& e) const {
    std::vector<shared_bank::LaneAccess> lanes;
    for (std::size_t l = 0; l < ev.lane_ranges.size(); ++l) {
        const auto& lr = ev.lane_ranges[l];
        shared_bank::LaneAccess la;
        la.lane = static_cast<std::uint32_t>(l);
        la.base = lr.base;
        la.len = lr.len;
        la.active = lr.active;
        lanes.push_back(la);
    }
    auto r = shared_bank::estimate(lanes, ev.element_width, ev.is_write);
    e.shared_passes += r.passes;
    e.shared_conflicts += r.conflict_count;
    e.shared_broadcasts += r.broadcast_count;
}

void MemoryProfiler::accumulate_global(const MemoryEvent& ev,
                                       AggregateEntry& e) const {
    shared_bank::LaneAccess lanes[32] = {};
    for (std::size_t l = 0; l < ev.lane_ranges.size() && l < 32; ++l) {
        const auto& lr = ev.lane_ranges[l];
        lanes[l].lane = static_cast<std::uint32_t>(l);
        lanes[l].base = lr.base;
        lanes[l].len = lr.len;
        lanes[l].active = lr.active;
    }
    auto r = global_model::estimate(lanes, ev.element_width);
    e.lane_requested_bytes += r.lane_requested_bytes;
    e.unique_useful_bytes += r.unique_useful_bytes;
    e.duplicate_reuse_bytes += r.duplicate_reuse_bytes;
    e.sector_fetch_bytes += r.sector_fetch_bytes;
    e.sector_overfetch_bytes += r.sector_overfetch_bytes;
    e.line_fill_bytes += r.line_fill_bytes;
    e.line_overfetch_bytes += r.line_overfetch_bytes;
    e.data_bank_passes += r.data_bank_passes;
    e.data_bank_conflicts += r.data_bank_conflicts;
    e.tag_bank_passes += r.tag_bank_passes;
}

void MemoryProfiler::accumulate_ldgsts(const MemoryEvent& ev,
                                       AggregateEntry& e) const {
    if (ev.ldgsts_goff.size() != 32 || ev.ldgsts_soff.size() != 32) return;
    // Round-2 H1: when the interpreter marks the prediction unavailable (an
    // address-computation overflow / invalid lane — see record_coupled_l1_to_
    // shared), the goff/soff of the failed lane are NOT valid offsets and must
    // never feed the estimator.  Every LDGSTS field is marked unsupported, no
    // fabricated counts are accumulated, and a dedicated counter is bumped.
    if (!ev.prediction) {
        e.prediction_unavailable_events++;
        e.confidence = "unsupported";                  // SharedWf
        e.ldgsts_count_confidence = "unsupported";     // TWf/TSetAcc/Sectors
        e.ldgsts_conflict_confidence = "unsupported";  // Shared/GlobalConf
        e.ldgsts_applicability =
            "prediction-unavailable (overflow / invalid lane): no estimate "
            "produced, all LDGSTS fields unsupported";
        e.ldgsts_model_version = semu::l1tex::kUnifiedModelVersion;
        e.cache_policy = ev.cache_policy.empty() ? "default" : ev.cache_policy;
        return;
    }
    semu::l1tex::UnifiedV1Estimator est;
    // Blocker-2: the cache policy travels on the event (derived by the
    // interpreter from the LDGSTS `loc` slot) and is forwarded to the
    // estimator so the .cg / L1-bypass path degrades to unsupported instead
    // of being silently treated as the default policy.
    auto r = est.estimate_ldgsts(ev.ldgsts_goff.data(), ev.ldgsts_soff.data(),
                                 static_cast<int>(ev.element_width),
                                 ev.active_mask,
                                 ev.cache_policy.empty() ? "default"
                                                         : ev.cache_policy);
    e.ldgsts_shared_wf += r.base.shared_wf;
    e.ldgsts_shared_conf += r.shared_conf;
    e.ldgsts_global_conf += r.global_conf;
    e.ldgsts_twf += r.twf;
    e.ldgsts_tag_conf += r.tag_conf;
    e.ldgsts_tset_acc += r.tset_acc;
    e.ldgsts_sectors += r.sectors;
    // The full LDGSTS confidence/applicability contract (Blocker-2): each
    // field group keeps its own label — SharedWf (entry confidence), count
    // fields (exact-empirical), conflict fields (approximate/unsupported).
    e.confidence = semu::l1tex::confidence_name(r.shared_wf_confidence);
    e.ldgsts_count_confidence =
        semu::l1tex::confidence_name(r.count_confidence);
    e.ldgsts_conflict_confidence =
        semu::l1tex::confidence_name(r.conflict_confidence);
    e.ldgsts_applicability = r.applicability;
    e.ldgsts_model_version = r.model_version;
    e.cache_policy = r.cache_policy;
}

ProfilerReport MemoryProfiler::report() const {
    ProfilerReport rep;
    rep.kernel = kernel_;
    rep.simulated_sm_count = sm_count_;

    aggregate_.clear();
    // Deterministic per-SM / per-subcore accumulation state.
    std::map<std::uint32_t, SmL1TexSummary> sms;
    std::map<std::uint64_t, std::map<std::uint32_t, std::uint32_t>> sector_sms;  // L2 sector -> sm set
    // L1 resident lines per SM (cold-cache first-touch miss model).
    std::map<std::uint32_t, std::vector<std::uint64_t>> sm_resident_lines;

    // Round-2 H3: L2 request state carries the full identity (parent/sector/SM)
    // so a completion is only valid when EVERY component matches, and a request
    // whose id is already present is a duplicate defect (the round-1 code
    // silently overwrote it).
    struct L2RequestState {
        std::uint64_t parent_event_id = 0;
        std::uint64_t sector = 0;
        std::uint32_t sm = 0;
        // Round-3 fix: the request's kind (load/store/atomic/...) is recorded
        // here so an atomic serialization chain can be attributed from the
        // REQUIRED request identity, never from the completion event — a
        // well-formed completion may legitimately omit request_kind while the
        // request it completes carries it.
        std::string request_kind;
        bool completed = false;
    };
    std::map<std::uint64_t, L2RequestState> l2_requests;
    std::map<std::uint64_t, std::vector<std::uint64_t>> sector_atomics;
    // request_id -> deterministic L2 completion seq (issue_tick of the
    // validated atomic completion).  The chain edges are built from this seq,
    // so they are invariant to the host event-list arrangement.
    std::map<std::uint64_t, std::uint64_t> atomic_seq;

    // -----------------------------------------------------------------------
    // Pass 1a — raw host order.  Per-event trace (row order is deterministic
    // and kept as-is), L2 REQUEST accounting, and the order-independent
    // per-event aggregates (commutative sums).  NO stateful L1TEX analysis
    // here: that runs on the arbitrated order in pass 2 (Blocker-1).
    // Loop-3 fix: L2 COMPLETIONS are NOT classified here.  Classification
    // needs the full request table (a completion is only an orphan when its
    // request id never appears ANYWHERE in the list — a completion that merely
    // arrives before its request in the host arrangement is a valid edge), so
    // it runs against the complete table in pass 1b (order-independent).
    // -----------------------------------------------------------------------
    for (const auto& ev : events_) {
        // Optional per-event trace line (deterministic: raw event order).
        {
            std::ostringstream t;
            t << "{\"kind\":" << static_cast<int>(ev.kind)
              << ",\"id\":" << ev.event_id << ",\"sm\":" << ev.sm
              << ",\"subcore\":" << ev.subcore << ",\"pc\":" << ev.pc
              << ",\"mnemonic\":\"" << json_escape(ev.mnemonic) << "\""
              << ",\"space\":\"" << (ev.coupled_l1_to_shared
                                         ? "ldgsts"
                                         : space_name(ev.address_space))
              << "\",\"active\":" << ev.active_mask << ",\"tick\":"
              << ev.issue_tick << "}";
            rep.events_trace.push_back(t.str());
        }
        if (ev.kind == MemoryEventKind::kL2Request) {
            rep.l2.request_count++;
            if (std::find(rep.l2.sectors.begin(), rep.l2.sectors.end(),
                          ev.sector) == rep.l2.sectors.end()) {
                rep.l2.sectors.push_back(ev.sector);
            }
            if (std::find(rep.l2.lines.begin(), rep.l2.lines.end(), ev.sector) ==
                rep.l2.lines.end()) {
                rep.l2.lines.push_back(ev.sector);
            }
            rep.l2.requests_per_sm[ev.sm]++;
            sector_sms[ev.sector][ev.sm]++;
            // Round-2 H3: a duplicate request id is a defect.  The second
            // request must NOT overwrite the first (the round-1 behaviour
            // silently dropped it); it is counted separately and only the
            // first occurrence is tracked for completion validation / atomic
            // chains.
            if (l2_requests.find(ev.request_id) != l2_requests.end()) {
                rep.l2.duplicate_requests++;
            } else {
                l2_requests[ev.request_id] = {ev.parent_event_id, ev.sector,
                                              ev.sm, ev.request_kind, false};
                if (ev.request_kind == "atomic") {
                    rep.l2.atomic_requests++;
                    sector_atomics[ev.sector].push_back(ev.request_id);
                }
            }
            continue;
        }
        if (ev.kind == MemoryEventKind::kL2Completion) {
            // Classified in pass 1b against the complete request table.
            continue;
        }
        if (ev.kind != MemoryEventKind::kL1TexIssue) continue;

        // --- raw access stream (commutative per-event sums) ----------------
        const std::string space = ev.coupled_l1_to_shared
                                      ? "ldgsts"
                                      : std::string(space_name(ev.address_space));
        std::string key =
            key_of(space, ev.mnemonic, ev.variant_class, ev.cache_policy, ev.pc);
        AggregateEntry& e = aggregate_[key];
        e.kernel = kernel_;
        e.pc = ev.pc;
        e.mnemonic = ev.mnemonic;
        e.variant = ev.variant_class;
        e.space = space;
        e.events++;

        if (ev.coupled_l1_to_shared) {
            accumulate_ldgsts(ev, e);
        } else if (ev.address_space == EventAddressSpace::kShared) {
            accumulate_shared(ev, e);
        } else if (ev.address_space == EventAddressSpace::kGlobal) {
            accumulate_global(ev, e);
        }
    }

    // Pass 1b — L2 completion classification, order-independent because it
    // validates against the COMPLETE request table built in pass 1a.  A
    // completion is an orphan only when its request id never exists at all;
    // arriving (or being listed) before the request is NOT a defect.
    for (const auto& ev : events_) {
        if (ev.kind != MemoryEventKind::kL2Completion) continue;
        rep.l2.completion_count++;
        // High-4 + round-2 H3: validate the one-to-one request->completion
        // edge instead of unconditionally counting it.  An orphan completion
        // (unknown request id) and a duplicate completion (request already
        // completed) are both defects; an identity mismatch on the request's
        // parent/sector/SM is treated as a malformed/orphan completion too.
        auto it = l2_requests.find(ev.request_id);
        if (it == l2_requests.end()) {
            // Completion references a request that was never issued anywhere
            // in the event list.
            rep.l2.orphan_completions++;
        } else if (it->second.parent_event_id != ev.parent_event_id ||
                   it->second.sector != ev.sector ||
                   it->second.sm != ev.sm) {
            // Identity mismatch: the completion claims to finish a request
            // whose L1 parent, sector or SM differs — malformed, not a
            // valid edge (checked BEFORE the duplicate test so a
            // wrong-identity completion of an already-done request is an
            // orphan, not a duplicate).
            rep.l2.orphan_completions++;
        } else if (it->second.completed) {
            // The request already has a valid completion.
            rep.l2.duplicate_completions++;
        } else {
            it->second.completed = true;
            rep.l2.completion_edges++;
            // Record the deterministic L2 completion seq for atomics so
            // the serialization chain is built from the serialized order
            // (issue_tick of the completion == completion_seq), never
            // from the host event-list arrangement.  The atomic attribute is
            // taken from the REQUEST the completion completes (the completion
            // event itself may legitimately omit request_kind).
            if (it->second.request_kind == "atomic") {
                atomic_seq[ev.request_id] = ev.issue_tick;
            }
        }
    }

    // Round-2 H3: atomic serialization chains are constructed EXPLICITLY, not
    // counted by sector size.  Per sector, the atomics with a validated
    // completion are ordered by the deterministic L2 completion seq and
    // adjacent dependency edges are emitted.  Because the seq is carried on
    // each completion, the chain is invariant to the host event-list
    // arrangement (out-of-order arrival, shuffled completions).
    // Round-3 H1: the member sort uses (completion_seq, REQUEST_ID) so even
    // two atomics whose completions share the same seq (e.g. a hand-built
    // event multiset that ties on issue_tick) resolve deterministically, and
    // the report keeps EXPLICIT edge identity — from/to request ids, sector
    // and both completion seqs — so a test can assert the actual chain
    // C->A->B, not merely that some 3-member permutation produced 2 edges.
    for (const auto& [sector, ids] : sector_atomics) {
        std::vector<std::uint64_t> members;
        for (auto id : ids) {
            if (atomic_seq.find(id) != atomic_seq.end()) members.push_back(id);
        }
        std::sort(members.begin(), members.end(),
                  [&](std::uint64_t a, std::uint64_t b) {
                      const std::uint64_t sa = atomic_seq.at(a);
                      const std::uint64_t sb = atomic_seq.at(b);
                      if (sa != sb) return sa < sb;
                      return a < b;  // request-id tie-break
                  });
        if (members.size() >= 2) {
            rep.l2.atomic_serialization_chains++;
            for (std::size_t i = 1; i < members.size(); ++i) {
                AtomicSerializationEdge edge;
                edge.from_request_id = members[i - 1];
                edge.to_request_id = members[i];
                edge.sector = sector;
                edge.from_seq = atomic_seq.at(members[i - 1]);
                edge.to_seq = atomic_seq.at(members[i]);
                rep.l2.atomic_serialization_edges_list.push_back(edge);
            }
        }
    }
    rep.l2.atomic_serialization_edges =
        rep.l2.atomic_serialization_edges_list.size();

    // -----------------------------------------------------------------------
    // Pass 2 — L1TEX hierarchy on the DETERMINISTIC ARBITRATED order
    // (Blocker-1).  Group L1TexIssue events by SM; within each subcore sort by
    // (subcore-local issue tick, event id); merge the four streams by
    // (issue tick, subcore id).  Every stateful cache/miss decision consumes
    // this merged order, so the miss attribution is invariant to the host-side
    // event-list arrangement.
    // -----------------------------------------------------------------------
    std::map<std::uint32_t, std::array<std::vector<const MemoryEvent*>, 4>>
        streams_by_sm;
    for (const auto& ev : events_) {
        if (ev.kind != MemoryEventKind::kL1TexIssue) continue;
        streams_by_sm[ev.sm][ev.subcore % 4].push_back(&ev);
    }
    for (auto& [sm_id, streams] : streams_by_sm) {
        (void)sm_id;
        for (auto& stream : streams) {
            std::sort(stream.begin(), stream.end(),
                      [](const MemoryEvent* a, const MemoryEvent* b) {
                          if (a->issue_tick != b->issue_tick)
                              return a->issue_tick < b->issue_tick;
                          return a->event_id < b->event_id;
                      });
        }
        // K-way merge of the four per-subcore streams by (issue_tick,
        // subcore_id): a deterministic round-robin over the tick domain.
        std::vector<const MemoryEvent*> merged;
        std::array<std::size_t, 4> idx = {0, 0, 0, 0};
        while (true) {
            int best = -1;
            for (std::uint32_t s = 0; s < 4; ++s) {
                if (idx[s] >= streams[s].size()) continue;
                if (best < 0) {
                    best = static_cast<int>(s);
                    continue;
                }
                const auto* a = streams[s][idx[s]];
                const auto* b = streams[static_cast<std::size_t>(best)][idx[static_cast<std::size_t>(best)]];
                if (a->issue_tick < b->issue_tick ||
                    (a->issue_tick == b->issue_tick && s < static_cast<std::uint32_t>(best))) {
                    best = static_cast<int>(s);
                }
            }
            if (best < 0) break;
            // NB: increment the INDEX, not the stored element — writing
            // `streams[best][idx[best]]++` would advance the pointer in the
            // vector (and never move idx), hanging the merge.
            const std::size_t bi = static_cast<std::size_t>(best);
            merged.push_back(streams[bi][idx[bi]]);
            ++idx[bi];
        }

        for (const auto* ev : merged) {
            SmL1TexSummary& sm = sms[ev->sm];
            sm.sm_id = ev->sm;
            sm.event_count++;
            if (sm.subcores.empty()) sm.subcores.resize(4);
            SubcoreStreamSummary& sc = sm.subcores[ev->subcore % 4];
            sc.subcore_id = ev->subcore % 4;
            sc.request_count++;
            if (sc.request_count == 1 || ev->issue_tick < sc.first_tick) {
                sc.first_tick = ev->issue_tick;
            }
            if (ev->issue_tick > sc.last_tick) sc.last_tick = ev->issue_tick;

            // Miss/bypass classification over 128-B lines (cold-cache model).
            // Round-2 B1: a .cg / L1-bypass request (cache_policy "cg" or
            // miss_path "l1-bypass") NEVER queries or updates the resident
            // line set — a bypassed line must not become resident, otherwise
            // a later default-policy access to the same line is wrongly
            // classified as a hit.  Bypass is recorded separately (count +
            // reason), the line list still records that the line was touched.
            const bool bypass = ev->cache_policy == "cg" ||
                                ev->miss_path == "l1-bypass";
            // Round-3 B1: a coupled LDGSTS event whose prediction is
            // UNAVAILABLE (address-computation overflow / invalid lane — the
            // interpreter sets prediction=false and leaves goff/soff as
            // invalid placeholder zeros) must NOT feed ANY L1 line/sector/
            // cache-state modeling.  With prediction=true the goff source
            // addresses are real and drive line/sector bookkeeping; with
            // prediction=false they are garbage: modelling them would
            // fabricate line 0 as resident, produce a spurious compulsory
            // miss, and misclassify a later REAL default-policy access to
            // line 0 as a hit.  The access is counted + reasoned separately
            // (prediction_unavailable), never as a miss/hit/bypass.
            if (ev->coupled_l1_to_shared && !ev->prediction) {
                sc.prediction_unavailable++;
                if (sc.prediction_unavailable_reasons.size() < 8) {
                    sc.prediction_unavailable_reasons.push_back(
                        "prediction-unavailable(no-l1-model sm" +
                        std::to_string(ev->sm) + " subcore" +
                        std::to_string(sc.subcore_id) + ")");
                }
                continue;
            }
            std::vector<std::uint64_t> lines;
            if (ev->coupled_l1_to_shared) {
                for (auto g : ev->ldgsts_goff) {
                    const std::uint64_t ln = g / 128;
                    if (std::find(lines.begin(), lines.end(), ln) ==
                        lines.end()) {
                        lines.push_back(ln);
                    }
                }
            } else if (ev->address_space == EventAddressSpace::kGlobal) {
                for (const auto& lr : ev->lane_ranges) {
                    if (!lr.active) continue;
                    for (std::uint64_t k = 0; k < lr.len; ++k) {
                        const std::uint64_t ln = (lr.base + k) / 128;
                        if (std::find(lines.begin(), lines.end(), ln) ==
                            lines.end()) {
                            lines.push_back(ln);
                        }
                    }
                }
            }
            for (auto ln : lines) {
                if (std::find(sm.lines.begin(), sm.lines.end(), ln) ==
                    sm.lines.end()) {
                    sm.lines.push_back(ln);
                }
                if (std::find(sc.lines.begin(), sc.lines.end(), ln) ==
                    sc.lines.end()) {
                    sc.lines.push_back(ln);
                }
                if (bypass) {
                    sc.bypasses++;
                    if (sc.bypass_reasons.size() < 8) {
                        sc.bypass_reasons.push_back(
                            "l1-bypass(policy=" + ev->cache_policy + " line" +
                            std::to_string(ln) + ")");
                    }
                    continue;
                }
                auto& resident = sm_resident_lines[ev->sm];
                if (std::find(resident.begin(), resident.end(), ln) ==
                    resident.end()) {
                    resident.push_back(ln);
                    sc.misses++;
                    sc.miss_reasons.push_back(
                        "compulsory-miss(first-line-touch sm" +
                        std::to_string(ev->sm) + " line" + std::to_string(ln) +
                        ")");
                } else if (sc.miss_reasons.size() < 8) {
                    sc.miss_reasons.push_back(
                        "hit(resident-line " + std::to_string(ln) + ")");
                }
            }
            // 32-B sectors (L1 granularity) per subcore + SM.
            std::vector<std::uint64_t> secs;
            if (ev->coupled_l1_to_shared) {
                for (auto g : ev->ldgsts_goff) {
                    const std::uint64_t s = g / 32;
                    if (std::find(secs.begin(), secs.end(), s) == secs.end()) {
                        secs.push_back(s);
                    }
                }
            } else if (ev->address_space == EventAddressSpace::kGlobal) {
                for (const auto& lr : ev->lane_ranges) {
                    if (!lr.active) continue;
                    for (std::uint64_t k = 0; k < lr.len; ++k) {
                        const std::uint64_t s = (lr.base + k) / 32;
                        if (std::find(secs.begin(), secs.end(), s) ==
                            secs.end()) {
                            secs.push_back(s);
                        }
                    }
                }
            }
            for (auto s : secs) {
                if (std::find(sm.sectors.begin(), sm.sectors.end(), s) ==
                    sm.sectors.end()) {
                    sm.sectors.push_back(s);
                }
                if (std::find(sc.sectors.begin(), sc.sectors.end(), s) ==
                    sc.sectors.end()) {
                    sc.sectors.push_back(s);
                }
            }
        }
    }

    for (auto& [s, sm] : sms) {
        (void)s;
        std::sort(sm.sectors.begin(), sm.sectors.end());
        std::sort(sm.lines.begin(), sm.lines.end());
        for (auto& sc : sm.subcores) {
            std::sort(sc.sectors.begin(), sc.sectors.end());
            std::sort(sc.lines.begin(), sc.lines.end());
        }
        rep.l1tex_per_sm.push_back(std::move(sm));
    }

    // L2 cross-SM contention: sectors touched by more than one SM.
    for (const auto& [sector, smset] : sector_sms) {
        (void)sector;
        if (smset.size() > 1) rep.l2.cross_sm_sector_contention++;
    }
    // Normalize the L2 sector/line lists so the aggregate is independent of
    // host worker arrival order (the multiset is what matters, not first-seen
    // order).
    std::sort(rep.l2.sectors.begin(), rep.l2.sectors.end());
    std::sort(rep.l2.lines.begin(), rep.l2.lines.end());

    for (auto& [k, e] : aggregate_) {
        (void)k;
        rep.aggregate.push_back(std::move(e));
    }
    return rep;
}

std::string AggregateEntry::to_json() const {
    std::ostringstream o;
    o << "{\"kernel\":\"" << json_escape(kernel) << "\",\"pc\":" << pc
      << ",\"mnemonic\":\"" << json_escape(mnemonic)
      << "\",\"variant\":\"" << json_escape(variant) << "\",\"space\":\""
      << json_escape(space) << "\",\"events\":" << events
      << ",\"shared_passes\":" << shared_passes
      << ",\"shared_conflicts\":" << shared_conflicts
      << ",\"shared_broadcasts\":" << shared_broadcasts
      << ",\"lane_requested_bytes\":" << lane_requested_bytes
      << ",\"unique_useful_bytes\":" << unique_useful_bytes
      << ",\"duplicate_reuse_bytes\":" << duplicate_reuse_bytes
      << ",\"sector_fetch_bytes\":" << sector_fetch_bytes
      << ",\"sector_overfetch_bytes\":" << sector_overfetch_bytes
      << ",\"line_fill_bytes\":" << line_fill_bytes
      << ",\"line_overfetch_bytes\":" << line_overfetch_bytes
      << ",\"data_bank_passes\":" << data_bank_passes
      << ",\"data_bank_conflicts\":" << data_bank_conflicts
      << ",\"tag_bank_passes\":" << tag_bank_passes
      << ",\"ldgsts_shared_wf\":" << ldgsts_shared_wf
      << ",\"ldgsts_shared_conf\":" << ldgsts_shared_conf
      << ",\"ldgsts_global_conf\":" << ldgsts_global_conf
      << ",\"ldgsts_twf\":" << ldgsts_twf
      << ",\"ldgsts_tag_conf\":" << ldgsts_tag_conf
      << ",\"ldgsts_tset_acc\":" << ldgsts_tset_acc
      << ",\"ldgsts_sectors\":" << ldgsts_sectors
      << ",\"prediction_unavailable_events\":" << prediction_unavailable_events
      << ",\"confidence\":\"" << json_escape(confidence)
      << "\",\"ldgsts_count_confidence\":\"" << json_escape(ldgsts_count_confidence)
      << "\",\"ldgsts_conflict_confidence\":\""
      << json_escape(ldgsts_conflict_confidence)
      << "\",\"ldgsts_applicability\":\"" << json_escape(ldgsts_applicability)
      << "\",\"ldgsts_model_version\":\"" << json_escape(ldgsts_model_version)
      << "\",\"cache_policy\":\"" << json_escape(cache_policy) << "\"}";
    return o.str();
}

std::string ProfilerReport::to_json(bool include_trace) const {
    std::ostringstream o;
    o << "{\"schema_version\":\"" << json_escape(schema_version)
      << "\",\"kernel\":\"" << json_escape(kernel)
      << "\",\"simulated_sm_count\":" << simulated_sm_count
      << ",\"aggregate\":[";
    for (std::size_t i = 0; i < aggregate.size(); ++i) {
        if (i) o << ",";
        o << aggregate[i].to_json();
    }
    o << "],\"l1tex\":{\"per_sm\":[";
    for (std::size_t i = 0; i < l1tex_per_sm.size(); ++i) {
        if (i) o << ",";
        const auto& sm = l1tex_per_sm[i];
        o << "{\"sm_id\":" << sm.sm_id << ",\"hierarchy_version\":\""
          << json_escape(sm.hierarchy_version) << "\",\"subcore_mapper\":\""
          << json_escape(sm.subcore_mapper) << "\",\"arbitration\":\""
          << json_escape(sm.arbitration) << "\",\"event_count\":"
          << sm.event_count << ",\"sectors\":[";
        for (std::size_t j = 0; j < sm.sectors.size(); ++j) {
            if (j) o << ",";
            o << sm.sectors[j];
        }
        o << "],\"lines\":[";
        for (std::size_t j = 0; j < sm.lines.size(); ++j) {
            if (j) o << ",";
            o << sm.lines[j];
        }
        o << "],\"subcores\":[";
        for (std::size_t j = 0; j < sm.subcores.size(); ++j) {
            if (j) o << ",";
            const auto& sc = sm.subcores[j];
            o << "{\"subcore_id\":" << sc.subcore_id
              << ",\"request_count\":" << sc.request_count
              << ",\"first_tick\":" << sc.first_tick
              << ",\"last_tick\":" << sc.last_tick
              << ",\"misses\":" << sc.misses
              << ",\"bypasses\":" << sc.bypasses
              << ",\"prediction_unavailable\":" << sc.prediction_unavailable
              << ",\"sectors\":[";
            for (std::size_t k = 0; k < sc.sectors.size(); ++k) {
                if (k) o << ",";
                o << sc.sectors[k];
            }
            o << "],\"lines\":[";
            for (std::size_t k = 0; k < sc.lines.size(); ++k) {
                if (k) o << ",";
                o << sc.lines[k];
            }
            o << "],\"miss_reasons\":[";
            for (std::size_t k = 0; k < sc.miss_reasons.size(); ++k) {
                if (k) o << ",";
                o << "\"" << json_escape(sc.miss_reasons[k]) << "\"";
            }
            o << "],\"bypass_reasons\":[";
            for (std::size_t k = 0; k < sc.bypass_reasons.size(); ++k) {
                if (k) o << ",";
                o << "\"" << json_escape(sc.bypass_reasons[k]) << "\"";
            }
            o << "],\"prediction_unavailable_reasons\":[";
            for (std::size_t k = 0; k < sc.prediction_unavailable_reasons.size();
                 ++k) {
                if (k) o << ",";
                o << "\"" << json_escape(sc.prediction_unavailable_reasons[k])
                  << "\"";
            }
            o << "]}";
        }
        o << "]}";
    }
    o << "],\"model_version\":\"" << json_escape(kL1TexHierarchyVersion)
      << "\"},\"l2\":{\"request_count\":" << l2.request_count
      << ",\"completion_count\":" << l2.completion_count
      << ",\"sectors\":[";
    for (std::size_t i = 0; i < l2.sectors.size(); ++i) {
        if (i) o << ",";
        o << l2.sectors[i];
    }
    o << "],\"lines\":[";
    for (std::size_t i = 0; i < l2.lines.size(); ++i) {
        if (i) o << ",";
        o << l2.lines[i];
    }
    o << "],\"requests_per_sm\":{";
    bool first = true;
    for (const auto& [sm, n] : l2.requests_per_sm) {
        if (!first) o << ",";
        first = false;
        o << "\"sm" << sm << "\":" << n;
    }
    o << "},\"cross_sm_sector_contention\":" << l2.cross_sm_sector_contention
      << ",\"completion_edges\":" << l2.completion_edges
      << ",\"orphan_completions\":" << l2.orphan_completions
      << ",\"duplicate_completions\":" << l2.duplicate_completions
      << ",\"duplicate_requests\":" << l2.duplicate_requests
      << ",\"atomic_requests\":" << l2.atomic_requests
      << ",\"atomic_serialization_chains\":" << l2.atomic_serialization_chains
      << ",\"atomic_serialization_edges\":" << l2.atomic_serialization_edges
      << ",\"atomic_serialization_edges_list\":[";
    for (std::size_t i = 0; i < l2.atomic_serialization_edges_list.size(); ++i) {
        if (i) o << ",";
        const auto& e = l2.atomic_serialization_edges_list[i];
        o << "{\"from_request_id\":" << e.from_request_id
          << ",\"to_request_id\":" << e.to_request_id << ",\"sector\":"
          << e.sector << ",\"from_seq\":" << e.from_seq << ",\"to_seq\":"
          << e.to_seq << "}";
    }
    o << "],\"confidence\":\"" << json_escape(l2.confidence)
      << "\",\"unsupported\":\"" << json_escape(l2.unsupported) << "\"}";
    if (include_trace) {
        o << ",\"events_trace\":[";
        for (std::size_t i = 0; i < events_trace.size(); ++i) {
            if (i) o << ",";
            o << events_trace[i];
        }
        o << "]";
    }
    o << "}";
    return o.str();
}

std::string ProfilerReport::to_text() const {
    std::ostringstream o;
    o << "profiler report (schema " << schema_version << ", kernel \""
      << kernel << "\", sm_count " << simulated_sm_count << ")\n";
    o << "aggregate by (pc, variant, space):\n";
    for (const auto& e : aggregate) {
        o << "  " << e.mnemonic << "@" << e.pc << " ["
          << (e.variant.empty() ? "-" : e.variant) << "/" << e.space
          << "] events=" << e.events;
        if (e.space == "shared") {
            o << " passes=" << e.shared_passes
              << " conflicts=" << e.shared_conflicts
              << " broadcasts=" << e.shared_broadcasts;
        } else if (e.space == "global") {
            o << " lane_req=" << e.lane_requested_bytes
              << " unique_useful=" << e.unique_useful_bytes
              << " reuse=" << e.duplicate_reuse_bytes
              << " sector_fetch=" << e.sector_fetch_bytes
              << " data_bank_passes=" << e.data_bank_passes
              << " tag_bank_passes=" << e.tag_bank_passes;
        } else if (e.space == "ldgsts") {
            o << " SharedWf=" << e.ldgsts_shared_wf
              << " SharedConf=" << e.ldgsts_shared_conf
              << " GlobalConf=" << e.ldgsts_global_conf
              << " TWf=" << e.ldgsts_twf
              << " TagConf=" << e.ldgsts_tag_conf
              << " TSetAcc=" << e.ldgsts_tset_acc
              << " Sectors=" << e.ldgsts_sectors
              << " nopred=" << e.prediction_unavailable_events
              << " policy=" << e.cache_policy
              << " (SharedWf=" << e.confidence
              << " counts=" << e.ldgsts_count_confidence
              << " conflicts=" << e.ldgsts_conflict_confidence << ")";
        }
        o << "\n";
    }
    for (const auto& sm : l1tex_per_sm) {
        o << "l1tex sm" << sm.sm_id << " (" << sm.hierarchy_version << ", "
          << sm.subcore_mapper << ") events=" << sm.event_count
          << " sectors=" << sm.sectors.size()
          << " lines=" << sm.lines.size() << "\n";
        for (const auto& sc : sm.subcores) {
            o << "  subcore " << sc.subcore_id << " requests="
              << sc.request_count << " ticks=[" << sc.first_tick << ","
              << sc.last_tick << "] misses=" << sc.misses
              << " bypasses=" << sc.bypasses
              << " nopred=" << sc.prediction_unavailable
              << " sectors=" << sc.sectors.size()
              << " lines=" << sc.lines.size() << "\n";
        }
    }
    o << "l2 requests=" << l2.request_count
      << " completions=" << l2.completion_count
      << " edges=" << l2.completion_edges
      << " orphan=" << l2.orphan_completions
      << " dup=" << l2.duplicate_completions
      << " dup_req=" << l2.duplicate_requests
      << " atomics=" << l2.atomic_requests
      << " chains=" << l2.atomic_serialization_chains
      << " chain_edges=" << l2.atomic_serialization_edges;
    for (const auto& e : l2.atomic_serialization_edges_list) {
        o << " " << e.from_request_id << "->" << e.to_request_id << "@"
          << e.sector << "(seq" << e.from_seq << "->" << e.to_seq << ")";
    }
    o << " cross_sm_sector_contention=" << l2.cross_sm_sector_contention
      << " (confidence " << l2.confidence << "; unsupported: "
      << l2.unsupported << ")\n";
    return o.str();
}

}  // namespace semu::profiler
