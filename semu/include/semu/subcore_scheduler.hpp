#pragma once

// SM subcore issue/serialization state (SIM_PLAN Phase 6 Step 2B).
//
// Each simulated SM has 4 independent subcore issue cursors.  A warp maps to
// exactly one subcore (stable, configurable via ISubcoreMapper); within a
// subcore, issue order preserves the warp's program order.  The 4 subcores do
// NOT impose a whole-SM total order — they are independent cursors.  Cross-
// subcore port arbitration, when needed, uses an explicit simulator policy
// (deterministic round-robin) and is never called a hardware-exact rule.
//
// This component is trace/issue-state only: it must never change functional
// memory values, scoreboard completion, atomic linearization, or happens-
// before edges.

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace semu {

struct SubcoreId {
    std::uint32_t id = 0;
    bool operator==(const SubcoreId&) const = default;
};

// One subcore's independent issue cursor.  Keeps the subcore-local program
// order and a stable per-request sequence number.
struct SubcoreIssueState {
    SubcoreId id;
    std::uint64_t next_issue_tick = 0;
    std::uint64_t issue_sequence = 0;   // subcore-local monotonic seq
    std::vector<std::uint64_t> issued_requests;  // per-issue, program order

    // Record one issue (program order within this subcore).  Returns the
    // subcore-local sequence assigned.
    std::uint64_t record_issue();
};

// Stable warp -> subcore mapper (review: warp_linear_id % 4 first version,
// encapsulated so a measured mapping change never touches the interpreter
// state machine).
class ISubcoreMapper {
public:
    virtual ~ISubcoreMapper() = default;
    virtual SubcoreId map(std::uint64_t warp_linear_id) const = 0;
    virtual const char* name() const = 0;
};

// Default: warp_linear_id % 4.
class Mod4SubcoreMapper : public ISubcoreMapper {
public:
    SubcoreId map(std::uint64_t warp_linear_id) const override {
        return SubcoreId{static_cast<std::uint32_t>(warp_linear_id % 4)};
    }
    const char* name() const override { return "warp%4"; }
};

// Per-SM L1TEX issue state: 4 subcores + a deterministic tie sequence for any
// cross-subcore arbitration the simulator policy needs (stable replay).
struct SmL1TexState {
    std::uint32_t sm_id = 0;
    std::array<SubcoreIssueState, 4> subcores;
    std::uint64_t next_event_id = 0;
    std::uint64_t deterministic_tie_seq = 0;

    SubcoreIssueState& subcore(SubcoreId id) {
        return subcores[static_cast<std::size_t>(id.id % 4)];
    }
    // Advance the deterministic cross-subcore tie-break counter (stable).
    std::uint64_t next_tie_seq() { return deterministic_tie_seq++; }
};

// Issue a warp memory request on its mapped subcore: record the subcore-local
// sequence and a deterministic global event id.  Returns the assigned ids.
struct SubcoreIssueResult {
    SubcoreId subcore;
    std::uint64_t subcore_seq = 0;
    std::uint64_t event_id = 0;
    std::uint64_t issue_tick = 0;
};
SubcoreIssueResult issue_on_subcore(SmL1TexState& sm,
                                    const ISubcoreMapper& mapper,
                                    std::uint64_t warp_linear_id);

// Serialize the subcore issue state as a compact trace line (does not
// total-order the SM — each subcore's program order is listed separately).
std::string subcore_trace_line(const SmL1TexState& sm);

}  // namespace semu
