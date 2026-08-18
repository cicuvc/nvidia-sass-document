#pragma once

// FROZEN (SIM_PLAN Phase 10): the profiler schema is locked by
// kReportSchemaVersion "1.0" (locked by a compatibility test); the event
// stream it consumes is kEventStreamVersion (api.hpp).  A profiler-on run and
// a profiler-off run are functionally identical — the stream never feeds back
// into execution.

// Memory profiler (SIM_PLAN Phase 8): backend-neutral execution/memory event
// stream consumers.
//
// The interpreter PRODUCES a normalized memory event stream (MemoryEvent);
// analyzers SUBSCRIBE to it and never feed back into execution — a profiler-on
// run and a profiler-off run are functionally identical.
//
// The report keeps the three resource domains strictly separate (SIM_PLAN
// Phase 8): shared-bank conflicts (SharedBankAnalyzer), L1 data/tag bank
// (global coalescing + L1TEX hierarchy) and L2 request contention
// (L2EventEngine aggregates) are NEVER merged into one counter.
//
// L1TEX hierarchy: per-SM model fed by 4 subcore-ordered streams.  Each
// subcore's stream preserves program order (per-subcore serialization); the
// four streams are arbitrated by a deterministic policy — within each subcore
// events are sorted by (subcore-local issue tick, event id), then the streams
// are merged by (issue tick, subcore id) — and reported per SM/per subcore
// with the model mapping version.  ALL stateful cache/miss analysis (resident
// 128-B lines, compulsory-miss attribution) consumes the arbitrated order, so
// the result is invariant to the host-side event-list arrangement (codex
// review Blocker-1).  L2 requests are an inter-layer interface — L1 completion
// order never masquerades as a cross-SM total order.
//
// Every derived quantity carries model version / applicability / confidence.
// The JSON output uses a fixed schema version (kReportSchemaVersion); a
// compatibility test locks it.

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include <semu/global_model.hpp>
#include <semu/l1tex_model.hpp>
#include <semu/memory_events.hpp>
#include <semu/shared_bank.hpp>

namespace semu::profiler {

constexpr const char* kReportSchemaVersion = "1.0";
constexpr const char* kL1TexHierarchyVersion = "l1tex-hierarchy-v1";
constexpr const char* kL1TexMapperVersion = "warp%4";

// ---------------------------------------------------------------------------
// L1TEX hierarchy (per SM / per subcore)
// ---------------------------------------------------------------------------
struct SubcoreStreamSummary {
    std::uint32_t subcore_id = 0;
    std::uint64_t request_count = 0;
    std::uint64_t first_tick = 0;    // subcore-local issue tick (min)
    std::uint64_t last_tick = 0;     // subcore-local issue tick (max)
    std::vector<std::uint64_t> sectors;  // distinct 32-B sectors on this subcore
    std::vector<std::uint64_t> lines;    // distinct 128-B lines on this subcore
    std::uint64_t misses = 0;        // compulsory misses (first SM line touch)
    std::vector<std::string> miss_reasons;
    // Round-2 B1: .cg / L1-bypass events.  These never query or update the
    // L1 resident-line set — a bypassed line must NOT be recorded as resident
    // (otherwise a later default-policy access to the same line is wrongly
    // classified as a hit).  The bypass is counted and its reason recorded
    // separately from misses/hits.
    std::uint64_t bypasses = 0;
    std::vector<std::string> bypass_reasons;
    // Round-3 B1: coupled LDGSTS events whose prediction is UNAVAILABLE
    // (address-computation overflow / invalid lane — the interpreter sets
    // `prediction=false` and leaves goff/soff as invalid placeholder zeros).
    // Such events never feed ANY L1 line/sector/cache-state modeling: their
    // placeholder offsets (e.g. 0) would otherwise fabricate line 0 as
    // resident, produce a spurious compulsory miss, and misclassify a later
    // REAL default-policy access to line 0 as a hit.  The access is counted
    // and reasoned separately from misses/hits/bypasses.
    std::uint64_t prediction_unavailable = 0;
    std::vector<std::string> prediction_unavailable_reasons;
};

struct SmL1TexSummary {
    std::uint32_t sm_id = 0;
    std::string hierarchy_version = kL1TexHierarchyVersion;
    std::string subcore_mapper = kL1TexMapperVersion;
    std::vector<SubcoreStreamSummary> subcores;   // 4 entries
    std::vector<std::uint64_t> sectors;           // SM-wide merged sectors
    std::vector<std::uint64_t> lines;             // SM-wide merged lines
    std::uint64_t event_count = 0;
    std::string arbitration = "issue-tick-round-robin";
};

// ---------------------------------------------------------------------------
// L2 aggregate (event-based, cross-SM).  Kept separate from L1/shared counts.
// Completion accounting VERIFIES the one-to-one request->completion contract
// (codex review High-4 + round-2 H3): every completion must reference a live
// request, its request_id/parent/sector/SM identity must all match, no request
// may be completed twice, and no two requests may share an id (duplicate
// requests are a defect, reported separately).  Atomics on the same sector
// form a serial chain in the deterministic L2 completion order; the adjacent
// dependency edges between consecutive atomics are constructed explicitly.
// ---------------------------------------------------------------------------
// Round-3 H1: every atomic serialization edge carries EXPLICIT identity — the
// from/to request ids, the serialized sector and the deterministic L2
// completion sequences on both ends.  Reports verify the actual chain (e.g.
// C->A->B) instead of a bare count; the member sort uses
// (completion_seq, request_id) so even equal seqs stay deterministic.
struct AtomicSerializationEdge {
    std::uint64_t from_request_id = 0;  // earlier member in L2 completion order
    std::uint64_t to_request_id = 0;    // later member (depends on `from`)
    std::uint64_t sector = 0;           // serialized 128-B sector
    std::uint64_t from_seq = 0;         // L2 completion sequence of `from`
    std::uint64_t to_seq = 0;           // L2 completion sequence of `to`
};

struct L2Aggregate {
    std::uint64_t request_count = 0;
    std::uint64_t completion_count = 0;
    std::vector<std::uint64_t> sectors;   // distinct 128-B sectors (L2 units)
    std::vector<std::uint64_t> lines;     // distinct 128-B lines
    std::map<std::uint32_t, std::uint64_t> requests_per_sm;
    std::uint64_t cross_sm_sector_contention = 0;  // sectors touched by >1 SM
    std::uint64_t completion_edges = 0;   // VALIDATED one-to-one edges
    std::uint64_t orphan_completions = 0;  // completion with no matching request
    std::uint64_t duplicate_completions = 0;  // completion for an already-completed req
    // Round-2 H3: two requests sharing one request id is a defect (the old
    // code silently overwrote the first request).  Reported separately.
    std::uint64_t duplicate_requests = 0;
    std::uint64_t atomic_requests = 0;       // total atomic requests issued
    std::uint64_t atomic_serialization_chains = 0;  // sectors with >=2 serialized atomics
    std::uint64_t atomic_serialization_edges = 0;   // explicit adjacent atomic dependency edges
    // Round-3 H1: the explicit edge list with full identity (from/to request
    // ids, sector, both completion sequences).  `atomic_serialization_edges`
    // is exactly edges_list.size().
    std::vector<AtomicSerializationEdge> atomic_serialization_edges_list;
    std::string confidence = "exact-empirical";
    // Not modelled: latency and replacement are approximate/unsupported.
    std::string unsupported = "latency,replacement";
};

// ---------------------------------------------------------------------------
// Aggregated per-(kernel, pc, variant, space) entries
// ---------------------------------------------------------------------------
struct AggregateEntry {
    std::string kernel;
    std::uint64_t pc = 0;
    std::string mnemonic;
    std::string variant;   // stable decode class (e.g. "ldgsts__RR32U")
    std::string space;   // "shared" | "global" | "constant" | "local" | "ldgsts"
    std::uint64_t events = 0;

    // Shared bank model aggregate.
    std::uint64_t shared_passes = 0;
    std::uint64_t shared_conflicts = 0;
    std::uint64_t shared_broadcasts = 0;

    // Global coalescing / L1 data+tag bank aggregate.  Byte counters are
    // explicitly denominated (codex review High-1): the lane-width SUM and the
    // distinct-byte UNION are never compared against each other.
    std::uint64_t lane_requested_bytes = 0;    // Σ per-lane request widths
    std::uint64_t unique_useful_bytes = 0;     // distinct bytes covered
    std::uint64_t duplicate_reuse_bytes = 0;   // lane_requested - unique_useful
    std::uint64_t sector_fetch_bytes = 0;
    std::uint64_t sector_overfetch_bytes = 0;  // sector_fetch - unique_useful
    std::uint64_t line_fill_bytes = 0;
    std::uint64_t line_overfetch_bytes = 0;    // line_fill - unique_useful
    std::uint64_t data_bank_passes = 0;
    std::uint64_t data_bank_conflicts = 0;
    std::uint64_t tag_bank_passes = 0;

    // LDGSTS model aggregate (per event, best-effort).  Carries the FULL
    // field set + per-field confidence + applicability + cache policy
    // (codex review Blocker-2): SharedWf / SharedConf / GlobalConf / TWf /
    // TagConf / TSetAcc / Sectors / count+conflict confidence / model scope.
    std::uint64_t ldgsts_shared_wf = 0;
    std::uint64_t ldgsts_shared_conf = 0;
    std::uint64_t ldgsts_global_conf = 0;
    std::uint64_t ldgsts_twf = 0;
    std::uint64_t ldgsts_tag_conf = 0;
    std::uint64_t ldgsts_tset_acc = 0;
    std::uint64_t ldgsts_sectors = 0;
    // Round-2 H1: LDGSTS events whose prediction is unavailable (interpreter
    // detected an address-computation overflow / invalid lane).  Such events
    // are aggregated (events++) but never fabricate model counts — every
    // LDGSTS field stays unsupported and this counter is bumped.
    std::uint64_t prediction_unavailable_events = 0;
    std::string confidence = "exact-architectural";   // SharedWf model confidence
    std::string ldgsts_count_confidence;              // count fields (TWf/TSetAcc/Sectors)
    std::string ldgsts_conflict_confidence;           // SharedConf/GlobalConf
    std::string ldgsts_applicability;                 // model scope
    std::string ldgsts_model_version;                 // "unified-v1"
    std::string cache_policy;                         // "default" | "cg"

    std::string to_json() const;
};

// ---------------------------------------------------------------------------
// Full profiler report (fixed schema)
// ---------------------------------------------------------------------------
struct ProfilerReport {
    std::string schema_version = kReportSchemaVersion;
    std::string kernel;
    std::uint32_t simulated_sm_count = 1;
    std::vector<AggregateEntry> aggregate;      // by (pc, mnemonic, space)
    std::vector<SmL1TexSummary> l1tex_per_sm;   // one per SM id encountered
    L2Aggregate l2;                             // cross-SM event aggregate
    std::vector<std::string> events_trace;      // optional per-event trace

    std::string to_json(bool include_trace = false) const;
    std::string to_text() const;
};

// Analyzer: subscribes to the backend-neutral event stream.
class MemoryProfiler {
public:
    MemoryProfiler(std::string kernel = "", std::uint32_t sm_count = 1);

    // Subscribe: consume one raw event (never mutates the event or execution).
    void add_event(const MemoryEvent& ev);
    void add_events(const std::vector<MemoryEvent>& evs);

    // Analyze everything consumed so far.  Pure read-only.
    ProfilerReport report() const;

    void set_kernel(std::string k) { kernel_ = std::move(k); }
    void set_sm_count(std::uint32_t n) { sm_count_ = n > 0 ? n : 1; }

private:
    void accumulate_shared(const MemoryEvent& ev, AggregateEntry& e) const;
    void accumulate_global(const MemoryEvent& ev, AggregateEntry& e) const;
    void accumulate_ldgsts(const MemoryEvent& ev, AggregateEntry& e) const;

    std::string kernel_;
    std::uint32_t sm_count_ = 1;
    std::vector<MemoryEvent> events_;
    mutable std::map<std::string, AggregateEntry> aggregate_;
};

}  // namespace semu::profiler
