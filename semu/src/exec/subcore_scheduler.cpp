// Subcore issue/serialization state (Phase 6 Step 2B).  Trace-only: never
// affects functional values, scoreboard completion, atomic linearization or
// happens-before edges.

#include <semu/exec/subcore_scheduler.hpp>

#include <sstream>

namespace semu {

std::uint64_t SubcoreIssueState::record_issue() {
    ++issue_sequence;
    issued_requests.push_back(issue_sequence);
    return issue_sequence;
}

SubcoreIssueResult issue_on_subcore(SmL1TexState& sm,
                                    const ISubcoreMapper& mapper,
                                    std::uint64_t warp_linear_id) {
    SubcoreId sc = mapper.map(warp_linear_id);
    SubcoreIssueState& st = sm.subcore(sc);
    SubcoreIssueResult r;
    r.subcore = sc;
    r.subcore_seq = st.record_issue();
    r.event_id = sm.next_event_id++;
    r.issue_tick = st.next_issue_tick++;
    return r;
}

std::string subcore_trace_line(const SmL1TexState& sm) {
    std::ostringstream o;
    o << "sm" << sm.sm_id << " {";
    for (std::size_t i = 0; i < sm.subcores.size(); ++i) {
        if (i) o << " ";
        o << "sc" << i << ":[";
        const auto& sc = sm.subcores[i];
        for (std::size_t j = 0; j < sc.issued_requests.size(); ++j) {
            if (j) o << ",";
            o << sc.issued_requests[j];
        }
        o << "]";
    }
    o << "}";
    return o.str();
}

}  // namespace semu
