// Profiler integration tests (Phase 8): the backend-neutral event stream is
// produced by the interpreter and consumed by MemoryProfiler with no reverse
// effect.  Covers shared-bank aggregation, global coalescing aggregation,
// LDGSTS aggregation, the L1TEX per-SM/per-subcore hierarchy, the L2 aggregate
// (kept separate from L1/shared counters) and profiler on/off functional
// identity.

#include <semu/context/context.hpp>
#include <semu/interpreter/interpreter.hpp>
#include <semu/memory/l2_events.hpp>
#include <semu/profiler/profiler.hpp>

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "test_framework.hpp"

using namespace semu;
using namespace semu::profiler;

namespace {

struct LoadedKernel {
    std::vector<std::uint8_t> cubin;
    std::string kernel_name;
    Kernel kernel;
};

void push16(std::vector<std::uint8_t>* out, std::uint16_t v) {
    out->push_back(v & 0xff);
    out->push_back((v >> 8) & 0xff);
}

std::vector<std::uint8_t> build_kernel_cubin(
    const std::string& mangled,
    const std::vector<std::pair<std::uint64_t, std::uint64_t>>& words) {
    struct S {
        std::string name;
        std::uint32_t type = 0;
        std::uint64_t flags = 0;
        std::vector<std::uint8_t> data;
        std::uint64_t size = 0;
        std::uint32_t link = 0;
        std::uint32_t info = 0;
        std::uint64_t align = 4;
        std::uint64_t entsize = 0;
    };
    std::vector<S> secs(6);
    secs[1].name = ".shstrtab"; secs[1].type = 3;
    secs[2].name = ".strtab"; secs[2].type = 3;
    secs[3].name = ".symtab"; secs[3].type = 2; secs[3].link = 2;
    secs[3].entsize = 24; secs[3].align = 8;
    secs[4].name = ".text." + mangled; secs[4].type = 1;
    secs[4].flags = 2 | 4; secs[4].align = 128;
    secs[5].name = ".nv.info." + mangled; secs[5].type = 0x70000000;
    secs[5].info = 4;

    auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
        for (int i = 0; i < 4; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
        for (int i = 0; i < 8; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    std::vector<std::uint8_t> text;
    for (const auto& [lo, hi] : words) {
        push64(&text, lo);
        push64(&text, hi);
    }
    std::vector<std::uint8_t> symtab(24, 0);
    auto sym = [&](std::uint32_t name, std::uint8_t info, std::uint8_t other,
                   std::uint16_t shndx, std::uint64_t value,
                   std::uint64_t size) {
        std::vector<std::uint8_t> e;
        push32(&e, name); e.push_back(info); e.push_back(other);
        e.push_back(shndx & 0xff); e.push_back(shndx >> 8);
        push64(&e, value); push64(&e, size);
        symtab.insert(symtab.end(), e.begin(), e.end());
    };
    const std::string text_name = ".text." + mangled;
    std::string strtab = std::string(1, '\0') + text_name + '\0' +
                         mangled + '\0';
    sym(1, 0x03, 0x00, 4, 0, 0);
    sym(static_cast<std::uint32_t>(2 + text_name.size()),
        0x12, 0x10, 4, 0, words.size() * 16);
    secs[4].data = text;
    secs[3].data = symtab;
    secs[2].data.assign(strtab.begin(), strtab.end());
    std::string shstr(1, '\0');
    for (std::size_t i = 1; i < secs.size(); ++i)
        shstr += secs[i].name + '\0';
    secs[1].data.assign(shstr.begin(), shstr.end());

    std::vector<std::uint64_t> offs(secs.size(), 0);
    std::uint64_t cur = 64;
    for (std::size_t i = 1; i < secs.size(); ++i) {
        const std::uint64_t al = std::max<std::uint64_t>(secs[i].align, 1);
        cur = (cur + al - 1) & ~(al - 1);
        offs[i] = cur;
        cur += secs[i].data.size();
    }
    const std::uint64_t shoff = cur;
    std::vector<std::uint8_t> out;
    const std::uint8_t ident[16] = {0x7f, 'E', 'L', 'F', 2, 1, 1, 0x41,
                                    0x08, 0, 0, 0, 0, 0, 0, 0};
    out.insert(out.end(), ident, ident + 16);
    push16(&out, 2);
    push16(&out, 190);
    push32(&out, 1);
    push64(&out, 0);
    push64(&out, 0);
    push64(&out, shoff);
    push32(&out, 0x06007802);
    push16(&out, 64); push16(&out, 56); push16(&out, 0);
    push16(&out, 64);
    push16(&out, static_cast<std::uint16_t>(secs.size()));
    push16(&out, 1);
    for (std::size_t i = 1; i < secs.size(); ++i) {
        while (out.size() % std::max<std::uint64_t>(secs[i].align, 1))
            out.push_back(0);
        out.insert(out.end(), secs[i].data.begin(), secs[i].data.end());
    }
    std::uint32_t name_pos = 1;
    for (std::size_t i = 0; i < secs.size(); ++i) {
        std::uint32_t no = 0;
        if (i > 0) { no = name_pos; name_pos += secs[i].name.size() + 1; }
        push32(&out, no);
        push32(&out, secs[i].type);
        push64(&out, secs[i].flags);
        push64(&out, 0);
        push64(&out, i == 0 ? 0 : offs[i]);
        push64(&out, secs[i].data.size());
        push32(&out, secs[i].link);
        push32(&out, secs[i].info);
        push64(&out, secs[i].align);
        push64(&out, secs[i].entsize);
    }
    return out;
}

LoadedKernel load_kernel(
    const std::string& mangled,
    const std::vector<std::pair<std::uint64_t, std::uint64_t>>& words) {
    LoadedKernel lk;
    lk.cubin = build_kernel_cubin(mangled, words);
    lk.kernel_name = mangled;
    auto m = semu::Module::load(lk.cubin);
    if (m.failed()) {
        std::fprintf(stderr, "load: %s\n", m.take_error().describe().c_str());
        return lk;
    }
    const Kernel* k = m.value().find_kernel(mangled);
    if (k) lk.kernel = *k;
    return lk;
}

// STS kernel: each lane writes TID.X to shared[0] (all lanes -> same word =
// broadcast).  S2R R0, SR_TID.X ; STS [R1], R0 ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kStsKernel = {
    {0x7919ULL, 0xe0a0000002100ULL},   // S2R R0, SR_TID.X
    {0x0000000001007388ULL, 0x001fd00000000800ULL},  // STS [R1], R0 (R1=0)
    {0x794dULL, 0xfea0003800000ULL},   // EXIT
};

// STG kernel: each lane writes TID.X to global[lane*4] (contiguous 4-B).
// S2R R0,SR_TID.X ; MOV32I R3,4 ; IMAD R4,R0,R3,RZ ; MOV32I R5,0 ;
// STG.E.32 desc[..][{R4,R5}],R0 ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kStgKernel = {
    {0x7919ULL, 0xe0a0000002100ULL},               // S2R R0, SR_TID.X
    {0x0000000400037802ULL, 0x001fca0000000f00ULL},  // MOV32I R3, 4
    {0x0000000300047224ULL, 0x001fd000078e02ffULL},  // IMAD R4, R0, R3, RZ
    {0x0000000000057802ULL, 0x001fca0000000f00ULL},  // MOV32I R5, 0
    {0x0000000004007986ULL, 0x001fd0000c101904ULL},  // STG.E.32 desc[..], R0
    {0x794dULL, 0xfea0003800000ULL},                 // EXIT
};

// LDGSTS kernel: S2R R0,SR_TID.X ; LDGSTS.E.32 R4,0x20,[{R0,R1}+URZ+0x10] ;
// EXIT  (functional LDGSTS unimplemented -> fault; prediction events emitted).
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kLdgstsKernel = {
    {0x7919ULL, 0xe0a0000002100ULL},   // S2R R0, SR_TID.X
    {0x2001000047faeULL, 0xfe2000b9200ffULL},  // LDGSTS.E.32 R4, 0x20, ...
    {0x794dULL, 0xfea0003800000ULL},   // EXIT
};

// LDGSTS.E.BYPASS.128 — the .cg / L1-bypass path (LOC@BYPASS, sz=128).
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kLdgstsBypassKernel =
    {
        {0x7919ULL, 0xe0a0000002100ULL},   // S2R R0, SR_TID.X
        {0x2001000047faeULL, 0xfe2000b9008ffULL},  // LDGSTS.E.BYPASS.128 R4,...
        {0x794dULL, 0xfea0003800000ULL},   // EXIT
    };

// LDGSTS.E.32 [RR64U wide form] — sets the global source pair {R0,R1} to
// 0xFFFFFFFF,0xFFFFFFFF so the global address (g = 0xFFFFFFFFFFFFFFFF) plus a
// positive Ra_offset OVERFLOWS 2^64.  The interpreter checks the arithmetic
// (never silent wrap) and marks the prediction unavailable: goff_valid_mask
// stays 0 even though every lane is active.  The shared destination offset
// (Rb=RZ + 0x20) alone would be valid — only the global side overflows.
const std::vector<std::pair<std::uint64_t, std::uint64_t>>
    kLdgstsOverflowKernel = {
        {0xffffffff00007802ULL, 0x001fca0000000f00ULL},  // MOV R0, 0xFFFFFFFF
        {0xffffffff00017802ULL, 0x001fca0000000f00ULL},  // MOV R1, 0xFFFFFFFF
        {0x2001000047faeULL, 0xfe2000b9a00ffULL},  // LDGSTS.E.32 R4, 0x20, [{R0,R1}+URZ+0x10] (RR64U)
        {0x794dULL, 0xfea0003800000ULL},   // EXIT
    };

}  // namespace

// Profiler subscribes to the interpreter's raw stream for a shared-store
// kernel; shared-bank aggregation reports a broadcast write (1 pass, 31
// broadcasts, 0 conflicts).
TEST(profiler_shared_broadcast) {
    auto lk = load_kernel("_Z4ksts", kStsKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    opts.memory.shared_size = 1024;
    opts.model.l1tex = L1TexMode::kTraceOnly;
    auto r = Interpreter::run_result(lk.kernel, env, opts);
    CHECK(!r.fault.has_value());
    if (r.fault) return;

    MemoryProfiler prof("ksts", 1);
    prof.add_events(r.memory_events);
    auto rep = prof.report();
    CHECK(rep.schema_version == kReportSchemaVersion);
    bool found = false;
    for (const auto& e : rep.aggregate) {
        if (e.space != "shared") continue;
        CHECK(e.events == 1);
        CHECK(e.shared_passes == 1);
        CHECK(e.shared_conflicts == 0);
        CHECK(e.shared_broadcasts == 31);
        found = true;
    }
    CHECK(found);
}

// Global store kernel: 32 contiguous 4-B stores -> 1 line, 4 sectors, 1
// data-bank pass, tag-bank 1 pass, useful==requested==128.
TEST(profiler_global_contiguous) {
    auto lk = load_kernel("_Z4kstg", kStgKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(4096, 0);
    RunOptions opts;
    opts.memory.global = &global;
    opts.model.l1tex = L1TexMode::kTraceOnly;
    auto r = Interpreter::run_result(lk.kernel, env, opts);
    CHECK(!r.fault.has_value());
    if (r.fault) return;

    MemoryProfiler prof("kstg", 1);
    prof.add_events(r.memory_events);
    auto rep = prof.report();
    bool found = false;
    for (const auto& e : rep.aggregate) {
        if (e.space != "global") continue;
        CHECK(e.events == 1);
        CHECK(e.lane_requested_bytes == 128);
        CHECK(e.unique_useful_bytes == 128);
        CHECK(e.duplicate_reuse_bytes == 0);
        CHECK(e.sector_fetch_bytes == 4 * 32);
        CHECK(e.sector_overfetch_bytes == 0);
        CHECK(e.line_fill_bytes == 128);
        CHECK(e.data_bank_passes == 1);
        CHECK(e.data_bank_conflicts == 0);
        CHECK(e.tag_bank_passes == 1);
        found = true;
    }
    CHECK(found);

    // L1TEX hierarchy: 1 SM, 4 subcores, per-subcore serialization + SM-wide
    // sector/line merging.  The whole warp maps to one subcore (warp%4).
    CHECK(rep.l1tex_per_sm.size() == 1);
    if (!rep.l1tex_per_sm.empty()) {
        const auto& sm = rep.l1tex_per_sm[0];
        CHECK(sm.sm_id == 0);
        CHECK(sm.subcore_mapper == kL1TexMapperVersion);
        CHECK(sm.subcores.size() == 4);
        CHECK(sm.sectors.size() == 4);
        CHECK(sm.lines.size() == 1);
        std::uint64_t total = 0;
        for (const auto& sc : sm.subcores) total += sc.request_count;
        CHECK(total == 1);
    }
}

// Profiler on/off functional identity: the global buffer and all GPRs are
// byte-identical whether or not the event stream is collected.
TEST(profiler_on_off_functional_identity) {
    auto lk = load_kernel("_Z4kstg", kStgKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {2, 1, 1};
    std::vector<std::uint8_t> g_off(4096, 0), g_on(4096, 0);
    RunOptions off;
    off.memory.global = &g_off;
    auto r_off = Interpreter::run_result(lk.kernel, env, off);
    RunOptions on;
    on.memory.global = &g_on;
    on.model.l1tex = L1TexMode::kTraceOnly;
    auto r_on = Interpreter::run_result(lk.kernel, env, on);
    CHECK(!r_off.fault.has_value());
    CHECK(!r_on.fault.has_value());
    CHECK(g_off == g_on);
    CHECK(!r_on.memory_events.empty());
    CHECK(r_off.memory_events.empty());
    CHECK(r_off.ctas.size() == r_on.ctas.size());
    for (std::size_t c = 0; c < r_off.ctas.size(); ++c) {
        CHECK(r_off.ctas[c].warps.size() == r_on.ctas[c].warps.size());
        for (std::size_t w = 0; w < r_off.ctas[c].warps.size(); ++w) {
            for (int l = 0; l < 32; ++l) {
                for (int g = 0; g < kNumGprs; ++g) {
                    CHECK(r_off.ctas[c].warps[w].threads[l].gpr[g] ==
                          r_on.ctas[c].warps[w].threads[l].gpr[g]);
                }
            }
        }
    }
}

// LDGSTS aggregation: the coupled prediction event carries the raw goff/soff
// arrays; the profiler recomputes the extended counters and aggregates them
// under the "ldgsts" space, with confidence labels present.
TEST(profiler_ldgsts_aggregate) {
    auto lk = load_kernel("_Z5kldg", kLdgstsKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    opts.memory.shared_size = 1024;
    opts.model.l1tex = L1TexMode::kTraceOnly;
    auto r = Interpreter::run_result(lk.kernel, env, opts);
    // Functional LDGSTS: the copy completes and the coupled event is emitted.
    CHECK(!r.fault.has_value());

    MemoryProfiler prof("kldg", 1);
    prof.add_events(r.memory_events);
    auto rep = prof.report();
    bool found = false;
    for (const auto& e : rep.aggregate) {
        if (e.space != "ldgsts") continue;
        CHECK(e.events == 1);
        // goff[lane] = lane + 0x10 (0x10..0x2f), soff = 0x20 (from the test
        // kernel): bytes 0x10..0x2f cross the 32-B boundary -> sectors {0,1},
        // all in 128-B line 0 -> TWf 1.
        CHECK(e.ldgsts_twf == 1);
        CHECK(e.ldgsts_sectors == 2);
        CHECK(e.ldgsts_shared_wf > 0);
        // structured (constant source stride, full warp) -> exact-empirical.
        CHECK(e.confidence == "exact-empirical");
        found = true;
    }
    CHECK(found);
}

// L2 aggregate stays SEPARATE from L1/shared bank counters: with --l2 the
// report's L2 request/completion counts are populated and cross-SM contention
// is reported without merging into shared/global bank counts.
TEST(profiler_l2_separate_from_bank) {
    auto lk = load_kernel("_Z4kstg", kStgKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {4, 1, 1};
    std::vector<std::uint8_t> global(4096, 0);
    RunOptions opts;
    opts.memory.global = &global;
    opts.model.l1tex = L1TexMode::kTraceOnly;
    opts.model.l2 = L2Mode::kFunctionalEvents;
    opts.model.simulated_sm_count = 2;
    opts.model.deterministic_seed = 7;
    auto r = Interpreter::run_result(lk.kernel, env, opts);
    CHECK(!r.fault.has_value());
    if (r.fault) return;

    MemoryProfiler prof("kstg", 2);
    prof.add_events(r.memory_events);
    auto rep = prof.report();
    // L2 aggregate present.  Each lane issues one per-lane L2 descriptor; 32
    // lanes x 4 CTAs all land in 128-B sector 0 -> 128 requests / completions.
    CHECK(rep.l2.request_count == 128);
    CHECK(rep.l2.completion_count == 128);
    CHECK(rep.l2.requests_per_sm.size() == 2);
    // Shared/global bank entries never consume L2 counts.
    for (const auto& e : rep.aggregate) {
        CHECK(e.space != "l2");
        if (e.space == "shared") {
            // The STS kernel isn't used here, but a shared aggregate must
            // never carry L2 request counts.
            CHECK(e.events == 0);
        }
    }
}

// JSON schema version is stable and the report renders deterministically.
TEST(profiler_report_json_schema) {
    auto lk = load_kernel("_Z4kstg", kStgKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(4096, 0);
    RunOptions opts;
    opts.memory.global = &global;
    opts.model.l1tex = L1TexMode::kTraceOnly;
    auto r = Interpreter::run_result(lk.kernel, env, opts);
    MemoryProfiler prof("kstg", 1);
    prof.add_events(r.memory_events);
    auto rep = prof.report();
    const std::string j1 = rep.to_json();
    const std::string j2 = rep.to_json();
    CHECK(j1 == j2);  // deterministic
    CHECK(j1.find("\"schema_version\":\"1.0\"") != std::string::npos);
    CHECK(j1.find("\"l1tex\":{\"per_sm\":[") != std::string::npos);
    CHECK(j1.find("\"l2\":{") != std::string::npos);
    // Optional per-event trace is populated and emitted when requested.
    const std::string jt = rep.to_json(/*include_trace=*/true);
    CHECK(jt.find("\"events_trace\":[") != std::string::npos);
    CHECK(jt.find("\"mnemonic\":\"STG\"") != std::string::npos);
    const std::string txt = rep.to_text();
    CHECK(txt.find("profiler report") != std::string::npos);
}

// L2 aggregate is invariant to host worker ARRIVAL order: the same multiset
// of requests issued in different (shuffled) orders, drained under the same
// deterministic seed, produces an identical profiler L2 aggregate
// (request/completion counts, sectors, requests-per-SM, cross-SM contention)
// even though the raw event order may differ.
TEST(profiler_l2_shuffled_arrival_deterministic) {
    // Build a fixed multiset of global accesses across 4 SMs.  Addresses are
    // chosen so several sectors are shared across SMs (contention).
    struct Req { std::uint32_t sm; std::uint32_t sc; std::uint64_t addr; };
    const std::vector<Req> base = {
        {0, 0, 0x1000}, {1, 0, 0x1000}, {0, 1, 0x1040}, {1, 1, 0x2000},
        {2, 0, 0x1000}, {3, 0, 0x1040}, {2, 1, 0x3000}, {3, 1, 0x1000},
        {0, 2, 0x4000}, {1, 2, 0x4000}, {2, 2, 0x5000}, {3, 2, 0x5000},
    };
    // Two different arrival orders (permutations) of the same multiset.
    std::vector<Req> a = base;
    std::vector<Req> b = base;
    std::reverse(b.begin(), b.end());
    for (std::size_t i = 0; i + 1 < b.size(); i += 3) std::swap(b[i], b[i + 1]);

    auto run_order = [](const std::vector<Req>& order, std::uint64_t seed) {
        L2EventEngine eng(4, seed);
        std::uint64_t instr = 1;
        for (const auto& r : order) {
            eng.issue_global(r.sm, r.sc, 0, 0, 0x100, instr, instr + 100,
                             "LDG", "load", r.addr, 4);
            ++instr;
        }
        eng.drain_completions();
        profiler::MemoryProfiler prof("k", 4);
        prof.add_events(eng.events());
        return prof.report();
    };

    for (std::uint64_t seed : {0ULL, 42ULL}) {
        auto ra = run_order(a, seed);
        auto rb = run_order(b, seed);
        CHECK(ra.l2.request_count == rb.l2.request_count);
        CHECK(ra.l2.completion_count == rb.l2.completion_count);
        CHECK(ra.l2.sectors == rb.l2.sectors);
        CHECK(ra.l2.requests_per_sm == rb.l2.requests_per_sm);
        CHECK(ra.l2.cross_sm_sector_contention ==
              rb.l2.cross_sm_sector_contention);
    }
    // Sanity: the multiset really exercises cross-SM contention.
    auto r = run_order(a, 0);
    CHECK(r.l2.cross_sm_sector_contention >= 1);
}

// L1TEX hierarchy: single-flow results are invariant under different
// interleavings (arrangements) of the four subcore-ordered streams, and the
// per-subcore serialization (ticks are strictly increasing per subcore) is
// preserved regardless of host-side event-list order.
TEST(profiler_l1tex_subcore_arrangement_invariant) {
    // Four subcores each issuing three global accesses.  Stream A interleaves
    // subcores round-robin; stream B is the same multiset in a shuffled order.
    MemoryEvent base;
    base.kind = MemoryEventKind::kL1TexIssue;
    base.address_space = EventAddressSpace::kGlobal;
    base.element_width = 4;
    base.mnemonic = "LDG";
    base.pc = 0x20;

    std::vector<MemoryEvent> a, b;
    const std::uint64_t bases[4] = {0x1000, 0x1040, 0x2000, 0x2040};
    // subcore s, issue k -> event with tick (s*10 + k).  Build stream A
    // interleaved by tick; stream B interleaved differently.
    std::vector<MemoryEvent> all;
    for (std::uint32_t s = 0; s < 4; ++s) {
        for (std::uint32_t k = 0; k < 3; ++k) {
            MemoryEvent e = base;
            e.sm = 0;
            e.subcore = s;
            e.issue_tick = s * 10 + k;
            e.event_id = s * 10 + k;
            e.lane_ranges.resize(32);
            e.lane_ranges[0] = {bases[s] + k * 4, 4, true};
            e.active_mask = 1;
            all.push_back(e);
        }
    }
    // Arrangement A: ascending tick.  Arrangement B: reverse order.
    a = all;
    std::sort(a.begin(), a.end(),
              [](const MemoryEvent& x, const MemoryEvent& y) {
                  return x.issue_tick < y.issue_tick;
              });
    b = all;
    std::reverse(b.begin(), b.end());

    auto summarize = [](const std::vector<MemoryEvent>& evs) {
        profiler::MemoryProfiler prof("k", 1);
        prof.add_events(evs);
        auto rep = prof.report();
        std::string out;
        for (const auto& sm : rep.l1tex_per_sm) {
            out += "sm" + std::to_string(sm.sm_id) + ":" +
                   std::to_string(sm.event_count) + ":";
            for (const auto& sc : sm.subcores) {
                out += "sc" + std::to_string(sc.subcore_id) + "(" +
                       std::to_string(sc.request_count) + "," +
                       std::to_string(sc.first_tick) + "," +
                       std::to_string(sc.last_tick) + ");";
            }
            out += "sec" + std::to_string(sm.sectors.size()) + ";";
        }
        return out;
    };

    const std::string sa = summarize(a);
    const std::string sb = summarize(b);
    CHECK(sa == sb);  // single-flow result invariant to stream arrangement
    CHECK(sa.find("sc0(3,") != std::string::npos);
    CHECK(sa.find("sc1(3,") != std::string::npos);
    CHECK(sa.find("sc2(3,") != std::string::npos);
    CHECK(sa.find("sc3(3,") != std::string::npos);
    // Cross-stream arbitration note: the policy is deterministic and reported.
    CHECK(sa.find("sec") != std::string::npos);
}

// Blocker-1: the L1TEX miss/bypass model must consume the DETERMINISTIC
// ARBITRATED order, not the raw host event order.  Two subcores touching the
// SAME 128-B line: the compulsory miss is attributed to the subcore that wins
// arbitration (lowest issue tick), and the attribution must be identical under
// any event-list arrangement.
TEST(profiler_l1tex_miss_attribution_arrangement_invariant) {
    MemoryEvent base;
    base.kind = MemoryEventKind::kL1TexIssue;
    base.address_space = EventAddressSpace::kGlobal;
    base.element_width = 4;
    base.mnemonic = "LDG";
    base.pc = 0x20;
    base.sm = 0;
    base.variant_class = "ldg__sImmOffset";
    base.cache_policy = "default";

    // subcore 0 issues at tick 0, subcore 1 at tick 1; BOTH touch line 0x20.
    MemoryEvent e0 = base;
    e0.subcore = 0; e0.issue_tick = 0; e0.event_id = 0;
    e0.lane_ranges.resize(32); e0.lane_ranges[0] = {0x1000, 4, true};
    e0.active_mask = 1;
    MemoryEvent e1 = base;
    e1.subcore = 1; e1.issue_tick = 1; e1.event_id = 1;
    e1.lane_ranges.resize(32); e1.lane_ranges[0] = {0x1004, 4, true};
    e1.active_mask = 1;

    std::vector<MemoryEvent> a = {e0, e1};  // natural order
    std::vector<MemoryEvent> b = {e1, e0};  // reversed arrangement

    auto summarize = [](const std::vector<MemoryEvent>& evs) {
        MemoryProfiler prof("k", 1);
        prof.add_events(evs);
        auto rep = prof.report();
        // Per-SUBCORE-ID miss tally (unused subcores keep subcore_id=0 by
        // default, so tally by the id each entry reports).
        std::uint64_t m[4] = {0, 0, 0, 0};
        for (const auto& sm : rep.l1tex_per_sm) {
            for (const auto& sc : sm.subcores) {
                m[sc.subcore_id % 4] += sc.misses;
            }
        }
        std::string out;
        for (int s = 0; s < 4; ++s) out += "sc" + std::to_string(s) + ":" +
                                            std::to_string(m[s]) + ";";
        return out;
    };

    const std::string sa = summarize(a);
    const std::string sb = summarize(b);
    CHECK(sa == sb);  // miss attribution is arrangement-invariant
    // subcore 0 wins arbitration (tick 0) -> it owns the compulsory miss;
    // subcore 1's access to the now-resident line is a hit.
    CHECK(sa == "sc0:1;sc1:0;sc2:0;sc3:0;");
}

// Blocker-2: the LDGSTS cache-policy contract end-to-end.  A real interpreter
// LDGSTS.E.BYPASS.128 (the .cg / L1-bypass path) event flows into the
// profiler JSON carrying cache_policy "cg", variant class, and DEGRADED
// confidence (SharedWf + conflicts -> unsupported; pure counts stay
// exact-empirical), kept SEPARATE from the default-policy entry.
TEST(profiler_ldgsts_cg_bypass_negative) {
    auto lk = load_kernel("_Z6kldgb", kLdgstsBypassKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    opts.memory.shared_size = 1024;
    opts.model.l1tex = L1TexMode::kTraceOnly;

    auto r = Interpreter::run_result(lk.kernel, env, opts);
    CHECK(!r.fault.has_value());  // functional LDGSTS (Phase 9)

    MemoryProfiler prof("kldgb", 1);
    prof.add_events(r.memory_events);
    auto rep = prof.report();
    bool found = false;
    for (const auto& e : rep.aggregate) {
        if (e.space != "ldgsts") continue;
        CHECK(e.cache_policy == "cg");
        CHECK(e.variant == "ldgsts__RR32U");
        CHECK(e.confidence == "unsupported");                  // SharedWf
        CHECK(e.ldgsts_conflict_confidence == "unsupported");  // Shared/GlobalConf
        CHECK(e.ldgsts_count_confidence == "exact-empirical"); // TWf/TSetAcc/Sectors
        CHECK(!e.ldgsts_applicability.empty());
        CHECK(e.ldgsts_model_version == "unified-v1");
        found = true;
    }
    CHECK(found);

    // Contrast: the DEFAULT-policy LDGSTS path stays exact-empirical, and both
    // policies coexist as separate aggregate entries in one report (the policy
    // is part of the aggregate key).
    auto lk2 = load_kernel("_Z5kldg", kLdgstsKernel);
    if (lk2.kernel.symbol_name.empty()) return;
    auto r2 = Interpreter::run_result(lk2.kernel, env, opts);
    MemoryProfiler prof3("k", 1);
    prof3.add_events(r.memory_events);
    prof3.add_events(r2.memory_events);
    auto rep3 = prof3.report();
    int n_cg = 0, n_default = 0;
    for (const auto& e : rep3.aggregate) {
        if (e.space != "ldgsts") continue;
        if (e.cache_policy == "cg") {
            n_cg++;
            CHECK(e.confidence == "unsupported");
        }
        if (e.cache_policy == "default") {
            n_default++;
            CHECK(e.confidence == "exact-empirical");
        }
    }
    CHECK(n_cg == 1 && n_default == 1);
    // The policy contract is visible in the JSON schema.
    CHECK(rep3.to_json().find("\"cache_policy\":\"cg\"") != std::string::npos);
    CHECK(rep3.to_json().find("\"ldgsts_tag_conf\"") != std::string::npos);
    CHECK(rep3.to_json().find("\"ldgsts_tset_acc\"") != std::string::npos);
    CHECK(rep3.to_json().find("\"ldgsts_count_confidence\"") != std::string::npos);
}

// Round-2 B1: .cg / L1-bypass MUST NOT pollute the L1 resident-line state.
// A bypassed line is recorded as a bypass (count + reason) and never becomes
// resident, so a LATER default-policy access to the SAME line is still a
// compulsory miss.  The attribution is identical under reversed event
// arrangements and across different subcores.
TEST(profiler_l1tex_cg_bypass_does_not_pollute_resident) {
    auto ldgsts_cg = [](std::uint32_t subcore, std::uint64_t tick,
                        std::uint64_t id) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL1TexIssue;
        e.coupled_l1_to_shared = true;
        e.address_space = EventAddressSpace::kGlobal;
        e.element_width = 4;
        e.mnemonic = "LDGSTS";
        e.pc = 0x20;
        e.sm = 0;
        e.subcore = subcore;
        e.issue_tick = tick;
        e.event_id = id;
        e.variant_class = "ldgsts__RR32U";
        e.cache_policy = "cg";
        e.miss_path = "l1-bypass";
        e.prediction = true;
        e.active_mask = 0xffffffffu;
        for (int l = 0; l < 32; ++l) {
            e.ldgsts_goff.push_back(0x1000);  // line 0x1000/128 == 0x20
            e.ldgsts_soff.push_back(0);
        }
        return e;
    };
    auto ldg_default = [](std::uint32_t subcore, std::uint64_t tick,
                          std::uint64_t id) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL1TexIssue;
        e.address_space = EventAddressSpace::kGlobal;
        e.element_width = 4;
        e.mnemonic = "LDG";
        e.pc = 0x20;
        e.sm = 0;
        e.subcore = subcore;
        e.issue_tick = tick;
        e.event_id = id;
        e.variant_class = "ldg__sImmOffset";
        e.cache_policy = "default";
        e.miss_path = "l1-access";
        e.lane_ranges.resize(32);
        e.lane_ranges[0] = {0x1000, 4, true};  // the same 128-B line 0x20
        e.active_mask = 1;
        return e;
    };

    MemoryEvent cg0 = ldgsts_cg(0, 0, 0);   // .cg on subcore 0, tick 0
    MemoryEvent df1 = ldg_default(1, 1, 1); // default on subcore 1, tick 1

    auto summarize = [](const std::vector<MemoryEvent>& evs) {
        MemoryProfiler prof("k", 1);
        prof.add_events(evs);
        auto rep = prof.report();
        std::uint64_t misses[4] = {}, bypasses[4] = {};
        for (const auto& sm : rep.l1tex_per_sm) {
            for (const auto& sc : sm.subcores) {
                misses[sc.subcore_id % 4] += sc.misses;
                bypasses[sc.subcore_id % 4] += sc.bypasses;
            }
        }
        std::string out;
        for (int s = 0; s < 4; ++s) {
            out += "sc" + std::to_string(s) + ":m" +
                   std::to_string(misses[s]) + ":b" +
                   std::to_string(bypasses[s]) + ";";
        }
        return out;
    };

    // Natural [cg, default] and reversed [default, cg] arrangements give the
    // same L1 resident/attribution state (pass 2 uses the arbitrated order).
    const std::string sa = summarize({cg0, df1});
    const std::string sb = summarize({df1, cg0});
    CHECK(sa == sb);
    // The .cg access (subcore 0) is a pure bypass (0 misses).  The DEFAULT
    // access to the SAME line (subcore 1) is still a compulsory miss: the
    // bypass never made the line resident.
    CHECK(sa == "sc0:m0:b1;sc1:m1:b0;sc2:m0:b0;sc3:m0:b0;");

    // Same-subcore contrast: two consecutive .cg accesses to one line are
    // BOTH bypasses (still no resident), and a subsequent default access to
    // that line is still a compulsory miss.
    MemoryEvent cg2 = ldgsts_cg(0, 2, 2);
    MemoryEvent df2 = ldg_default(0, 3, 3);
    const std::string sc_ = summarize({cg0, cg2, df2});
    CHECK(sc_ == "sc0:m1:b2;sc1:m0:b0;sc2:m0:b0;sc3:m0:b0;");

    // The bypass reason is surfaced in the JSON schema.
    std::string j = summarize({cg0, df1});
    (void)j;
    MemoryProfiler prof("k", 1);
    prof.add_events({cg0, df1});
    auto rep = prof.report();
    CHECK(rep.to_json().find("\"bypasses\":1") != std::string::npos);
    CHECK(rep.to_json().find("\"bypass_reasons\":[\"l1-bypass(policy=cg line32)\"]") !=
          std::string::npos);
}

// Round-2 H1: the interpreter sets `prediction=false` when the LDGSTS address
// computation overflows / a lane is invalid (record_coupled_l1_to_shared at
// interpreter.cpp ~2898).  The profiler MUST consume that flag: the LDGSTS
// event is still aggregated but every model field is marked unsupported, no
// fabricated counts are accumulated, and prediction_unavailable_events is
// bumped.  End-to-end: a kernel whose 64-bit global source pair makes g +
// Ra_offset overflow 2^64 for every active lane.
TEST(profiler_ldgsts_prediction_unavailable_overflow) {
    auto lk = load_kernel("_Z7kldgofl", kLdgstsOverflowKernel);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    opts.memory.shared_size = 1024;
    opts.model.l1tex = L1TexMode::kTraceOnly;
    auto r = Interpreter::run_result(lk.kernel, env, opts);
    // The overflow excludes every lane from the functional copy (no global
    // read / shared write happens) and from the prediction; the run completes
    // cleanly.
    CHECK(!r.fault.has_value());

    // The raw event really is prediction-unavailable (overflow excludes every
    // lane from goff_valid_mask).
    bool found_raw = false;
    for (const auto& ev : r.memory_events) {
        if (ev.kind == MemoryEventKind::kL1TexIssue && ev.coupled_l1_to_shared) {
            CHECK(!ev.prediction);
            CHECK(ev.active_mask == 0);  // no valid prediction lane
            found_raw = true;
        }
    }
    CHECK(found_raw);

    MemoryProfiler prof("kldgofl", 1);
    prof.add_events(r.memory_events);
    auto rep = prof.report();
    bool found = false;
    for (const auto& e : rep.aggregate) {
        if (e.space != "ldgsts") continue;
        CHECK(e.events == 1);
        CHECK(e.prediction_unavailable_events == 1);
        // No fabricated numbers: every count stays zero.
        CHECK(e.ldgsts_shared_wf == 0 && e.ldgsts_shared_conf == 0 &&
              e.ldgsts_global_conf == 0 && e.ldgsts_twf == 0 &&
              e.ldgsts_tag_conf == 0 && e.ldgsts_tset_acc == 0 &&
              e.ldgsts_sectors == 0);
        // All LDGSTS fields unsupported.
        CHECK(e.confidence == "unsupported");
        CHECK(e.ldgsts_count_confidence == "unsupported");
        CHECK(e.ldgsts_conflict_confidence == "unsupported");
        CHECK(e.ldgsts_applicability.find("prediction-unavailable") !=
              std::string::npos);
        CHECK(e.ldgsts_model_version == "unified-v1");
        found = true;
    }
    CHECK(found);
    // The counter is visible in the JSON.
    CHECK(rep.to_json().find("\"prediction_unavailable_events\":1") !=
          std::string::npos);
}

// Round-2 H1 (direct): a coupled event constructed with prediction=false is
// consumed the same way at the profiler level — aggregated, not counted.
TEST(profiler_ldgsts_prediction_unavailable_direct) {
    MemoryEvent ev;
    ev.kind = MemoryEventKind::kL1TexIssue;
    ev.coupled_l1_to_shared = true;
    ev.address_space = EventAddressSpace::kGlobal;
    ev.element_width = 4;
    ev.mnemonic = "LDGSTS";
    ev.pc = 0x20;
    ev.sm = 0;
    ev.subcore = 0;
    ev.issue_tick = 0;
    ev.event_id = 0;
    ev.variant_class = "ldgsts__RR64U";
    ev.cache_policy = "default";
    ev.miss_path = "l1-access";
    ev.prediction = false;  // prediction unavailable
    ev.model_version = semu::l1tex::kUnifiedModelVersion;
    ev.active_mask = 0;
    for (int l = 0; l < 32; ++l) {
        ev.ldgsts_goff.push_back(0);
        ev.ldgsts_soff.push_back(0);
    }
    MemoryProfiler prof("k", 1);
    prof.add_events({ev});
    auto rep = prof.report();
    bool found = false;
    for (const auto& e : rep.aggregate) {
        if (e.space != "ldgsts") continue;
        CHECK(e.events == 1);
        CHECK(e.prediction_unavailable_events == 1);
        CHECK(e.ldgsts_twf == 0 && e.ldgsts_sectors == 0);
        CHECK(e.confidence == "unsupported");
        CHECK(e.ldgsts_count_confidence == "unsupported");
        CHECK(e.ldgsts_conflict_confidence == "unsupported");
        found = true;
    }
    CHECK(found);
}

// Round-3 B1: a coupled LDGSTS event whose prediction is UNAVAILABLE (the
// interpreter leaves goff/soff as invalid placeholder zeros) must never feed
// ANY L1 line/sector/cache-state modeling — NOT even into the resident-line
// set.  The access is counted + reasoned as prediction_unavailable, but its
// placeholder line 0 must NOT become resident, so a LATER valid default-policy
// access to line 0 is still a compulsory miss (if the placeholder had become
// resident, the real access would be misclassified as a hit).  The attribution
// is identical under reversed event arrangements and across subcores.
TEST(profiler_l1tex_prediction_unavailable_does_not_pollute_resident) {
    auto ldgsts_nopred = [](std::uint32_t subcore, std::uint64_t tick,
                            std::uint64_t id) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL1TexIssue;
        e.coupled_l1_to_shared = true;
        e.address_space = EventAddressSpace::kGlobal;
        e.element_width = 4;
        e.mnemonic = "LDGSTS";
        e.pc = 0x20;
        e.sm = 0;
        e.subcore = subcore;
        e.issue_tick = tick;
        e.event_id = id;
        e.variant_class = "ldgsts__RR64U";
        e.cache_policy = "default";
        e.miss_path = "l1-access";
        e.prediction = false;  // prediction unavailable
        e.model_version = semu::l1tex::kUnifiedModelVersion;
        e.active_mask = 0;     // no valid prediction lane
        for (int l = 0; l < 32; ++l) {
            // INVALID placeholder offsets (address computation overflow):
            // must NEVER be modeled as resident line 0 / sector 0.
            e.ldgsts_goff.push_back(0);
            e.ldgsts_soff.push_back(0);
        }
        return e;
    };
    auto ldg_default_line0 = [](std::uint32_t subcore, std::uint64_t tick,
                                std::uint64_t id) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL1TexIssue;
        e.address_space = EventAddressSpace::kGlobal;
        e.element_width = 4;
        e.mnemonic = "LDG";
        e.pc = 0x20;
        e.sm = 0;
        e.subcore = subcore;
        e.issue_tick = tick;
        e.event_id = id;
        e.variant_class = "ldg__sImmOffset";
        e.cache_policy = "default";
        e.miss_path = "l1-access";
        e.lane_ranges.resize(32);
        e.lane_ranges[0] = {0x0, 4, true};  // the same 128-B line 0 (0x0..0x3)
        e.active_mask = 1;
        return e;
    };

    // Invalid LDGSTS on subcore 0 (tick 0) whose placeholder would be line 0;
    // then a REAL default access to line 0 on subcore 1 (tick 1).
    MemoryEvent nopred0 = ldgsts_nopred(0, 0, 0);
    MemoryEvent df1 = ldg_default_line0(1, 1, 1);

    auto summarize = [](const std::vector<MemoryEvent>& evs) {
        MemoryProfiler prof("k", 1);
        prof.add_events(evs);
        auto rep = prof.report();
        // Tally per SUBCORE id (unused subcores keep all-zero summaries).
        std::uint64_t m[4] = {}, b[4] = {}, n[4] = {}, lc[4] = {};
        for (const auto& sme : rep.l1tex_per_sm) {
            for (const auto& sc : sme.subcores) {
                const std::uint32_t s = sc.subcore_id % 4;
                m[s] += sc.misses;
                b[s] += sc.bypasses;
                n[s] += sc.prediction_unavailable;
                lc[s] += sc.lines.size();
            }
        }
        std::ostringstream o;
        for (int s = 0; s < 4; ++s) {
            o << "sc" << s << ":m" << m[s] << ":b" << b[s] << ":n" << n[s]
              << ":L" << lc[s] << ";";
        }
        return o.str();
    };

    // Natural [nopred, default] and reversed [default, nopred] arrangements:
    // identical L1 resident/attribution state (pass 2 uses the arbitrated
    // order).
    const std::string sa = summarize({nopred0, df1});
    const std::string sb = summarize({df1, nopred0});
    CHECK(sa == sb);
    // The invalid event (subcore 0) is counted as prediction_unavailable (n1),
    // NEVER as a miss/bypass, and recorded NO line (L0).  The valid default
    // access on subcore 1 is still a compulsory miss on line 0 (m1, line
    // recorded once) — the placeholder never became resident.
    CHECK(sa == "sc0:m0:b0:n1:L0;sc1:m1:b0:n0:L1;sc2:m0:b0:n0:L0;sc3:m0:b0:n0:L0;");

    // Same-subcore contrast: two consecutive invalid events (tick 0, tick 2)
    // and then a REAL default access to line 0 on the same subcore (tick 3).
    // The invalid events never pollute; the real access is still a compulsory
    // miss (m1, n2, line recorded exactly once).
    MemoryEvent nopred2 = ldgsts_nopred(0, 2, 2);
    MemoryEvent df0 = ldg_default_line0(0, 3, 3);
    const std::string sc_ = summarize({nopred0, nopred2, df0});
    CHECK(sc_ == "sc0:m1:b0:n2:L1;sc1:m0:b0:n0:L0;sc2:m0:b0:n0:L0;sc3:m0:b0:n0:L0;");

    // Detailed per-subcore accounting on the canonical arrangement.
    MemoryProfiler prof("k", 1);
    prof.add_events({nopred0, df1});
    auto rep = prof.report();
    CHECK(rep.l1tex_per_sm.size() == 1);
    if (!rep.l1tex_per_sm.empty()) {
        const auto& sme = rep.l1tex_per_sm[0];
        const auto& sub0 = sme.subcores[0];
        const auto& sub1 = sme.subcores[1];
        CHECK(sub0.prediction_unavailable == 1);
        CHECK(sub0.misses == 0 && sub0.bypasses == 0);
        CHECK(!sub0.prediction_unavailable_reasons.empty());
        bool line0_in_sub0 = false;
        for (auto ln : sub0.lines) line0_in_sub0 = line0_in_sub0 || (ln == 0);
        CHECK(!line0_in_sub0);  // placeholder line 0 was never modeled
        bool line0_in_sm = false;
        for (auto ln : sme.lines) line0_in_sm = line0_in_sm || (ln == 0);
        CHECK(line0_in_sm);  // only the REAL default access made line 0 known
        CHECK(sub1.misses == 1);
    }
    // The prediction-unavailable accounting + reason is surfaced in the JSON.
    const std::string j = rep.to_json();
    CHECK(j.find("\"prediction_unavailable\":1") != std::string::npos);
    CHECK(j.find("prediction-unavailable(no-l1-model sm0 subcore0)") !=
          std::string::npos);
    CHECK(j.find("\"prediction_unavailable_reasons\":[\"prediction-unavailable(no-l1-model sm0 subcore0)\"]") !=
          std::string::npos);
}

// High-3: aggregate entries split by variant class (same mnemonic+pc, two
// encoding classes) and the L2 report carries atomic serialization metrics.
TEST(profiler_variant_aggregation_and_atomic_chain) {
    MemoryEvent a;
    a.kind = MemoryEventKind::kL1TexIssue;
    a.address_space = EventAddressSpace::kGlobal;
    a.element_width = 4; a.mnemonic = "LDG"; a.pc = 0x40; a.sm = 0;
    a.subcore = 0; a.issue_tick = 0; a.event_id = 0;
    a.variant_class = "ldg__sImmOffset"; a.cache_policy = "default";
    a.lane_ranges.resize(32); a.lane_ranges[0] = {0x1000, 4, true};
    a.active_mask = 1;

    MemoryEvent b = a;
    b.variant_class = "ldg__uImmOffset"; b.issue_tick = 1; b.event_id = 1;
    b.lane_ranges[0] = {0x2000, 4, true};

    MemoryProfiler prof("k", 1);
    prof.add_events({a, b});
    auto rep = prof.report();
    int n_ldg = 0;
    bool saw_a = false, saw_b = false;
    for (const auto& e : rep.aggregate) {
        if (e.space != "global") continue;
        n_ldg++;
        if (e.variant == "ldg__sImmOffset") saw_a = true;
        if (e.variant == "ldg__uImmOffset") saw_b = true;
        CHECK(e.events == 1);
        CHECK(rep.to_json().find("\"variant\":\"ldg__") != std::string::npos);
    }
    CHECK(n_ldg == 2);  // two separate variant entries
    CHECK(saw_a && saw_b);

    // High-4: atomic serialization chain — two atomics on the same sector
    // serialize at L2 (one chain), with valid one-to-one completion edges.
    MemoryEvent ar1, ar2;
    ar1.kind = MemoryEventKind::kL2Request;
    ar1.event_id = 20; ar1.request_id = 1; ar1.sector = 0x20;
    ar1.request_kind = "atomic"; ar1.sm = 0; ar1.subcore = 0;
    ar1.parent_event_id = 200; ar1.mnemonic = "ATOM";
    ar2 = ar1; ar2.event_id = 21; ar2.request_id = 2;
    MemoryEvent ac1, ac2;
    ac1.kind = MemoryEventKind::kL2Completion;
    ac1.event_id = 22; ac1.request_id = 1; ac1.parent_event_id = 200;
    ac1.sector = 0x20; ac1.sm = 0; ac1.subcore = 0;
    ac2 = ac1; ac2.event_id = 23; ac2.request_id = 2;
    MemoryProfiler prof2("k", 1);
    prof2.add_events({ar1, ar2, ac1, ac2});
    auto rep2 = prof2.report();
    CHECK(rep2.l2.atomic_requests == 2);
    CHECK(rep2.l2.atomic_serialization_chains == 1);
    CHECK(rep2.l2.completion_edges == 2);
    CHECK(rep2.l2.orphan_completions == 0);
    CHECK(rep2.l2.duplicate_completions == 0);
}

// High-4 negative tests: orphan and duplicate L2 completions are detected and
// reported, and a valid one-to-one edge is counted exactly once.
TEST(profiler_l2_orphan_duplicate_completions) {
    std::vector<MemoryEvent> evs;
    // One live request (request_id 1).
    MemoryEvent req;
    req.kind = MemoryEventKind::kL2Request;
    req.event_id = 10; req.request_id = 1; req.parent_event_id = 100;
    req.sector = 0x20; req.sm = 0; req.subcore = 0;
    req.request_kind = "load"; req.mnemonic = "LDG";
    evs.push_back(req);

    // Valid completion.
    MemoryEvent ok;
    ok.kind = MemoryEventKind::kL2Completion;
    ok.event_id = 11; ok.request_id = 1; ok.parent_event_id = 100;
    ok.sector = 0x20; ok.sm = 0; ok.subcore = 0;
    evs.push_back(ok);

    // Orphan: completion for a request that never existed.
    MemoryEvent orphan;
    orphan.kind = MemoryEventKind::kL2Completion;
    orphan.event_id = 12; orphan.request_id = 99; orphan.parent_event_id = 101;
    orphan.sector = 0x20; orphan.sm = 0; orphan.subcore = 0;
    evs.push_back(orphan);

    // Duplicate: the same request completed a second time.
    MemoryEvent dup = ok;
    dup.event_id = 13;
    evs.push_back(dup);

    // Parent-identity mismatch: completion references a DIFFERENT parent L1
    // event than the request it claims to complete.
    MemoryEvent wrong_parent = ok;
    wrong_parent.event_id = 14; wrong_parent.parent_event_id = 555;
    evs.push_back(wrong_parent);

    MemoryProfiler prof("k", 1);
    prof.add_events(evs);
    auto rep = prof.report();
    CHECK(rep.l2.completion_count == 4);
    CHECK(rep.l2.completion_edges == 1);
    CHECK(rep.l2.orphan_completions == 2);     // unknown id + parent mismatch
    CHECK(rep.l2.duplicate_completions == 1);
    const std::string j = rep.to_json();
    CHECK(j.find("\"completion_edges\":1") != std::string::npos);
    CHECK(j.find("\"orphan_completions\":2") != std::string::npos);
    CHECK(j.find("\"duplicate_completions\":1") != std::string::npos);
}

// Round-2 H3: a duplicate request id is a defect, and a completion must match
// the request's parent AND sector AND SM identity.  The duplicate request
// never overwrites the first; sector/SM identity mismatches are malformed.
TEST(profiler_l2_duplicate_request_and_identity) {
    std::vector<MemoryEvent> evs;
    // One live request (request_id 7, parent 100, sector 0x20, sm 0).
    MemoryEvent req;
    req.kind = MemoryEventKind::kL2Request;
    req.event_id = 10; req.request_id = 7; req.parent_event_id = 100;
    req.sector = 0x20; req.sm = 0; req.subcore = 0;
    req.request_kind = "load"; req.mnemonic = "LDG";
    evs.push_back(req);

    // DUPLICATE request id: same id 7, different parent/sector/sm.
    MemoryEvent req_dup = req;
    req_dup.event_id = 11; req_dup.parent_event_id = 200;
    req_dup.sector = 0x30; req_dup.sm = 1;
    evs.push_back(req_dup);

    // Valid completion for the FIRST request (identity matches).
    MemoryEvent ok;
    ok.kind = MemoryEventKind::kL2Completion;
    ok.event_id = 12; ok.request_id = 7; ok.parent_event_id = 100;
    ok.sector = 0x20; ok.sm = 0; ok.subcore = 0;
    evs.push_back(ok);

    // Sector mismatch: completion for request 7 but a DIFFERENT sector.
    MemoryEvent bad_sector = ok;
    bad_sector.event_id = 13; bad_sector.sector = 0x99;
    evs.push_back(bad_sector);

    // SM mismatch: completion for request 7 but a DIFFERENT SM.
    MemoryEvent bad_sm = ok;
    bad_sm.event_id = 14; bad_sm.sm = 3;
    evs.push_back(bad_sm);

    MemoryProfiler prof("k", 2);
    prof.add_events(evs);
    auto rep = prof.report();
    // Two request events, one duplicate.
    CHECK(rep.l2.request_count == 2);
    CHECK(rep.l2.duplicate_requests == 1);
    // Only the valid completion forms an edge; sector/SM mismatches are
    // orphaned (malformed), never counted twice.
    CHECK(rep.l2.completion_edges == 1);
    CHECK(rep.l2.orphan_completions == 2);
    CHECK(rep.l2.duplicate_completions == 0);
    const std::string j = rep.to_json();
    CHECK(j.find("\"duplicate_requests\":1") != std::string::npos);
}

// Round-2 H3: atomic serialization chains are built from EXPLICIT adjacent
// dependency edges in the deterministic L2 completion order.  The chain is
// invariant to the host event-list arrangement (permutations / out-of-order
// arrival), never crosses sectors, and only atomics with a validated
// completion are members.
TEST(profiler_l2_atomic_chain_edges_permutation_invariant) {
    auto areq = [](std::uint64_t id, std::uint64_t rid, std::uint64_t p,
                   std::uint64_t sector, std::uint32_t sm) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL2Request;
        e.event_id = id; e.request_id = rid; e.parent_event_id = p;
        e.sector = sector; e.sm = sm; e.subcore = 0;
        e.request_kind = "atomic"; e.mnemonic = "ATOM";
        return e;
    };
    auto acom = [](std::uint64_t id, std::uint64_t rid, std::uint64_t p,
                   std::uint64_t sector, std::uint32_t sm, std::uint64_t seq) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL2Completion;
        e.event_id = id; e.request_id = rid; e.parent_event_id = p;
        e.sector = sector; e.sm = sm; e.subcore = 0;
        e.request_kind = "atomic"; e.mnemonic = "ATOM";
        e.issue_tick = seq;  // deterministic L2 completion order
        return e;
    };

    // Sector 0x20: three atomics serializing in completion order 3,1,2.
    //   A(rid 1, parent 100, sector 0x20, sm 0)
    //   B(rid 2, parent 200, sector 0x20, sm 0)
    //   C(rid 3, parent 300, sector 0x20, sm 1)
    // Sector 0x40: one atomic (D) — never forms a chain (needs >=2).
    std::vector<MemoryEvent> base = {
        areq(10, 1, 100, 0x20, 0), areq(11, 2, 200, 0x20, 0),
        areq(12, 3, 300, 0x20, 1), areq(13, 4, 400, 0x40, 0),
        acom(20, 3, 300, 0x20, 1, 1),  // seq 1: C
        acom(21, 1, 100, 0x20, 0, 2),  // seq 2: A
        acom(22, 2, 200, 0x20, 0, 3),  // seq 3: B
        acom(23, 4, 400, 0x40, 0, 4),  // D completes alone
    };

    auto summarize = [](const std::vector<MemoryEvent>& evs) {
        MemoryProfiler prof("k", 4);
        prof.add_events(evs);
        auto rep = prof.report();
        std::ostringstream o;
        o << "chains=" << rep.l2.atomic_serialization_chains
          << ",edges=" << rep.l2.atomic_serialization_edges
          << ",requests=" << rep.l2.atomic_requests
          << ",completion_edges=" << rep.l2.completion_edges;
        return o.str();
    };

    // Same multiset, four different host arrangements (including reversed
    // requests + completions).  The chain is fully identical: one chain on
    // sector 0x20 (members ordered [3,1,2] by completion seq) => 2 edges;
    // sector 0x40 has a single atomic => no chain.
    std::vector<std::vector<MemoryEvent>> arrangements;
    arrangements.push_back(base);
    {
        auto v = base;
        std::reverse(v.begin(), v.end());
        arrangements.push_back(v);
    }
    {
        // Interleave: all requests first, then completions in shuffled order.
        std::vector<MemoryEvent> v;
        for (int i = 0; i < 8; i += 2) v.push_back(base[static_cast<std::size_t>(i)]);
        for (int i = 1; i < 8; i += 2) v.push_back(base[static_cast<std::size_t>(i)]);
        std::swap(v[4], v[7]);
        arrangements.push_back(v);
    }
    {
        // Out-of-order arrival: completions for odd seq delivered first.
        std::vector<MemoryEvent> v;
        v.push_back(base[4]);
        v.push_back(base[0]); v.push_back(base[1]); v.push_back(base[2]);
        v.push_back(base[3]);
        v.push_back(base[6]); v.push_back(base[5]); v.push_back(base[7]);
        arrangements.push_back(v);
    }
    const std::string canonical = summarize(arrangements[0]);
    for (const auto& arr : arrangements) {
        CHECK(summarize(arr) == canonical);
    }
    CHECK(canonical == "chains=1,edges=2,requests=4,completion_edges=4");

    // Cross-sector atomic safety: the sector 0x40 atomic must NOT be pulled
    // into the 0x20 chain (chains/edges stay 1/2), proven by the canonical
    // above.  Explicitly: even when completions are permuted the chain is
    // built from the completion seq carried on each event.
    const std::string j = summarize(base);
    (void)j;
    MemoryProfiler prof("k", 4);
    prof.add_events(base);
    auto rep = prof.report();
    CHECK(rep.to_json().find("\"atomic_serialization_chains\":1") !=
          std::string::npos);
    CHECK(rep.to_json().find("\"atomic_serialization_edges\":2") !=
          std::string::npos);
}

// Round-3 H1: the atomic serialization chain carries EXPLICIT edge identity —
// each edge's from/to request ids, the serialized sector and both deterministic
// L2 completion seqs — and the member sort is (completion_seq, request_id) so
// even equal completion seqs (a tie) order deterministically.  Assert the
// ACTUAL chain (C->A->B, three edges) instead of a bare count, invariant to the
// host event-list arrangement, and verify the edges render in the JSON.
TEST(profiler_l2_atomic_chain_edge_identity) {
    auto areq = [](std::uint64_t id, std::uint64_t rid, std::uint64_t p,
                   std::uint32_t sm) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL2Request;
        e.event_id = id; e.request_id = rid; e.parent_event_id = p;
        e.sector = 0x20; e.sm = sm; e.subcore = 0;
        e.request_kind = "atomic"; e.mnemonic = "ATOM";
        return e;
    };
    auto acom = [](std::uint64_t id, std::uint64_t rid, std::uint64_t p,
                   std::uint32_t sm, std::uint64_t seq) {
        MemoryEvent e;
        e.kind = MemoryEventKind::kL2Completion;
        e.event_id = id; e.request_id = rid; e.parent_event_id = p;
        e.sector = 0x20; e.sm = sm; e.subcore = 0;
        e.request_kind = "atomic"; e.mnemonic = "ATOM";
        e.issue_tick = seq;  // deterministic L2 completion order
        return e;
    };
    auto render = [](const ProfilerReport& rep) {
        std::ostringstream o;
        o << "chains=" << rep.l2.atomic_serialization_chains
          << ",edges=" << rep.l2.atomic_serialization_edges << ":";
        for (const auto& e : rep.l2.atomic_serialization_edges_list) {
            o << e.from_request_id << "->" << e.to_request_id << "@" << e.sector
              << "(seq" << e.from_seq << "->" << e.to_seq << ");";
        }
        return o.str();
    };
    auto summarize = [&](const std::vector<MemoryEvent>& evs) {
        MemoryProfiler prof("k", 1);
        prof.add_events(evs);
        return render(prof.report());
    };

    // Four atomics on sector 0x20 (A=rid1, B=rid2, C=rid3, D=rid4).  The
    // deterministic L2 completion order serializes them as C->A->B->D: C seq 1,
    // A seq 2, B seq 3, D seq 3 — B and D TIE on seq 3, so the
    // (completion_seq, request_id) tie-break must order rid2 before rid4.
    // Three adjacent dependency edges: C->A, A->B, B->D.
    std::vector<MemoryEvent> base = {
        areq(10, 1, 100, 0), areq(11, 2, 200, 0),
        areq(12, 3, 300, 1), areq(13, 4, 400, 1),
        acom(20, 3, 300, 1, 1),  // C seq 1
        acom(21, 1, 100, 0, 2),  // A seq 2
        acom(22, 2, 200, 0, 3),  // B seq 3
        acom(23, 4, 400, 1, 3),  // D seq 3 (tie with B)
    };
    const std::string canonical =
        "chains=1,edges=3:3->1@32(seq1->2);1->2@32(seq2->3);2->4@32(seq3->3);";
    CHECK(summarize(base) == canonical);

    // Arrangement invariance: the SAME multiset under different host event-list
    // orders must produce byte-identical edge identities (the chain is built
    // from the completion seq carried on each event, never host order).
    std::vector<std::vector<MemoryEvent>> arrangements;
    arrangements.push_back(base);
    {
        auto v = base;
        std::reverse(v.begin(), v.end());
        arrangements.push_back(v);
    }
    {
        // All requests first, then completions shuffled.
        std::vector<MemoryEvent> v;
        for (int i = 0; i < 8; i += 2) v.push_back(base[static_cast<std::size_t>(i)]);
        for (int i = 1; i < 8; i += 2) v.push_back(base[static_cast<std::size_t>(i)]);
        std::swap(v[6], v[7]);
        arrangements.push_back(v);
    }
    {
        // Completions arrive before their requests (legal out-of-order arrival).
        std::vector<MemoryEvent> v;
        for (int i = 4; i < 8; ++i) v.push_back(base[static_cast<std::size_t>(i)]);
        for (int i = 0; i < 4; ++i) v.push_back(base[static_cast<std::size_t>(i)]);
        arrangements.push_back(v);
    }
    for (const auto& arr : arrangements) {
        CHECK(summarize(arr) == canonical);
    }

    // The exact edge identities are rendered in the report JSON.
    MemoryProfiler prof("k", 1);
    prof.add_events(base);
    auto rep = prof.report();
    const std::string j = rep.to_json();
    CHECK(j.find("\"from_request_id\":3,\"to_request_id\":1") !=
          std::string::npos);
    CHECK(j.find("\"from_request_id\":1,\"to_request_id\":2") !=
          std::string::npos);
    CHECK(j.find("\"from_request_id\":2,\"to_request_id\":4") !=
          std::string::npos);
    // No request id in the sector 0x30 (never issued) ever becomes an edge.
    CHECK(j.find(":48(") == std::string::npos);

    // Sub-case: exactly the C->A->B chain with no tie — A,B,C serialized
    // C(seq1) A(seq2) B(seq3) => two explicit edges.
    std::vector<MemoryEvent> three = {
        areq(10, 1, 100, 0), areq(11, 2, 200, 0), areq(12, 3, 300, 1),
        acom(20, 3, 300, 1, 1),
        acom(21, 1, 100, 0, 2),
        acom(22, 2, 200, 0, 3),
    };
    CHECK(summarize(three) ==
          "chains=1,edges=2:3->1@32(seq1->2);1->2@32(seq2->3);");
    {
        auto v = three;
        std::reverse(v.begin(), v.end());
        CHECK(summarize(v) ==
              "chains=1,edges=2:3->1@32(seq1->2);1->2@32(seq2->3);");
    }
}

// Medium-2: JSON string escaping.  Kernel/mnemonic values with quotes,
// backslashes and control characters must not corrupt the report document.
TEST(profiler_json_escape_special_chars) {
    MemoryEvent a;
    a.kind = MemoryEventKind::kL1TexIssue;
    a.address_space = EventAddressSpace::kShared;
    a.element_width = 4; a.mnemonic = "ST\"S\n\\"; a.pc = 0x10; a.sm = 0;
    a.subcore = 0; a.issue_tick = 0; a.event_id = 0;
    a.variant_class = "sts__RR"; a.cache_policy = "default";
    a.lane_ranges.resize(32); a.lane_ranges[0] = {0, 4, true};
    a.active_mask = 1;

    MemoryProfiler prof("ke\"r\n\\nel", 1);
    prof.add_events({a});
    auto rep = prof.report();
    const std::string j = rep.to_json(/*include_trace=*/true);
    // Escaped round-trip values are present.
    CHECK(j.find("ke\\\"r\\n\\\\nel") != std::string::npos);
    CHECK(j.find("ST\\\"S\\n\\\\") != std::string::npos);
    // No raw newline leaks into the document (every '\n' in a string value is
    // the two-char escape sequence, never a literal line break).
    CHECK(j.find_first_of('\n') == std::string::npos);
    CHECK(j.find("\"kernel\":\"ke\\\"r\\n\\\\nel\"") != std::string::npos);
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-profiler");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu profiler tests\n");
    }
    return failures == 0 ? 0 : 1;
}
