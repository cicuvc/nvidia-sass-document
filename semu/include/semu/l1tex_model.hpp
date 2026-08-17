#pragma once

// UnifiedV1Estimator — pure C++ port of the selector-free unified L1TEX
// SharedWf model (SIM_PLAN Phase 6 Step 2B).
//
// This is a PURE FUNCTION component: no MemoryService, no worker pool, no
// subcore scheduler, no side effects.  It models one mechanism for a coupled
// L1-read -> shared-write transfer (LDGSTS / cp.async style) and nothing else.
//
// For every sealed 128-byte token the single rule is:
//
//     SharedWf = read_waves + write_waves - largest_joint_fiber
//
// Token sealing contract (frozen in unified_model.py `formation`):
//   - 4 B elements:  32 lanes/token
//   - 8 B elements:  16 lanes/token
//   - 16 B elements:  8 lanes/token
//   - active mask only removes lanes within a token; it never compresses lane
//     ids and re-groups across tokens.
//   - tokens never merge fibers, share waves, or cancel overlap across tokens.
//
// Inputs are the same as the Python `simulate(goff, soff, size, mask)`:
//   goff[32] : per-lane global/L1 byte offset
//   soff[32] : per-lane shared byte offset (destination)
//   size     : element width in bytes {4,8,16}
//   mask     : 32-bit active lane mask
//
// Output mirrors the Python dict exactly (see UnifiedEstimate).
//
// Phase 8 extension (estimate_ldgsts): the LDGSTS profiler model.  It extends
// the unified SharedWf rule with the architectural counters the corpus
// measures — TWf / Sectors / TagConf / TSetAcc (pure counts, exact) and
// SharedConf / GlobalConf (per-bank distinct-word conflict counts, definitional)
// — plus per-field confidence and the applicability scope recorded in
// `arch/l1tex/shared_bank_conflicts.md`.  Reference model is
// `~/cs/projects/arch/l1tex/unified_model.py` (NOT `model.py`: the former is
// the single-rule model exact on structured patterns; the latter's selectors
// target random-data accuracy and is deliberately not used).

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace semu::l1tex {

constexpr const char* kUnifiedModelVersion = "unified-v1";

// Per-token decomposition (Python TokenStats entry).
struct TokenStat {
    int token = 0;
    int lanes = 0;
    int read_wf = 0;
    int write_wf = 0;
    int overlap_wf = 0;
    int shared_wf = 0;
};

// The full estimate (Python simulate() return dict).
struct UnifiedEstimate {
    int shared_wf = 0;
    int read_wf = 0;
    int write_wf = 0;
    int overlap_wf = 0;
    int tokens = 0;
    std::vector<TokenStat> token_stats;

    // JSON rendering (for the Python-oracle field-by-field comparison).
    std::string to_json() const;
};

// Confidence taxonomy (SIM_PLAN §5 Profiler 精度分级).
enum class Confidence : std::uint8_t {
    kExactArchitectural = 0,  // pure counting from addresses + arch rules
    kExactEmpirical,          // matches the frozen hardware corpus in scope
    kApproximate,             // known error; scope + source reported
    kUnsupported,             // no reliable model; raw events only
};
const char* confidence_name(Confidence c);

// Phase 8 LDGSTS estimate: unified SharedWf + measured-corpus counters.
struct LdgstsEstimate {
    UnifiedEstimate base;             // SharedWf/ReadWf/WriteWf/OverlapWf/Tokens
    int twf = 0;                      // token wavefronts (T-stage coloring)
    int tag_conf = 0;                 // max(0, TWf - 1)
    int tset_acc = 0;                 // distinct 128-B lines/tags touched
    int sectors = 0;                  // distinct 32-B sectors touched
    int shared_conf = 0;              // shared write-bank distinct-word conflicts
    int global_conf = 0;              // L1 read-bank distinct-word conflicts
    Confidence shared_wf_confidence = Confidence::kApproximate;
    Confidence count_confidence = Confidence::kExactEmpirical;  // TWf/TSetAcc/Sectors
    Confidence conflict_confidence = Confidence::kApproximate;  // Shared/GlobalConf
    std::string applicability;        // model scope per shared_bank_conflicts.md
    std::string model_version = kUnifiedModelVersion;
    std::string cache_policy = "default";  // "cg" => bypass, unsupported paths

    std::string to_json() const;      // full LDGSTS JSON (all fields + confidence)
};

// Deterministic LCG for tests / replay (not used by the estimator itself).
class UnifiedV1Estimator {
public:
    // `goff`/`soff` are 32-lane arrays; `mask` selects active lanes.
    // Returns an empty estimate when no lanes are active.
    UnifiedEstimate estimate(const std::uint32_t goff[32],
                             const std::uint32_t soff[32],
                             int element_width,
                             std::uint32_t mask) const;

    // Convenience over std::vector inputs (validates size 32).
    UnifiedEstimate estimate(const std::vector<std::uint32_t>& goff,
                             const std::vector<std::uint32_t>& soff,
                             int element_width,
                             std::uint32_t mask) const;

    // Phase 8: extended LDGSTS estimate.  Same inputs; `cache_policy`
    // "cg" marks the L1-bypass path (SharedWf/conflicts become unsupported).
    LdgstsEstimate estimate_ldgsts(const std::uint32_t goff[32],
                                   const std::uint32_t soff[32],
                                   int element_width, std::uint32_t mask,
                                   const std::string& cache_policy = "default") const;
};

// Token membership: group id for lane `lane` given element width (used by
// tests to verify sealing; not exposed by the estimator output).
int token_of(int lane, int element_width);

}  // namespace semu::l1tex
