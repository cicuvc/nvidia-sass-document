#pragma once

// Shared-memory LDS/STS bank-conflict model (SIM_PLAN Phase 8).
//
// Pure analysis over the backend-neutral event stream: given per-lane shared
// byte offsets, an element width and an active mask, it computes the classic
// 32-bank shared-memory access structure:
//
//   bank = (byte_address / 4) % 32
//
// Lanes are grouped by the LSU lane-group partition (4 B: whole warp, 8 B:
// half warp, 16 B: quarter warp); each group is serviced independently and
// its lanes are greedily coloured into conflict-free passes.  Two lanes
// CONFLICT when they touch the same bank with DIFFERENT words; the same
// (bank, word) pair is a broadcast / coalesce and never a conflict.
//
// Outputs (per access):
//   passes          — number of service passes (wavefronts)
//   per-pass lane/bank detail
//   conflicts       — same-bank distinct-word pairs with a reason chain
//                     (which lane, which bank, which words, which earlier
//                      pass holds the conflicting access)
//   broadcast_count — lanes coalesced onto an identical (bank, word)
//
// This component NEVER changes memory values, scoreboard completion, atomic
// linearization or happens-before edges: it is a pure read-only analyser.

#include <cstdint>
#include <string>
#include <vector>

namespace semu::shared_bank {

constexpr const char* kSharedBankModelVersion = "shared-bank-v1";
constexpr int kSharedBanks = 32;

struct LaneAccess {
    std::uint32_t lane = 0;
    std::uint64_t base = 0;   // shared byte offset
    std::uint64_t len = 0;    // byte width (4/8/16)
    bool active = false;
};

struct PassDetail {
    std::uint32_t pass = 0;        // 0-based pass index
    std::vector<std::uint32_t> lanes;    // lanes served in this pass
    std::vector<std::uint32_t> banks;    // distinct banks touched in this pass
};

struct Conflict {
    std::uint32_t bank = 0;        // conflicting bank
    std::uint32_t lane_a = 0;      // lane already placed (earlier pass or
                                   // earlier in the same pass)
    std::uint32_t word_a = 0;      // word index (byte_address/4) of lane_a
    std::uint32_t lane_b = 0;      // lane deferred to a later pass
    std::uint32_t word_b = 0;      // word index of lane_b
    std::uint32_t pass_a = 0;      // pass that holds lane_a
    std::string reason;            // human-readable cause chain
};

struct SharedAccessEstimate {
    std::uint32_t passes = 0;              // total service passes (0 if no lanes)
    std::uint32_t active_lanes = 0;
    std::uint32_t conflict_count = 0;      // same-bank distinct-word conflicts
    std::uint32_t broadcast_count = 0;     // lanes coalesced onto identical word
    bool is_write = false;
    std::uint32_t element_width = 4;
    std::string model_version = kSharedBankModelVersion;
    std::vector<PassDetail> passes_detail;
    std::vector<Conflict> conflicts;
    // Per-lane first-word bank map (lane -> bank of its first word), for
    // report/trace use.  Size 32; inactive lanes hold 0.
    std::vector<std::uint32_t> lane_bank;

    // JSON rendering (schema-versioned; see profiler.hpp for the report
    // wrapper that carries model version / applicability / confidence).
    std::string to_json() const;
};

// Estimate a warp shared access.  `lanes` carries per-lane offsets/widths for
// all 32 lanes (inactive ones marked `active=false`); `width` is the element
// width and `is_write` distinguishes STS (true) from LDS (false).
SharedAccessEstimate estimate(const std::vector<LaneAccess>& lanes,
                              std::uint32_t width, bool is_write);

// Convenience: 32-lane arrays of byte offsets + active mask.
SharedAccessEstimate estimate(const std::uint64_t base[32],
                              std::uint32_t width, std::uint32_t mask,
                              bool is_write);

}  // namespace semu::shared_bank
