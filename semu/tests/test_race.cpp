// Race detector unit tests (Phase 6 Step 2D).
//
// Golden matrix:
//   shared: same-warp lane write/write at one dynamic instruction, read/write,
//           same-warp program order across instructions, cross-warp no
//           barrier, BAR after -> no race, disjoint bytes, same-address
//           atomic, partial active mask, dynamic shared boundary, WAR
//   global: cross-CTA/SM write/write and read/write, atomic release/acquire
//           HB, fence+flag publish, different allocation, overlapping
//           nonaligned range, kernel boundary HB, dedup with reversed
//           observation order
//
// Plus: byte-for-byte deterministic JSON for the same execution.

#include <semu/race_detector.hpp>

#include <cstdio>
#include <string>

#include "test_framework.hpp"

using semu::RaceDetector;
using semu::RaceAccess;
using semu::AllocationId;
using semu::AddressSpace;

namespace {

RaceAccess mk(std::uint32_t sm, std::uint32_t cta, std::uint32_t warp,
              std::uint32_t lane, std::uint64_t insn, std::uint64_t pc,
              std::uint64_t begin, std::uint64_t end, bool write,
              AddressSpace space, AllocationId aid = AllocationId{1},
              std::uint64_t gen = 0) {
    RaceAccess a;
    a.instruction = insn;
    a.pc = pc;
    a.mnemonic = write ? "ST" : "LD";
    a.space = space;
    a.alloc_id = aid;
    a.generation = gen;
    a.cta = cta;
    a.sm = sm;
    a.warp = warp;
    a.lane = lane;
    a.byte_begin = begin;
    a.byte_end = end;
    a.is_write = write;
    a.order_scope_ok = "supported";
    return a;
}

}  // namespace

// Same-warp lane write/write at the SAME dynamic instruction (one warp memory
// instruction whose active lanes are concurrent participants) -> race.
TEST(race_shared_same_warp_write_write) {
    RaceDetector d;
    d.set_enabled(true);
    auto r = d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.empty());
    r = d.observe(mk(0, 0, 0, 1, 1, 0x10, 0, 4, true,
                     AddressSpace::kShared));
    CHECK(r.size() == 1);
    CHECK(r[0].reason.find("concurrent") != std::string::npos ||
          r[0].reason.find("no ") != std::string::npos);
}

// Same-warp lane read/write at one dynamic instruction -> race (concurrent
// participants).
TEST(race_shared_same_warp_read_write) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, false, AddressSpace::kShared));
    auto r = d.observe(mk(0, 0, 0, 1, 1, 0x10, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.size() == 1);
}

// Same warp, DIFFERENT dynamic instructions: warp program order establishes
// HB (a later STS overwrites an earlier one deterministically, no race).
TEST(race_shared_same_warp_program_order_no_race) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared));
    auto r = d.observe(mk(0, 0, 0, 1, 2, 0x20, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.empty());
}

// Cross-warp shared write/write without a barrier -> race.
TEST(race_shared_cross_warp_no_barrier) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared));
    auto r = d.observe(mk(0, 0, 1, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.size() == 1);
}

// After a CTA barrier, cross-warp shared write/write has HB -> no race.
TEST(race_shared_barrier_after_no_race) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared));
    d.cta_barrier(0, 0, {0, 1});  // sync warps 0 and 1
    auto r = d.observe(mk(0, 0, 1, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.empty());  // HB established by the barrier
}

// Disjoint byte ranges at the same shared base -> no race.
TEST(race_shared_disjoint_bytes) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared));
    auto r = d.observe(mk(0, 0, 1, 0, 2, 0x20, 8, 12, true,
                          AddressSpace::kShared));  // bytes 8..12
    CHECK(r.empty());
}

// Same-address atomics are compatible (no race).
TEST(race_shared_same_address_atomic) {
    RaceDetector d;
    d.set_enabled(true);
    auto a1 = mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared);
    a1.is_atomic = true;
    a1.atomic_op = "add";
    d.observe(a1);
    auto a2 = mk(0, 0, 1, 0, 2, 0x20, 0, 4, true, AddressSpace::kShared);
    a2.is_atomic = true;
    a2.atomic_op = "add";
    auto r = d.observe(a2);
    CHECK(r.empty());  // compatible atomics
}

// Global cross-CTA write/write at same address -> race (no sync).
TEST(race_global_cross_cta_write_write) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 1));
    auto r = d.observe(mk(1, 1, 0, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kGlobal, AllocationId{5}, 1));
    CHECK(r.size() == 1);
}

// Global read/write cross-SM at same address -> race.
TEST(race_global_cross_sm_read_write) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, false, AddressSpace::kGlobal,
                 AllocationId{5}, 1));
    auto r = d.observe(mk(1, 1, 0, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kGlobal, AllocationId{5}, 1));
    CHECK(r.size() == 1);
}

// Fence alone establishes no HB; a fence + matching flag publish does not
// race in this model only if the flag read is ordered by a barrier/atomic.
// Without communication, a bare fence leaves the accesses unordered.
TEST(race_global_fence_alone_no_hb) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 1));
    d.fence(0, 0, 0, "gpu");  // bare fence: no HB
    auto r = d.observe(mk(1, 1, 0, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kGlobal, AllocationId{5}, 1));
    CHECK(r.size() == 1);  // still a race (fence alone insufficient)
}

// Atomic release/acquire: a release store on location X followed (in HB) by
// an acquire load of X orders prior writes; a plain relaxed load after the
// release does not.
TEST(race_global_atomic_release_acquire_no_race) {
    RaceDetector d;
    d.set_enabled(true);
    // Data write by cta0.
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 0));
    // Release store to the flag.
    auto rel = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    rel.is_atomic = true;
    rel.mem_order = "release";
    rel.scope = "gpu";
    d.atomic_rmw(rel);
    // Acquire load of the flag by cta1 (same actor chain via a barrier would
    // be needed for real hardware; the detector merges the release clock).
    auto acq = mk(1, 1, 0, 0, 3, 0x30, 0x40, 0x44, false,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    acq.is_atomic = true;
    acq.mem_order = "acquire";
    acq.scope = "gpu";
    d.atomic_rmw(acq);
    // Data read by cta1 after the acquire -> HB via release/acquire chain.
    auto r = d.observe(mk(1, 1, 0, 0, 4, 0x40, 0, 4, false,
                          AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.empty());
}

// A relaxed atomic (or a plain load) after a release does NOT acquire the
// release clock -> the data race remains.
TEST(race_global_atomic_relaxed_after_release_race) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 0));
    auto rel = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    rel.is_atomic = true;
    rel.mem_order = "release";
    rel.scope = "gpu";
    d.atomic_rmw(rel);
    // Relaxed read of the flag by cta1: no acquire -> release not merged.
    auto acq = mk(1, 1, 0, 0, 3, 0x30, 0x40, 0x44, false,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    acq.is_atomic = true;
    acq.mem_order = "relaxed";
    acq.scope = "gpu";
    d.atomic_rmw(acq);
    auto r = d.observe(mk(1, 1, 0, 0, 4, 0x40, 0, 4, false,
                          AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.size() == 1);  // race: relaxed flag read did not acquire
}

// WAR: a write to a byte range a different lane already read races unless
// ordered.
TEST(race_shared_write_after_read_no_order) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 1, 0, 1, 0x10, 0, 4, false, AddressSpace::kShared));
    auto r = d.observe(mk(0, 0, 0, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.size() == 1);  // WAR across warps, no barrier
}

// WAR after a barrier that orders the two warps -> no race.
TEST(race_shared_write_after_read_after_barrier) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, false, AddressSpace::kShared));
    d.cta_barrier(0, 0, {0, 1});
    auto r = d.observe(mk(0, 0, 1, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.empty());
}

// Different global allocations -> no race.
TEST(race_global_different_allocation) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 1));
    auto r = d.observe(mk(0, 0, 0, 1, 2, 0x20, 0, 4, true,
                          AddressSpace::kGlobal, AllocationId{6}, 1));
    CHECK(r.empty());
}

// Overlapping nonaligned ranges (2..6 vs 4..8) -> race.
TEST(race_global_overlap_nonaligned) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 2, 6, true, AddressSpace::kGlobal,
                 AllocationId{5}, 1));
    auto r = d.observe(mk(1, 1, 0, 0, 2, 0x20, 4, 8, true,
                          AddressSpace::kGlobal, AllocationId{5}, 1));
    CHECK(r.size() == 1);
    CHECK(r[0].overlap_begin == 4 && r[0].overlap_end == 6);
}

// Reversed observation order of the same pair must dedup into ONE report
// (Medium fix: canonical actor order in the key).
TEST(race_dedup_reversed_observation_order) {
    RaceDetector a, b;
    a.set_enabled(true);
    b.set_enabled(true);
    const auto x = mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared);
    const auto y = mk(0, 0, 1, 0, 2, 0x20, 0, 4, true, AddressSpace::kShared);
    a.observe(x);
    a.observe(y);
    b.observe(y);  // reversed order of the same two accesses
    b.observe(x);
    const auto ra = a.reports();
    const auto rb = b.reports();
    CHECK(ra.size() == 1 && rb.size() == 1);
    if (!ra.empty() && !rb.empty()) {
        CHECK(ra[0].key == rb[0].key);
        CHECK(ra[0].occurrence == rb[0].occurrence);
    }
}

// Reclaiming a global allocation bumps its generation: an access to a reused
// VA under a new allocation must not alias the old allocation's shadow.
TEST(race_global_reclaim_generation_isolates) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 0));
    d.reclaim_allocation(AllocationId{5});  // gen -> 1, stale shadow dropped
    // A write under the SAME alloc id is now a fresh generation: no race with
    // the pre-reclaim write (its shadow was dropped), so the report set has
    // no stale entry and no new race either (only one live access).
    auto r = d.observe(mk(1, 1, 0, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.empty());
}

// Same execution -> byte-for-byte identical JSON report.
TEST(race_report_deterministic) {
    RaceDetector a, b;
    a.set_enabled(true);
    b.set_enabled(true);
    const auto seq = []() {
        return std::vector<RaceAccess>{
            mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared),
            mk(0, 0, 1, 0, 2, 0x20, 0, 4, true, AddressSpace::kShared),
            mk(0, 0, 0, 1, 3, 0x30, 8, 12, true, AddressSpace::kShared),
        };
    };
    for (const auto& x : seq()) a.observe(x);
    for (const auto& x : seq()) b.observe(x);
    CHECK(a.reports_to_json() == b.reports_to_json());
}

// order_scope_ok is carried in the JSON report.
TEST(race_json_carries_order_scope_ok) {
    RaceDetector d;
    d.set_enabled(true);
    auto x = mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared);
    x.mem_order = "mmio";
    x.scope = "gpu";
    x.order_scope_ok = semu::classify_order_scope("mmio", "gpu");
    d.observe(x);
    auto y = mk(0, 0, 1, 0, 2, 0x20, 0, 4, true, AddressSpace::kShared);
    y.mem_order = "release";
    y.scope = "gpu";
    y.order_scope_ok = semu::classify_order_scope("release", "gpu");
    d.observe(y);
    const std::string j = d.reports_to_json();
    CHECK(j.find("race-analysis-unsupported") != std::string::npos);
    CHECK(j.find("order_scope_ok") != std::string::npos);
}

// classify_order_scope uses scope (weak + any scope; strong with a known
// scope; unknown scope / mmio -> unsupported).
TEST(race_classify_order_scope) {
    CHECK(semu::classify_order_scope("relaxed", "gpu") == "supported");
    CHECK(semu::classify_order_scope("WEAK", "nosco") == "supported");
    CHECK(semu::classify_order_scope("strong", "gpu") == "supported");
    CHECK(semu::classify_order_scope("acq_rel", "cta") == "supported");
    CHECK(semu::classify_order_scope("release", "sys") == "supported");
    CHECK(semu::classify_order_scope("release", "") == "supported");
    CHECK(semu::classify_order_scope("mmio", "gpu") ==
          "race-analysis-unsupported");
    CHECK(semu::classify_order_scope("strong", "bogus") ==
          "race-analysis-unsupported");
    CHECK(semu::classify_order_scope("unknown", "gpu") ==
          "race-analysis-unsupported");
}

// Split semantics: a write then a partial overlapping write then a read of
// the untouched tail must not race with the first write (disjoint sub-range).
TEST(race_interval_split_keeps_nonoverlapping_tail) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 8, true, AddressSpace::kShared));
    auto r = d.observe(mk(0, 0, 1, 0, 2, 0x20, 0, 4, true,
                          AddressSpace::kShared));  // overwrites [0,4)
    CHECK(r.size() == 1);  // only [0,4) races
    // The untouched tail [4,8) must still race with a new writer.
    r = d.observe(mk(0, 0, 2, 0, 3, 0x30, 4, 8, true, AddressSpace::kShared));
    CHECK(r.size() == 1);
}

// Blocker-1: a READ must preserve the overlapped interval's writer.  The
// counterexample: warpA writes X, warpB (HB with A via a barrier) reads X,
// then an unsynchronized warpC writes X.  The third step must surface BOTH
// the WAW (A vs C) and the WAR (B vs C).  The old code dropped A's writer
// when B read, so only B vs C was reported.
TEST(race_read_preserves_writer_for_waw) {
    RaceDetector d;
    d.set_enabled(true);
    // Step 1: warpA (warp 0) writes X [0,4).
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared));
    // Barrier between warp 0 and warp 1 -> A happens-before B.
    d.cta_barrier(0, 0, {0, 1});
    // Step 2: warpB (warp 1) reads X with HB to A -> no RAW.
    auto r = d.observe(mk(0, 0, 1, 0, 2, 0x20, 0, 4, false,
                          AddressSpace::kShared));
    CHECK(r.empty());  // A -> B via barrier: no RAW
    // Step 3: warpC (warp 2) writes X with no HB to anyone.
    r = d.observe(mk(0, 0, 2, 0, 3, 0x30, 0, 4, true, AddressSpace::kShared));
    CHECK(r.size() == 2);  // WAW (A vs C) AND WAR (B vs C)
}

// Blocker (round 3 + round 4): the atomic-writer fast exemption must be scoped
// STRICTLY to the atomic↔atomic writer pair over the same byte range.  It must
// NOT excuse an unsynchronized plain (non-atomic) read after an atomic write.
//
// Round-3 scenario: actor A atomic-writes X → actor B (distinct actor, no HB)
// does a plain read X → actor C atomic-writes X.  Round 3 required the third
// step to report the B/C WAR (the plain read is unordered against C's write);
// the old code bypassed the WAR check against the interval's NON-ATOMIC
// readers, hiding B's plain read.
//
// Round-4 refinement: the exemption must ALSO not hide the A/B RAW on step 2.
// An atomic write does not linearize an unsynchronized plain read — absent a
// happens-before edge, actor B's plain read races against A's atomic write and
// must be reported.  Round 4 therefore changes step 2 from `r.empty()` (the
// over-broad `!access.is_write` exemption) to expecting exactly 1 A/B RAW, so
// an atomic A → plain read B → atomic C chain surfaces BOTH the A/B RAW and
// the B/C WAR.
TEST(race_atomic_write_plain_read_atomic_write_reports_war) {
    RaceDetector d;
    d.set_enabled(true);
    // Step 1: actor A (warp 0) atomic-writes X [0,4).
    auto a = mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared);
    a.is_atomic = true;
    a.atomic_op = "add";
    auto r = d.observe(a);
    CHECK(r.empty());
    // Step 2: actor B (warp 1) does a PLAIN read of X with NO HB to A.  The
    // exemption must NOT cover this plain read: it races against A's atomic
    // write (RAW) and must be reported.
    r = d.observe(mk(0, 0, 1, 0, 2, 0x20, 0, 4, false, AddressSpace::kShared));
    CHECK(r.size() == 1);
    // The A/B RAW report is prior=A (atomic write), current=B (plain read).
    const semu::RaceActor aa{0, 0, 0, 0, 0};
    const semu::RaceActor ba{0, 0, 0, 1, 0};
    CHECK(r[0].first.actor() == aa);
    CHECK(r[0].first.is_atomic);
    CHECK(r[0].second.actor() == ba);
    CHECK(!r[0].second.is_atomic);
    // Step 3: actor C (warp 2) atomic-writes X with NO HB to anyone.  The A/C
    // WAW is exempt (both atomic over the same range) — but the B/C WAR
    // against the plain reader must still surface as a NEW report.
    auto c = mk(0, 0, 2, 0, 3, 0x30, 0, 4, true, AddressSpace::kShared);
    c.is_atomic = true;
    c.atomic_op = "add";
    r = d.observe(c);
    CHECK(r.size() == 1);
    // The new report must involve B (the plain reader) against C.  RaceActor
    // fields are (launch, sm, cta, warp, lane): B = warp 1, C = warp 2.
    const semu::RaceActor ca{0, 0, 0, 2, 0};
    CHECK(r[0].first.actor() == ba);
    CHECK(r[0].second.actor() == ca);
}

// Round-4 guard: when a genuine release/acquire happens-before exists between
// the atomic writer and the plain reader, the directed vector clock eliminates
// the RAW — the plain read must NOT be misreported.  This proves the reported
// step-2 RAW above is due to the missing HB edge, not the nature of the access.
TEST(race_atomic_write_plain_read_with_release_acquire_hb_no_report) {
    RaceDetector d;
    d.set_enabled(true);
    // Step 1: actor A (warp 0) atomic-writes the data X [0,4).
    auto data = mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kShared);
    data.is_atomic = true;
    data.atomic_op = "add";
    auto r = d.observe(data);
    CHECK(r.empty());
    // Step 2: A release.publishs a flag (warp 0) at a disjoint location.
    auto rel = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true, AddressSpace::kShared);
    rel.is_atomic = true;
    rel.mem_order = "release";
    rel.scope = "gpu";
    rel.atomic_op = "st";
    d.atomic_rmw(rel);
    // Barrier-free release/acquire across warps in the same CTA: the acquire
    // in warp 1 on the flag merges A's clock into B.
    auto acq = mk(0, 0, 1, 0, 3, 0x30, 0x40, 0x44, false, AddressSpace::kShared);
    acq.is_atomic = true;
    acq.mem_order = "acquire";
    acq.scope = "gpu";
    acq.atomic_op = "ld";
    d.atomic_rmw(acq);
    // Step 3: actor B (warp 1) does a PLAIN read of X.  HB via release/acquire
    // in the SAME CTA and shared location (scope gpu covers the whole launch)
    // -> A is visible to B -> no RAW, no misreport.
    r = d.observe(mk(0, 0, 1, 0, 4, 0x34, 0, 4, false, AddressSpace::kShared));
    CHECK(r.empty());
}

// Blocker-2: the HB test is DIRECTED prior -> current.  A reverse edge must
// never suppress a race.  Feed the detector out of order (instruction ids not
// monotonic in observation order — as can happen with cross-CTA replay or
// wrong input): warp 0 lane 0 writes at inst 5, then warp 0 lane 1 writes at
// inst 3.  Only prior(inst5) -> current(inst3) is asked; the same-warp
// program-order test reads prior.instruction < current.instruction and fails,
// so the race is reported.  The old code's `|| happens_before(current, prior)`
// accepted the reverse edge and hid it.
TEST(race_reverse_instruction_order_still_races) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 5, 0x10, 0, 4, true, AddressSpace::kShared));
    auto r = d.observe(mk(0, 0, 0, 1, 3, 0x20, 0, 4, true,
                          AddressSpace::kShared));
    CHECK(r.size() == 1);
}

// High-1: a release.cta is only visible within its own CTA.  A release in
// cta0 and an acquire in cta1 on the same location must NOT synchronize even
// though both are cta-scoped on the same byte range.
TEST(race_scope_cta_release_does_not_cross_cta) {
    RaceDetector d;
    d.set_enabled(true);
    // Data write by cta0.
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 0));
    // cta0 releases the flag with .cta scope.
    auto rel = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    rel.is_atomic = true;
    rel.mem_order = "release";
    rel.scope = "cta";
    d.atomic_rmw(rel);
    // cta1 acquires the flag with .cta scope: DIFFERENT CTA -> the release is
    // not visible -> no clock merge.
    auto acq = mk(1, 1, 0, 0, 3, 0x30, 0x40, 0x44, false,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    acq.is_atomic = true;
    acq.mem_order = "acquire";
    acq.scope = "cta";
    d.atomic_rmw(acq);
    // Data read by cta1 after the acquire: must still race with the cta0
    // write (the cta-scoped release/acquire never synchronized).
    auto r = d.observe(mk(1, 1, 0, 0, 4, 0x40, 0, 4, false,
                          AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.size() == 1);
}

// High-1: a release.cta IS visible to an acquire.gpu in the SAME CTA (a wider
// acquire scope covers the releasing thread), but the reverse (release.gpu +
// acquire.cta in different CTAs) must not synchronize.
TEST(race_scope_cta_release_visible_to_same_cta_gpu_acquire) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 0));
    auto rel = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    rel.is_atomic = true;
    rel.mem_order = "release";
    rel.scope = "cta";
    d.atomic_rmw(rel);
    // Acquire.gpu in the SAME CTA: the release's cta-scope includes it and the
    // acquire's gpu-scope includes the releaser -> compatible.
    auto acq = mk(0, 0, 1, 0, 3, 0x30, 0x40, 0x44, false,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    acq.is_atomic = true;
    acq.mem_order = "acquire";
    acq.scope = "gpu";
    d.atomic_rmw(acq);
    auto r = d.observe(mk(0, 0, 1, 0, 4, 0x40, 0, 4, false,
                          AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.empty());
}

// High-1: a release.gpu is NOT visible to an acquire.cta in a DIFFERENT CTA
// (the acquire's cta-scope does not include the releasing thread).
TEST(race_scope_gpu_release_not_visible_to_other_cta_cta_acquire) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 0));
    auto rel = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    rel.is_atomic = true;
    rel.mem_order = "release";
    rel.scope = "gpu";
    d.atomic_rmw(rel);
    auto acq = mk(1, 1, 0, 0, 3, 0x30, 0x40, 0x44, false,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    acq.is_atomic = true;
    acq.mem_order = "acquire";
    acq.scope = "cta";
    d.atomic_rmw(acq);
    auto r = d.observe(mk(1, 1, 0, 0, 4, 0x40, 0, 4, false,
                          AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.size() == 1);
}

// High-1: an SM-scoped release only synchronizes within its SM.
TEST(race_scope_sm_release_domain) {
    RaceDetector d;
    d.set_enabled(true);
    d.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                 AllocationId{5}, 0));
    auto rel = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    rel.is_atomic = true;
    rel.mem_order = "release";
    rel.scope = "sm";
    d.atomic_rmw(rel);
    // Acquire.sm from a DIFFERENT SM (sm=1): release not visible -> race.
    auto acq = mk(1, 1, 0, 0, 3, 0x30, 0x40, 0x44, false,
                  AddressSpace::kGlobal, AllocationId{5}, 0);
    acq.is_atomic = true;
    acq.mem_order = "acquire";
    acq.scope = "sm";
    d.atomic_rmw(acq);
    auto r = d.observe(mk(1, 1, 0, 0, 4, 0x40, 0, 4, false,
                          AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.size() == 1);
    // The same release IS visible to an acquire.sm on the SAME SM.
    RaceDetector d2;
    d2.set_enabled(true);
    d2.observe(mk(0, 0, 0, 0, 1, 0x10, 0, 4, true, AddressSpace::kGlobal,
                  AllocationId{5}, 0));
    auto rel2 = mk(0, 0, 0, 0, 2, 0x20, 0x40, 0x44, true,
                   AddressSpace::kGlobal, AllocationId{5}, 0);
    rel2.is_atomic = true;
    rel2.mem_order = "release";
    rel2.scope = "sm";
    d2.atomic_rmw(rel2);
    auto acq2 = mk(0, 1, 0, 0, 3, 0x30, 0x40, 0x44, false,
                   AddressSpace::kGlobal, AllocationId{5}, 0);
    acq2.is_atomic = true;
    acq2.mem_order = "acquire";
    acq2.scope = "sm";
    d2.atomic_rmw(acq2);
    r = d2.observe(mk(0, 1, 0, 0, 4, 0x40, 0, 4, false,
                      AddressSpace::kGlobal, AllocationId{5}, 0));
    CHECK(r.empty());
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-race");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu race tests\n");
    }
    return failures == 0 ? 0 : 1;
}
