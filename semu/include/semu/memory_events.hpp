#pragma once

// FROZEN (SIM_PLAN Phase 10, kEventStreamVersion in api.hpp): the
// backend-neutral normalized memory event stream.  Extensions must ADD
// fields/event kinds in the trailing tags (never renumber existing enum
// values or remove populated fields).

// Normalized memory events (Phase 6 Step 2B, extended Phase 8).  These are
// produced when a dynamic warp memory instruction is issued; they carry
// model-versioned predictions and subcore identity but never change
// functional semantics.
//
// Event types:
//   L1TexIssue      — a warp memory request issued on a subcore
//   TokenService    — a sealed 128-B token's read/write/joint-fiber service
//   L2Request       — a global access that misses L1 (parent = L1TexIssue)
//   L2Completion    — an L2 request completing
//
// Every L1TexIssue / TokenService event is marked `prediction=true` with
// `model_version="unified-v1"` when the SharedWf estimate is attached.
//
// Phase 8 extension: the event stream is backend-neutral — the interpreter
// PRODUCES raw per-lane byte ranges (lane_ranges + address_space + is_write)
// for every committed warp memory access, and analyzers (shared-bank model,
// global sector/line model, L1TEX hierarchy, L2 aggregate, LDGSTS model)
// SUBSCRIBE to the same stream.  Producing/consuming the stream never feeds
// back into execution: profiler-on and profiler-off runs are functionally
// identical.

#include <cstdint>
#include <string>
#include <vector>

namespace semu {

constexpr const char* kModelVersion = "unified-v1";

struct LaneByteRange {
    std::uint64_t base = 0;
    std::uint64_t len = 0;
    bool active = false;
};

enum class MemoryEventKind : std::uint8_t {
    kL1TexIssue = 0,
    kTokenService = 1,
    kL2Request = 2,
    kL2Completion = 3,
};

struct TokenServiceEvent {
    std::uint64_t token_id = 0;
    std::uint32_t active_lanes = 0;
    int read_wf = 0;
    int write_wf = 0;
    int overlap_wf = 0;
    int shared_wf = 0;
    std::uint32_t read_bank_span_mask = 0;   // bit i = bank i read by token
    std::uint32_t write_bank_span_mask = 0;  // bit i = bank i written by token
};

// Address-space discriminator mirrored on the event so analyzers never need
// to reinterpret the request kind string (Phase 8).
enum class EventAddressSpace : std::uint8_t {
    kGlobal = 0,
    kConstant = 1,
    kShared = 2,
    kLocal = 3,
};

struct MemoryEvent {
    MemoryEventKind kind = MemoryEventKind::kL1TexIssue;
    std::uint64_t event_id = 0;
    std::uint64_t parent_event_id = 0;  // L2 parent / L1 issue link
    std::uint64_t instruction = 0;      // dynamic instruction id
    std::uint32_t sm = 0;
    std::uint32_t subcore = 0;
    std::uint32_t cta = 0;
    std::uint32_t warp = 0;
    std::uint32_t active_mask = 0;
    std::uint64_t pc = 0;
    std::string mnemonic;
    // Request kind: load / store / coupled / atomic / constant / local.
    std::string request_kind;
    uint32_t element_width = 4;
    bool coupled_l1_to_shared = false;
    // Prediction metadata (L1TexIssue / TokenService only).
    bool prediction = false;
    std::string model_version;
    int predicted_shared_wf = 0;
    // Per-token service decomposition (TokenService events).
    std::vector<TokenServiceEvent> tokens;
    // L2 sector metadata (L2Request / L2Completion).
    std::uint64_t sector = 0;          // 128-B sector index
    std::vector<std::uint64_t> sectors;  // all sectors touched by this request
    std::uint64_t issue_tick = 0;
    std::string tie_reason;            // stable cross-subcore arbitration note

    // --- Phase 8 backend-neutral raw access stream -------------------------
    EventAddressSpace address_space = EventAddressSpace::kGlobal;
    bool is_write = false;             // store / atomic (else load)
    // Per-lane byte ranges of the COMMITTED access (one entry per active lane,
    // inactive lanes have `active=false`).  `base` is the effective address:
    // global VA for global, shared byte offset for shared, constant-bank
    // offset for constant, per-warp window offset for local.
    std::vector<LaneByteRange> lane_ranges;
    // Coupled LDGSTS source (global/L1) and destination (shared) per-lane byte
    // offsets.  Populated only for coupled_l1_to_shared events so the profiler
    // can recompute the extended LDGSTS counters (TWf/Sectors/TagConf/TSetAcc/
    // SharedConf/GlobalConf) without re-execution.
    std::vector<std::uint32_t> ldgsts_goff;
    std::vector<std::uint32_t> ldgsts_soff;

    // --- Phase 8 refinement (codex review): variant + cache-policy contract --
    // Stable decode class (e.g. "ldgsts__RR32U") so analyzers can aggregate by
    // variant without re-decoding the raw word.  Populated on every L1TexIssue.
    std::string variant_class;
    // Cache policy as seen by L1TEX.  For LDGSTS this is derived from the
    // `loc` FORMAT slot: LOC@BYPASS maps to "cg" (L1 bypass), LOC@ACCESS maps
    // to "default".  Analyzers must honor it (e.g. the LDGSTS estimator marks
    // its SharedWf/conflict counters unsupported on "cg").
    std::string cache_policy;
    // The L1 data path taken by this request: "l1-access" (normal allocate) or
    // "l1-bypass" (the .cg / LOC@BYPASS path that skips L1 fill).
    std::string miss_path;
    // L2 request id (L2Request / L2Completion events): the stable handle the
    // profiler uses to validate one-to-one completion edges and build atomic
    // serialization chains per sector.
    std::uint64_t request_id = 0;
};

}  // namespace semu
