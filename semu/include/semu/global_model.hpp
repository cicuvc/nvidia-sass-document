#pragma once

// Global LDG/STG coalescing / sector-line model (SIM_PLAN Phase 8).
//
// Pure analysis over the backend-neutral event stream: given per-lane global
// VAs and a width, it derives the L1TEX data-path structure of a warp access:
//
//   lane_requested_bytes  — Σ per-lane request widths (bytes the lanes asked for)
//   unique_useful_bytes   — distinct bytes covered by the lanes (the union)
//   duplicate_reuse_bytes — lane_requested − unique_useful (bytes requested by
//                           more than one lane; broadcast/reuse traffic)
//   sector_fetch_bytes    — distinct 32-B sectors × 32 (bytes transferred)
//   line_fill_bytes       — distinct 128-B lines × 128 (tag fill footprint)
//   sector_overfetch      — sector_fetch − unique_useful (fetched but unused)
//   line_overfetch        — line_fill − unique_useful
//   coalescing_efficiency — unique_useful / sector_fetch  ∈ [0,1]
//   broadcast_reuse_factor— lane_requested / unique_useful  (≥1 when shared)
//
// These five byte counters are EXPLICITLY denominated (codex review High-1):
// the byte UNION is never compared against the lane-width SUM, so overfetch
// can never be forced to ~0 and a broadcast never reports efficiency > 1.
//
// L1 data-bank and tag-bank are reported SEPARATELY and must never be merged
// with shared-bank conflicts or L2 request contention:
//   data_bank_passes — L1 data-bank service: each lane's byte range is split
//                      into per-128-B-line fragments, then bank-conflict
//                      passes over 32 banks × 4 B words run WITHIN each line
//                      (identical (bank, word) coalesces; different lines
//                      never share data banks, and a lane spanning two lines
//                      contributes fragments to each line independently).
//   tag_bank_passes  — tag-pipeline service: distinct 128-B lines colored by
//                      the token-bank hash tbk(line) into conflict-free waves.
//
// This component NEVER changes memory values, scoreboard completion, atomic
// linearization or happens-before edges: pure read-only analysis.

#include <cstdint>
#include <string>
#include <vector>

#include <semu/shared_bank.hpp>  // LaneAccess (lane/base/len/active)

namespace semu::global_model {

constexpr const char* kGlobalModelVersion = "global-coalesce-v1";
constexpr int kSectorBytes = 32;
constexpr int kLineBytes = 128;

struct LaneMapping {
    std::uint32_t lane = 0;
    std::uint64_t base = 0;          // global VA
    std::uint64_t len = 0;
    std::uint64_t sector = 0;        // base/32
    std::uint64_t line = 0;          // base/128
    std::uint32_t first_bank = 0;    // data bank of the first word
    bool active = false;
};

struct GlobalAccessEstimate {
    std::uint32_t active_lanes = 0;
    // Coalescing byte accounting (explicitly denominated — see the header).
    std::uint64_t lane_requested_bytes = 0;    // Σ per-lane request widths
    std::uint64_t unique_useful_bytes = 0;     // distinct bytes covered (union)
    std::uint64_t duplicate_reuse_bytes = 0;   // lane_requested - unique_useful
    std::uint64_t sector_fetch_bytes = 0;      // sectors.size() * 32 (transferred)
    std::uint64_t line_fill_bytes = 0;         // lines.size() * 128 (tag fill)
    std::uint64_t sector_overfetch_bytes = 0;  // sector_fetch - unique_useful
    std::uint64_t line_overfetch_bytes = 0;    // line_fill - unique_useful
    double coalescing_efficiency = 0.0;        // unique_useful / sector_fetch
    double broadcast_reuse_factor = 0.0;       // lane_requested / unique_useful
    std::vector<std::uint64_t> sectors;  // distinct 32-B sectors (sorted)
    std::vector<std::uint64_t> lines;    // distinct 128-B lines (sorted)
    int data_bank_passes = 0;            // L1 data-bank service passes
    int data_bank_conflicts = 0;         // same-bank different-word conflicts
    int tag_bank_passes = 0;             // tag-pipeline token-bank waves
    std::vector<LaneMapping> lane_map;
    std::string model_version = kGlobalModelVersion;
    // Confidence of each derived quantity (see SIM_PLAN §5):
    //   sectors/lines + byte counters          -> exact-architectural
    //   data_bank_passes / data_bank_conflicts -> exact-architectural
    //   tag_bank_passes                        -> exact-empirical
    std::string confidence = "exact-architectural";

    std::string to_json() const;
};

// Estimate one warp global access.  `lanes` carries 32 entries (inactive:
// active=false); `width` is the per-lane element width {1,2,4,8,16}.
GlobalAccessEstimate estimate(const shared_bank::LaneAccess* lanes,
                              std::uint32_t width);

}  // namespace semu::global_model