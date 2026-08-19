// L4 unit tests: Phase 7 debug session (single-step debugger interface).
//
// Builds small sm120 kernels from pre-assembled words, runs them through
// DebugSession (single worker, deterministic stepping), and verifies:
//   step / continue / step_n; PC + mnemonic breakpoints with CTA / warp /
//   lane conditions; memory watchpoints (multi-lane, cross-boundary, atomic);
//   GPR / UR / predicate / PC / special-register / memory / barrier /
//   scoreboard view and modify; fault stop with state viewable; unsupported
//   instruction stops BEFORE execution; instruction limit; warp step focus;
//   step-N-then-continue == direct-continue; fully reproducible traces.

#include <semu/debugger.hpp>
#include <semu/interpreter.hpp>

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "test_framework.hpp"

using namespace semu;

namespace {

// Minimal hand-built cubin (mirrors test_interp.cpp).
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
    out.push_back(2); out.push_back(0);
    out.push_back(190); out.push_back(0);
    auto push16 = [&out](std::uint16_t v) {
        out.push_back(v & 0xff); out.push_back(v >> 8);
    };
    push32(&out, 1);
    push64(&out, 0);
    push64(&out, 0);
    push64(&out, shoff);
    push32(&out, 0x06007802);
    push16(64); push16(56); push16(0);
    push16(64);
    push16(static_cast<std::uint16_t>(secs.size()));
    push16(1);
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

struct LoadedKernel {
    std::vector<std::uint8_t> cubin;
    std::string kernel_name;
    Kernel kernel;
};

LoadedKernel load_kernel(const std::string& mangled,
                         const std::vector<std::pair<std::uint64_t,
                                                     std::uint64_t>>& words) {
    LoadedKernel lk;
    lk.cubin = build_kernel_cubin(mangled, words);
    lk.kernel_name = mangled;
    auto m = semu::Module::load(lk.cubin);
    if (m.failed()) {
        std::fprintf(stderr, "load: %s\n",
                     m.take_error().describe().c_str());
        return lk;
    }
    const Kernel* k = m.value().find_kernel(mangled);
    if (k) lk.kernel = *k;
    return lk;
}

// Pre-assembled sm120 words (assembler-verified).  S2R R0, TID.X ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kS2rExit = {
    {0x7919ULL, 0xe0a0000002100ULL},  // S2R R0, SR_TID.X
    {0x794dULL, 0xfea0003800000ULL},  // EXIT
};
// Divergence with a spin on the taken path: lanes < 16 branch to 0x50 and
// spin there; fall-through lanes run 0x30 then EXIT at 0x40.  The two PC
// groups never reconverge, so a breakpoint on 0x50 fires with exactly the
// taken-lane mask.
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kDivSpin = {
    {0x7919ULL, 0x10220000002100ULL},             // 0000 S2R R0, SR_TID.X
    {0x100000780cULL, 0x1fe40003f01070ULL},       // 0010 ISETP.LT.U32.AND P0,PT,R0,0x10,PT
    {0x80947ULL, 0x1fe60003800000ULL},            // 0020 @P0 BRA 0x50
    {0x1111111100017802ULL, 0x1fe80000000f00ULL}, // 0030 MOV32I R1, 0x11111111
    {0x794dULL, 0x1fea0003800000ULL},             // 0040 EXIT
    {0x2222222200027802ULL, 0x1fec0000000f00ULL}, // 0050 MOV32I R2, 0x22222222 (spin)
    {0xfffffffc00f87947ULL, 0x1fee000383ffffULL}, // 0060 BRA 0x50
};
// BRA loop (R2 counts to 5) — reuse from the interp suite.
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kLoop = {
    {0x7919ULL, 0xe0a0000002100ULL},          // 0000 S2R R0, SR_TID.X
    {0x500017802ULL, 0xfca0000000f00ULL},     // 0010 MOV32I R1, 0x5
    {0x27802ULL, 0xfca0000000f00ULL},         // 0020 MOV32I R2, 0x0
    {0x102027810ULL, 0x1fca0007ffe0ffULL},    // 0030 IADD3 R2, R2, 1, RZ
    {0x10200720cULL, 0x1fca0003f01070ULL},    // 0040 ISETP.LT.U32.AND P0,...
    {0xfffffffc00f40947ULL, 0xfea000383ffffULL},  // 0050 @P0 BRA loop
    {0x794dULL, 0xfea0003800000ULL},          // 0060 EXIT
};
// S2R ; MOV32I R1,5 ; IADD3 R2,R0,R1,RZ ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kAdd = {
    {0x7919ULL, 0x10220000002100ULL},          // 0000 S2R R0, SR_TID.X
    {0x500017802ULL, 0x1fe40000000f00ULL},     // 0010 MOV32I R1, 0x5
    {0x100027210ULL, 0x7fe60007ffe0ffULL},     // 0020 IADD3 R2, R0, R1, RZ
    {0x794dULL, 0x1fe80003800000ULL},          // 0030 EXIT
};
// S2R ; MUFU.RCP R1,R0 (decode-only, not implemented) ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kUnsupported = {
    {0x7919ULL, 0x10220000002100ULL},          // 0000 S2R R0, SR_TID.X
    {0x17308ULL, 0x3e120000001000ULL},         // 0010 MUFU.RCP R1, R0
    {0x794dULL, 0x1fec0003800000ULL},          // 0020 EXIT
};
// S2R ; ISETP.LT P0,R0,0x10 ; MOV32I R2 ; @P0 STG.E [R6.64+0x40],R2 ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kStgMask = {
    {0x7919ULL, 0x10220000002100ULL},          // 0000 S2R R0, SR_TID.X
    {0x100000780cULL, 0x1fe40003f01070ULL},    // 0010 ISETP.LT.U32.AND P0,PT,R0,0x10,PT
    {0xdeadbeef00027802ULL, 0x1fe60000000f00ULL},  // 0020 MOV32I R2, 0xDEADBEEF
    {0x400206000986ULL, 0x73ca000c101904ULL},  // 0030 @P0 STG.E [R6.64+0x40], R2
    {0x794dULL, 0x1fec0003800000ULL},          // 0040 EXIT
};
// MOV32I R0 ; MOV32I R1 ; STG.E.64 [R6.64+0x40],{R0,R1} ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kStg64 = {
    {0x1122334400007802ULL, 0x1fe20000000f00ULL},  // 0000 MOV32I R0, 0x11223344
    {0x5566778800017802ULL, 0x1fe20000000f00ULL},  // 0010 MOV32I R1, 0x55667788
    {0x400006007986ULL, 0xf3ca000c101b04ULL},      // 0020 STG.E.64 [R6.64+0x40], {R0,R1}
    {0x794dULL, 0x1fec0003800000ULL},              // 0030 EXIT
};
// MOV32I R2 ; ATOM.E.ADD.STRONG.GPU R3,[R6.64+0x40],R2 ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kAtom = {
    {0x100027802ULL, 0x1fe20000000f00ULL},     // 0000 MOV32I R2, 0x1
    {0x40020603738aULL, 0x3f5000001ee100ULL},  // 0010 ATOM.E.ADD.STRONG.GPU R3, [R6.64+0x40], R2
    {0x794dULL, 0x1fec0003800000ULL},          // 0020 EXIT
};
// MOV32I R0 ; STG.E [R6.64+0x40],R0 ; LDG.E R1,[R6.64+0x40] ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kStgLdg = {
    {0xaaaa555500007802ULL, 0x1fe20000000f00ULL},  // 0000 MOV32I R0, 0xAAAA5555
    {0x400006007986ULL, 0x33ca000c101904ULL},      // 0010 STG.E [R6.64+0x40], R0
    {0x400406017981ULL, 0x3e8a000c1e1900ULL},      // 0020 LDG.E R1, [R6.64+0x40]
    {0x794dULL, 0x1fec0003800000ULL},              // 0030 EXIT
};
// MOV32I R0 ; STG.E [R6.64+0x2000],R0 (OOB for a 0x100-byte buffer) ; EXIT
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kStgOob = {
    {0xdeadbeef00007802ULL, 0x1fe20000000f00ULL},  // 0000 MOV32I R0, 0xDEADBEEF
    {0x20000006007986ULL, 0x33ca000c101904ULL},    // 0010 STG.E [R6.64+0x2000], R0
    {0x794dULL, 0x1fec0003800000ULL},              // 0020 EXIT
};
// S2R R0,TID.X ; BAR.SYNC 0 ; EXIT — both warps of a 64-thread block must
// arrive at barrier 0 before either proceeds.
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kBarSync = {
    {0x7919ULL, 0xe0a0000002100ULL},       // 0000 S2R R0, SR_TID.X
    {0x7b1dULL, 0xfea0000000000ULL},       // 0010 BAR.SYNC 0
    {0x794dULL, 0xfea0003800000ULL},       // 0020 EXIT
};
// MOV32I R0 ; MOV32I R1 ; IADD3 R2,R0,R1 ; STG.E [R6.64+0x40],R2 ; EXIT
// (assembler-verified sm120 words; used by the mnemonic-breakpoint tests so a
// `break mnem STG` must NOT stop at the MOVs / IADD3).
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kMovIaddStg = {
    {0x123400007802ULL, 0xfc00000000f00ULL},  // 0000 MOV32I R0, 0x1234
    {0x500017802ULL, 0xfc00000000f00ULL},     // 0010 MOV32I R1, 0x5
    {0x100027210ULL, 0xfc00007ffe0ffULL},     // 0020 IADD3 R2, R0, R1, RZ
    {0x400206007986ULL, 0xfc0000c1019ffULL},  // 0030 STG.E [R6.64+0x40], R2
    {0x794dULL, 0xfc00003800000ULL},          // 0040 EXIT
};

// Compare the observable thread state of two results (GPR/pred/pc/exited).
bool state_equal(const std::vector<CtaState>& a, const std::vector<CtaState>& b) {
    if (a.size() != b.size()) return false;
    for (std::size_t c = 0; c < a.size(); ++c) {
        if (a[c].warps.size() != b[c].warps.size()) return false;
        for (std::size_t w = 0; w < a[c].warps.size(); ++w) {
            if (a[c].warps[w].done != b[c].warps[w].done) return false;
            for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                const auto& x = a[c].warps[w].threads[lane];
                const auto& y = b[c].warps[w].threads[lane];
                if (x.exited != y.exited || x.active != y.active ||
                    x.pc != y.pc) {
                    return false;
                }
                for (int r = 0; r < kNumGprs; ++r)
                    if (x.gpr[r] != y.gpr[r]) return false;
                for (int p = 0; p < 7; ++p)
                    if (x.pred[p] != y.pred[p]) return false;
            }
            for (int u = 0; u < kNumUrs; ++u)
                if (a[c].warps[w].ur[u] != b[c].warps[w].ur[u]) return false;
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// Basic stepping: kernel/CTA/warp/PC/active mask/decoded instruction/diff.
// ---------------------------------------------------------------------------

TEST(dbg_step_basic) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    DebugStepInfo a = s.step();
    CHECK(a.reason == DebugStopReason::kStepped);
    CHECK(a.kernel_name == "_Z3kex");
    CHECK(a.cta == 0 && a.warp == 0);
    CHECK(a.pc == 0x0);
    CHECK(a.active_mask == 0xffffffffu);
    CHECK(a.instruction.mnemonic == isa::Mnemonic::kS2R);
    // Register diff: R0 per lane set to TID.X, PC advanced.
    std::uint32_t lane0 = 0;
    CHECK(s.read_gpr(0, 0, 0, 0, &lane0).ok() && lane0 == 0);
    bool saw_r0 = false, saw_pc = false;
    for (const auto& d : a.reg_diffs) {
        if (d.kind == ChangeKind::kGpr && d.index == 0 && d.lane == 3) {
            saw_r0 = (d.new_value == 3);
        }
        if (d.kind == ChangeKind::kPc) saw_pc = true;
    }
    CHECK(saw_r0 && saw_pc);

    DebugStepInfo b = s.step();
    CHECK(b.reason == DebugStopReason::kStepped);
    CHECK(b.pc == 0x10);
    CHECK(b.instruction.mnemonic == isa::Mnemonic::kEXIT);
    bool saw_exited = false;
    for (const auto& d : b.reg_diffs)
        if (d.kind == ChangeKind::kExited && d.lane == 5 && d.new_value)
            saw_exited = true;
    CHECK(saw_exited);

    // After EXIT the launch finishes.
    DebugStepInfo c = s.step();
    CHECK(c.reason == DebugStopReason::kDone);
}

// ---------------------------------------------------------------------------
// Unsupported instruction: stop BEFORE execution; state stays viewable.
// ---------------------------------------------------------------------------

TEST(dbg_unsupported_stops_before_exec_and_state_viewable) {
    auto lk = load_kernel("_Z3kun", kUnsupported);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    DebugStepInfo a = s.step();  // S2R executes
    CHECK(a.reason == DebugStopReason::kStepped && a.pc == 0x0);

    DebugStepInfo b = s.step();  // MUFU: stops BEFORE executing
    CHECK(b.reason == DebugStopReason::kUnsupported);
    CHECK(b.pc == 0x10);
    CHECK(b.fault.has_value());
    CHECK(b.fault->kind() == FaultKind::kUnsupportedInstruction);
    CHECK(b.fault->mnemonic() && *b.fault->mnemonic() == "MUFU");
    // State still viewable: R0 was written by the S2R, R1 untouched, PC not
    // advanced past the unsupported instruction.
    std::uint32_t r0 = 0, r1 = 0;
    CHECK(s.read_gpr(0, 0, 3, 0, &r0).ok() && r0 == 3);
    CHECK(s.read_gpr(0, 0, 3, 1, &r1).ok() && r1 == 0);
    auto pc = s.read_pc(0, 0, 3);
    CHECK(pc.ok() && pc.value() == 0x10);
    // A further step stays parked at the same instruction.
    DebugStepInfo c = s.step();
    CHECK(c.reason == DebugStopReason::kUnsupported && c.pc == 0x10);
    // The session did not run away: no executed instruction after the S2R.
    CHECK(s.executed_count() == 1);
    // state_report still renders (fault + state inspection path).
    CHECK(!s.state_report().empty());
}

// ---------------------------------------------------------------------------
// step N then continue == direct continue (deterministic single worker).
// ---------------------------------------------------------------------------

TEST(dbg_step_n_then_continue_matches_direct_continue) {
    auto lk = load_kernel("_Z3kex", kLoop);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;

    auto sa0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(sa0.ok());
    if (!sa0.ok()) return;
    DebugSession sa = std::move(sa0.value());
    for (int i = 0; i < 5; ++i) {
        DebugStepInfo st = sa.step();
        CHECK(st.reason == DebugStopReason::kStepped);
    }
    DebugStepInfo stopa = sa.continue_run();
    CHECK(stopa.reason == DebugStopReason::kDone);

    auto sb0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(sb0.ok());
    if (!sb0.ok()) return;
    DebugSession sb = std::move(sb0.value());
    DebugStepInfo stopb = sb.continue_run();
    CHECK(stopb.reason == DebugStopReason::kDone);

    CHECK(sa.executed_count() == sb.executed_count());
    CHECK(state_equal(sa.ctas(), sb.ctas()));
    // Loop kernel: R2 == 5 after the loop.
    std::uint32_t r2 = 0;
    CHECK(sa.read_gpr(0, 0, 0, 2, &r2).ok() && r2 == 5);
}

// ---------------------------------------------------------------------------
// Divergence: PC breakpoint hits only the correct PC group + lane mask.
// ---------------------------------------------------------------------------

TEST(dbg_breakpoint_divergence_pc_group_and_lane_mask) {
    auto lk = load_kernel("_Z3kds", kDivSpin);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 100000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    // Breakpoint on the taken-path spin start (pc 0x50).
    Breakpoint bp;
    bp.kind = BreakpointKind::kPc;
    bp.pc = 0x50;
    auto id = s.add_breakpoint(bp);
    CHECK(id.ok());

    // The fall-through lanes exit, so only the taken lanes (0..15) ever reach
    // 0x50; the breakpoint fires with exactly that lane mask.
    DebugStepInfo st = s.continue_run();
    CHECK(st.reason == DebugStopReason::kPcBreakpoint);
    CHECK(st.pc == 0x50);
    CHECK(st.active_mask == 0x0000ffffu);
    CHECK(st.breakpoint_id == id.value());

    // Continue steps over the breakpoint word once, then re-hits it on the
    // spin loop with the same partial lane mask.
    DebugStepInfo st2 = s.continue_run();
    CHECK(st2.reason == DebugStopReason::kPcBreakpoint);
    CHECK(st2.pc == 0x50);
    CHECK(st2.active_mask == 0x0000ffffu);

    // Delete the breakpoint and run to the limit: the taken lanes spin; the
    // fall-through lanes exited with R1 = 0x11111111.
    CHECK(s.remove_breakpoint(id.value()).ok());
    s.set_instruction_limit(200);
    DebugStepInfo fin = s.continue_run();
    CHECK(fin.reason == DebugStopReason::kLimit);
    std::uint32_t r1 = 0, r2 = 0;
    for (int lane = 0; lane < 16; ++lane) {
        CHECK(s.read_gpr(0, 0, lane, 2, &r2).ok() && r2 == 0x22222222u);
    }
    for (int lane = 16; lane < 32; ++lane) {
        CHECK(s.read_gpr(0, 0, lane, 1, &r1).ok() && r1 == 0x11111111u);
        auto pc = s.read_pc(0, 0, lane);
        CHECK(pc.ok() && pc.value() == 0x50);  // EXIT word (0x40) + 16
    }
}

// ---------------------------------------------------------------------------
// Mnemonic breakpoint with CTA / warp / lane conditions.
// ---------------------------------------------------------------------------

TEST(dbg_breakpoint_cta_warp_lane_condition) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {2, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    // Mnemonic breakpoint on S2R restricted to CTA 1 only.
    Breakpoint bp;
    bp.kind = BreakpointKind::kMnemonic;
    bp.mnemonic = "S2R";
    bp.cta = 1;
    auto id = s.add_breakpoint(bp);
    CHECK(id.ok());

    DebugStepInfo st = s.continue_run();
    CHECK(st.reason == DebugStopReason::kMnemonicBreakpoint);
    CHECK(st.cta == 1);
    CHECK(st.instruction.mnemonic == isa::Mnemonic::kS2R);
    CHECK(st.breakpoint_id == id.value());
    // The breakpoint fires BEFORE CTA 1's S2R executes, so exactly one group
    // (CTA 0's S2R) ran.
    CHECK(s.executed_count() == 1);
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Blocker-1 (round 2 re-review): a mnemonic breakpoint must match the DECODED
// mnemonic of the group about to execute — `break mnem STG` must not stop at
// the entry MOV / IADD3.  The old check only required a non-empty target, so
// every instruction of the launch matched.
// ---------------------------------------------------------------------------

TEST(dbg_mnemonic_breakpoint_compares_mnemonic) {
    auto lk = load_kernel("_Z3kms", kMovIaddStg);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(256, 0);
    RunOptions opts;
    opts.memory.global = &global;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    Breakpoint bp;
    bp.kind = BreakpointKind::kMnemonic;
    bp.mnemonic = "STG";
    auto id = s.add_breakpoint(bp);
    CHECK(id.ok());

    // Continue: the MOV32I / MOV32I / IADD3 execute, and the launch stops
    // ONLY at the STG (before it executes).  With the old bug this stopped at
    // the very first instruction (MOV32I at pc 0x0).
    DebugStepInfo st = s.continue_run();
    CHECK(st.reason == DebugStopReason::kMnemonicBreakpoint);
    CHECK(st.pc == 0x30);
    CHECK(st.instruction.mnemonic == isa::Mnemonic::kSTG);
    CHECK(st.breakpoint_id == id.value());
    CHECK(s.executed_count() == 3);  // MOV32I, MOV32I, IADD3 ran; STG not yet

    // Continue again steps over the matched word once (GDB semantics) and the
    // launch finishes; the store committed R2 = 0x1234 + 0x5.
    DebugStepInfo fin = s.continue_run();
    CHECK(fin.reason == DebugStopReason::kDone);
    std::uint32_t w = 0;
    std::memcpy(&w, global.data() + 0x40, 4);
    CHECK(w == 0x1239u);
}

TEST(dbg_mnemonic_breakpoint_nonexistent_target_runs_to_done) {
    auto lk = load_kernel("_Z3kms", kMovIaddStg);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(256, 0);
    RunOptions opts;
    opts.memory.global = &global;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    // A mnemonic that does not appear in the kernel must never stop the
    // launch: continue runs straight to Done (and the STG still commits).
    Breakpoint bp;
    bp.kind = BreakpointKind::kMnemonic;
    bp.mnemonic = "MUFU";  // not present in kMovIaddStg
    auto id = s.add_breakpoint(bp);
    CHECK(id.ok());
    DebugStepInfo fin = s.continue_run();
    CHECK(fin.reason == DebugStopReason::kDone);
    CHECK(!fin.fault.has_value());
    std::uint32_t w = 0;
    std::memcpy(&w, global.data() + 0x40, 4);
    CHECK(w == 0x1239u);
    (void)id;
}

// ---------------------------------------------------------------------------
// Memory watchpoints: multi-lane, cross-boundary, atomic + negatives.
// ---------------------------------------------------------------------------

TEST(dbg_watchpoint_multilane) {
    auto lk = load_kernel("_Z3kst", kStgMask);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(256, 0);
    RunOptions opts;
    opts.memory.global = &global;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    Watchpoint wp;
    wp.space = AddressSpace::kGlobal;
    wp.base = 0x40;
    wp.size = 4;
    wp.kind = WK_WRITE;
    auto id = s.add_watchpoint(wp);
    CHECK(id.ok());

    DebugStepInfo st = s.continue_run();
    CHECK(st.reason == DebugStopReason::kWatchpoint);
    CHECK(st.pc == 0x30);
    // Only lanes < 16 were active on the predicated STG; the watchpoint hit
    // mask must be exactly those lanes.
    CHECK(!st.watch_hits.empty());
    CHECK(st.watch_hits[0].watchpoint_id == id.value());
    CHECK(st.watch_hits[0].lanes == 0x0000ffffu);
    CHECK(st.accesses.size() == 16);
    for (const auto& a : st.accesses) {
        CHECK(a.space == AddressSpace::kGlobal && a.address == 0x40);
        CHECK(a.width == 4 && a.write && !a.atomic);
    }
    // After continue the store committed; the buffer holds 0xDEADBEEF.
    DebugStepInfo fin = s.continue_run();
    CHECK(fin.reason == DebugStopReason::kDone);
    std::uint32_t w = 0;
    std::memcpy(&w, global.data() + 0x40, 4);
    CHECK(w == 0xDEADBEEFu);
}

TEST(dbg_watchpoint_cross_boundary_and_negative) {
    auto lk = load_kernel("_Z3k64", kStg64);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(256, 0);
    RunOptions opts;
    opts.memory.global = &global;

    // Cross-boundary: the 8-byte store at 0x40 covers [0x40,0x48); a
    // watchpoint on [0x44,0x48) intersects it.
    {
        auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
        CHECK(s0.ok());
        if (!s0.ok()) return;
        auto s = std::move(s0.value());
        Watchpoint wp;
        wp.space = AddressSpace::kGlobal;
        wp.base = 0x44;
        wp.size = 4;
        wp.kind = WK_WRITE;
        auto id = s.add_watchpoint(wp);
        CHECK(id.ok());
        DebugStepInfo st = s.continue_run();
        CHECK(st.reason == DebugStopReason::kWatchpoint);
        CHECK(st.watch_hits.size() == 1);
        CHECK(st.watch_hits[0].watchpoint_id == id.value());
        CHECK(st.watch_hits[0].lanes == 0xffffffffu);
    }
    // Negative: a watchpoint wholly outside the store range does not fire.
    {
        auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
        CHECK(s0.ok());
        if (!s0.ok()) return;
        auto s = std::move(s0.value());
        Watchpoint wp;
        wp.space = AddressSpace::kGlobal;
        wp.base = 0x30;
        wp.size = 4;   // [0x30,0x34) — store covers [0x40,0x48)
        wp.kind = WK_WRITE;
        auto id = s.add_watchpoint(wp);
        CHECK(id.ok());
        DebugStepInfo st = s.continue_run();
        CHECK(st.reason == DebugStopReason::kDone);
        (void)id;
    }
    // The 8-byte store committed the two words.
    std::uint64_t w = 0;
    std::memcpy(&w, global.data() + 0x40, 8);
    CHECK(w == 0x5566778811223344ULL);
}

TEST(dbg_watchpoint_atomic_and_kind_negatives) {
    auto lk = load_kernel("_Z3kat", kAtom);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(256, 0);
    RunOptions opts;
    opts.memory.global = &global;

    // Atomic-kind watchpoint fires on the ATOM RMW.
    {
        auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
        CHECK(s0.ok());
        if (!s0.ok()) return;
        auto s = std::move(s0.value());
        Watchpoint wp;
        wp.space = AddressSpace::kGlobal;
        wp.base = 0x40;
        wp.size = 4;
        wp.kind = WK_ATOMIC;
        auto id = s.add_watchpoint(wp);
        CHECK(id.ok());
        DebugStepInfo st = s.continue_run();
        CHECK(st.reason == DebugStopReason::kWatchpoint);
        CHECK(st.instruction.mnemonic == isa::Mnemonic::kATOM);
        CHECK(!st.watch_hits.empty());
        CHECK(st.watch_hits[0].watchpoint_id == id.value());
        CHECK(st.watch_hits[0].atomic);
        // The atomic also performed a read-back into Rd, but the watchpoint
        // kind selected only WK_ATOMIC.
        for (const auto& a : st.accesses)
            CHECK(a.atomic);
        // The atomic committed on this stop: the word advanced by the lanes
        // that hit the watchpoint (all 32).
        std::uint32_t w = 0;
        std::memcpy(&w, global.data() + 0x40, 4);
        CHECK(w == 32u);
    }
    // A read-only watchpoint does NOT fire on the atomic (RMW is write+atomic
    // kind, never plain read); execution runs to done.
    {
        // Fresh buffer so the committed atomics of this subtest are isolated.
        std::vector<std::uint8_t> g2(256, 0);
        RunOptions o2 = opts;
        o2.memory.global = &g2;
        auto s0 = DebugSession::begin(lk.kernel, env, o2, 10000);
        CHECK(s0.ok());
        if (!s0.ok()) return;
        auto s = std::move(s0.value());
        Watchpoint wp;
        wp.space = AddressSpace::kGlobal;
        wp.base = 0x40;
        wp.size = 4;
        wp.kind = WK_READ;
        auto id = s.add_watchpoint(wp);
        CHECK(id.ok());
        DebugStepInfo st = s.continue_run();
        CHECK(st.reason == DebugStopReason::kDone);
        std::uint32_t w = 0;
        std::memcpy(&w, g2.data() + 0x40, 4);
        CHECK(w == 32u);  // the atomics still committed (no watchpoint stop)
        (void)id;
    }
}

// ---------------------------------------------------------------------------
// Modify register / memory, then continue with the modified state.
// ---------------------------------------------------------------------------

TEST(dbg_modify_register_changes_execution) {
    auto lk = load_kernel("_Z3kad", kAdd);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    DebugStepInfo a = s.step();  // S2R
    CHECK(a.reason == DebugStopReason::kStepped);
    DebugStepInfo b = s.step();  // MOV32I R1,5
    CHECK(b.reason == DebugStopReason::kStepped && b.pc == 0x10);
    // Overwrite R1 = 99 on every lane.
    for (int lane = 0; lane < kLanesPerWarp; ++lane)
        CHECK(s.write_gpr(0, 0, lane, 1, 99).ok());
    DebugStepInfo c = s.step();  // IADD3 R2 = R0 + R1
    CHECK(c.reason == DebugStopReason::kStepped && c.pc == 0x20);
    std::uint32_t r2 = 0, r1 = 0;
    for (int lane = 0; lane < 32; ++lane) {
        CHECK(s.read_gpr(0, 0, lane, 2, &r2).ok());
        CHECK(r2 == static_cast<std::uint32_t>(lane) + 99);
    }
    CHECK(s.read_gpr(0, 0, 0, 1, &r1).ok() && r1 == 99);
    // The register diff of the IADD3 step reports the R2 writes.
    std::size_t r2_diffs = 0;
    for (const auto& d : c.reg_diffs)
        if (d.kind == ChangeKind::kGpr && d.index == 2) ++r2_diffs;
    CHECK(r2_diffs == 32);
}

TEST(dbg_modify_memory_changes_execution) {
    auto lk = load_kernel("_Z3ksl", kStgLdg);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(256, 0);
    RunOptions opts;
    opts.memory.global = &global;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    DebugStepInfo a = s.step();  // MOV32I R0
    CHECK(a.reason == DebugStopReason::kStepped);
    DebugStepInfo b = s.step();  // STG.E [0x40], R0
    CHECK(b.reason == DebugStopReason::kStepped && b.pc == 0x10);
    CHECK(b.accesses.size() == 32);
    // The store committed the original value.
    std::uint32_t w = 0;
    std::memcpy(&w, global.data() + 0x40, 4);
    CHECK(w == 0xAAAA5555u);
    // Rewrite the memory via the debugger; the LDG must now read the new value.
    const std::vector<std::uint8_t> bytes = {0xBB, 0xBB, 0xBB, 0xBB};
    CHECK(s.write_memory(AddressSpace::kGlobal, 0x40, bytes).ok());
    DebugStepInfo c = s.step();  // LDG.E R1, [0x40]
    CHECK(c.reason == DebugStopReason::kStepped && c.pc == 0x20);
    std::uint32_t r1 = 0;
    CHECK(s.read_gpr(0, 0, 0, 1, &r1).ok());
    CHECK(r1 == 0xBBBBBBBBu);
}

// ---------------------------------------------------------------------------
// Fault stop: a memory fault stops the session with state viewable and the
// fault object explaining the failure (memory fault).
// ---------------------------------------------------------------------------

TEST(dbg_fault_stop_state_viewable_memory_fault) {
    auto lk = load_kernel("_Z3kob", kStgOob);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    std::vector<std::uint8_t> global(0x100, 0);
    RunOptions opts;
    opts.memory.global = &global;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    DebugStepInfo a = s.step();  // MOV32I
    CHECK(a.reason == DebugStopReason::kStepped);
    DebugStepInfo f = s.step();  // STG out of bounds -> fault
    CHECK(f.reason == DebugStopReason::kFault);
    CHECK(f.fault.has_value());
    CHECK(f.fault->kind() == FaultKind::kIllegalMemoryAccess);
    // The fault carries locality: PC, warp, active mask, message.
    CHECK(f.fault->pc().value_or(0) == 0x10);
    CHECK(f.fault->warp().value_or(~0u) == 0);
    CHECK(f.fault->active_mask().value_or(0) == 0xffffffffu);
    CHECK(!f.fault->message().empty());
    // Session is faulted (terminal) and state still viewable.
    CHECK(s.faulted());
    std::uint32_t r0 = 0;
    CHECK(s.read_gpr(0, 0, 7, 0, &r0).ok() && r0 == 0xDEADBEEFu);
    DebugStepInfo g = s.step();
    CHECK(g.reason == DebugStopReason::kFault);
}

// ---------------------------------------------------------------------------
// Instruction limit: the session suspends AT the limit with state viewable.
// ---------------------------------------------------------------------------

TEST(dbg_instruction_limit_stops_with_state) {
    auto lk = load_kernel("_Z3kex", kLoop);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 3);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());
    CHECK(s.instruction_limit() == 3);

    DebugStepInfo a = s.step();
    CHECK(a.reason == DebugStopReason::kStepped && a.dynamic_instructions == 1);
    DebugStepInfo b = s.step();
    CHECK(b.reason == DebugStopReason::kStepped && b.dynamic_instructions == 2);
    DebugStepInfo c = s.step();
    CHECK(c.reason == DebugStopReason::kStepped && c.dynamic_instructions == 3);
    DebugStepInfo d = s.step();
    CHECK(d.reason == DebugStopReason::kLimit);
    CHECK(d.fault.has_value());
    CHECK(d.fault->kind() == FaultKind::kInstructionLimit);
    // The limit instruction never executed.
    CHECK(s.executed_count() == 3);
    // State is viewable (R2 still 0 — the IADD3 never ran).
    std::uint32_t r2 = 0;
    CHECK(s.read_gpr(0, 0, 0, 2, &r2).ok() && r2 == 0);
    // Raising the limit lets execution continue.
    s.set_instruction_limit(10000);
    DebugStepInfo e = s.continue_run();
    CHECK(e.reason == DebugStopReason::kDone);
    CHECK(s.read_gpr(0, 0, 0, 2, &r2).ok() && r2 == 5);
}

// ---------------------------------------------------------------------------
// Warp step: focus restricts scheduling to one (cta, warp).
// ---------------------------------------------------------------------------

TEST(dbg_warp_step_focus) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {64, 1, 1};  // two warps
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    s.set_focus(std::make_pair<std::uint32_t, std::uint32_t>(0, 1));
    CHECK(s.focus().has_value());
    DebugStepInfo a = s.step();
    CHECK(a.reason == DebugStopReason::kStepped);
    CHECK(a.warp == 1);
    DebugStepInfo b = s.step();
    CHECK(b.reason == DebugStopReason::kStepped && b.warp == 1);
    // Only warp 1 ran so far: warp 0 still at the entry S2R.
    std::uint32_t r0 = 0;
    CHECK(s.read_gpr(0, 0, 0, 0, &r0).ok() && r0 == 0);
    auto p0 = s.read_pc(0, 0, 0);
    CHECK(p0.ok() && p0.value() == 0x0);

    // Clear focus: the whole launch finishes; warp 0 then runs.
    s.set_focus(std::nullopt);
    DebugStepInfo c = s.continue_run();
    CHECK(c.reason == DebugStopReason::kDone);
    // Warp 0's S2R ran after focus was cleared (TID.X = lane).
    CHECK(s.read_gpr(0, 0, 0, 0, &r0).ok() && r0 == 0);
    // Warp 1's S2R ran during the focused steps (TID.X = 32 + lane).
    CHECK(s.read_gpr(0, 1, 0, 0, &r0).ok() && r0 == 32);
    auto p1 = s.read_pc(0, 1, 0);
    CHECK(p1.ok() && p1.value() == 0x20);  // EXIT word pc + 16
}

// ---------------------------------------------------------------------------
// Blocker (Phase 7 re-review): focus-warp semantics vs launch Done.
//
// A warp-step focus must never collapse into "the launch is done".  When the
// focused warp has nothing eligible to run — because it already exited, or is
// suspended at a barrier, or the (cta, warp) simply does not exist — the
// session must keep reporting kFocusBlocked (NOT kDone), stay alive, and
// resume once the focus is cleared / re-targeted.
// ---------------------------------------------------------------------------

TEST(dbg_focus_warp_exits_then_clear_focus_continues) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {64, 1, 1};  // two warps
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    s.set_focus(std::make_pair(0u, 1u));
    // Run the focused warp to completion.
    DebugStepInfo a = s.step();  // warp 1 S2R
    CHECK(a.reason == DebugStopReason::kStepped && a.warp == 1);
    DebugStepInfo b = s.step();  // warp 1 EXIT
    CHECK(b.reason == DebugStopReason::kStepped && b.warp == 1);
    // The focus warp exited, but the launch is NOT done: warp 0 is still
    // runnable and merely excluded by the filter.  A step must report
    // kFocusBlocked, never kDone, and the session must stay alive.
    DebugStepInfo c = s.step();
    CHECK(c.reason == DebugStopReason::kFocusBlocked);
    CHECK(!s.finished());
    CHECK(!s.faulted());
    DebugStepInfo d = s.step();
    CHECK(d.reason == DebugStopReason::kFocusBlocked);
    // Clear focus: warp 0 is now schedulable and the launch completes.
    s.set_focus(std::nullopt);
    DebugStepInfo e = s.step();
    CHECK(e.reason == DebugStopReason::kStepped && e.warp == 0);
    DebugStepInfo f = s.step();
    CHECK(f.reason == DebugStopReason::kStepped && f.warp == 0);
    DebugStepInfo g = s.step();
    CHECK(g.reason == DebugStopReason::kDone);
    // Both S2Rs ran: warp 1 under focus (TID.X = 32 + lane), warp 0 after the
    // clear (TID.X = lane).
    std::uint32_t r0 = 0;
    CHECK(s.read_gpr(0, 0, 0, 0, &r0).ok() && r0 == 0);
    CHECK(s.read_gpr(0, 1, 0, 0, &r0).ok() && r0 == 32);
}

TEST(dbg_focus_warp_waiting_barrier_released_by_other) {
    auto lk = load_kernel("_Z4kbar", kBarSync);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {64, 1, 1};  // two warps
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    s.set_focus(std::make_pair(0u, 0u));
    DebugStepInfo a = s.step();  // warp 0 S2R
    CHECK(a.reason == DebugStopReason::kStepped && a.warp == 0);
    DebugStepInfo b = s.step();  // warp 0 BAR.SYNC -> suspended at barrier
    CHECK(b.reason == DebugStopReason::kStepped && b.warp == 0);
    // Warp 0 is parked at the barrier; warp 1 is runnable but excluded by the
    // focus filter.  Stepping must report kFocusBlocked (the barrier release
    // is blocked on warp 1, which only focus-clearing can schedule) — NOT the
    // launch being done.
    DebugStepInfo c = s.step();
    CHECK(c.reason == DebugStopReason::kFocusBlocked);
    CHECK(!s.finished());
    DebugStepInfo d = s.step();
    CHECK(d.reason == DebugStopReason::kFocusBlocked);
    // Clear focus: warp 1 runs, arrives at the barrier, releases warp 0, and
    // the whole launch completes normally.
    s.set_focus(std::nullopt);
    DebugStepInfo fin = s.continue_run();
    CHECK(fin.reason == DebugStopReason::kDone);
    std::uint32_t r0 = 0;
    CHECK(s.read_gpr(0, 0, 0, 0, &r0).ok() && r0 == 0);   // warp 0 lane 0 TID
    CHECK(s.read_gpr(0, 1, 0, 0, &r0).ok() && r0 == 32);  // warp 1 lane 0 TID
}

TEST(dbg_focus_nonexistent_cta_warp_rejected) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};  // one warp
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    // A focus target naming a CTA/warp that is not present in this launch is a
    // STRUCTURED rejection — never silently accepted and then mistaken for
    // "the launch is done".
    auto bad_cta = s.set_focus(std::make_pair(1u, 0u));  // no CTA 1
    CHECK(bad_cta.failed());
    auto bad_warp = s.set_focus(std::make_pair(0u, 4u));  // only warp 0 exists
    CHECK(bad_warp.failed());
    // The rejected set_focus left the session untouched: no focus is active.
    CHECK(!s.focus().has_value());
    // A valid focus still works afterwards, and the launch runs to completion.
    auto good = s.set_focus(std::make_pair(0u, 0u));
    CHECK(good.ok());
    DebugStepInfo a = s.step();
    CHECK(a.reason == DebugStopReason::kStepped && a.warp == 0);
    s.set_focus(std::nullopt);
    DebugStepInfo fin = s.continue_run();
    CHECK(fin.reason == DebugStopReason::kDone);
}

// ---------------------------------------------------------------------------
// Blocker-2 (round 2 re-review): the debugger must report a barrier deadlock
// as a FAULT, never as a clean Done.  Warp 0 (TID < 32) waits at BAR.SYNC 0;
// warp 1 (TID >= 32) exits without arriving — a real barrier deadlock.  The
// old code latched done_ = true + kDone on "no runnable group", silently
// reporting the deadlocked launch as a clean completion.
// ---------------------------------------------------------------------------

TEST(dbg_continue_run_barrier_deadlock_reports_fault) {
    // kBarDeadlock: S2R R0,TID ; ISETP.LT P0,R0,0x20 ; @!P0 EXIT ; BAR.SYNC 0 ;
    // EXIT.  Warp 0 (TID 0..31): P0 true -> falls through to BAR.SYNC 0 and
    // waits forever; warp 1 (TID 32..63): P0 false -> @!P0 EXIT without
    // arriving.
    const std::vector<std::pair<std::uint64_t, std::uint64_t>> kBarDeadlock = {
        {0x7919ULL, 0xe0a0000002100ULL},           // 0000 S2R R0, SR_TID.X
        {0x200000780cULL, 0x1fca0003f01070ULL},    // 0010 ISETP.LT.U32.AND P0
        {0x894dULL, 0xfea0003800000ULL},           // 0020 @!P0 EXIT
        {0x7b1dULL, 0xfea0000000000ULL},           // 0030 BAR.SYNC 0
        {0x794dULL, 0xfea0003800000ULL},           // 0040 EXIT
    };
    auto lk = load_kernel("_Z4kbdv", kBarDeadlock);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {64, 1, 1};  // two warps
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 100000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    DebugStepInfo fin = s.continue_run();
    // A real barrier deadlock is a FAULT, never kDone (fault-stop contract).
    CHECK(fin.reason == DebugStopReason::kFault);
    CHECK(fin.fault.has_value());
    CHECK(fin.fault->kind() == FaultKind::kBarrierDeadlock);
    CHECK(!fin.fault->message().empty());
    CHECK(fin.fault->message().find("barrier") != std::string::npos);
    // The session is faulted (terminal), not "done", and state is viewable.
    CHECK(s.faulted());
    CHECK(!s.finished());
    std::uint32_t r0 = 0;
    CHECK(s.read_gpr(0, 0, 3, 0, &r0).ok() && r0 == 3);  // warp 0 lane 3 TID
    // A further drive re-reports the terminal fault (does not run away).
    DebugStepInfo again = s.continue_run();
    CHECK(again.reason == DebugStopReason::kFault);
    CHECK(again.fault.has_value() &&
          again.fault->kind() == FaultKind::kBarrierDeadlock);
}

// ---------------------------------------------------------------------------
// Barrier / scoreboard / pending view; special registers; PC modify.
// ---------------------------------------------------------------------------

TEST(dbg_state_view_barrier_scoreboard_pending_sreg) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    // Pending memory-op scoreboard: no cp.async ops in this kernel -> 0.
    auto pg = s.pending_groups();
    CHECK(pg.ok() && pg.value() == 0);
    // Barrier map is empty (no named barrier).
    auto bars = s.barriers(0);
    CHECK(bars.ok() && bars.value().empty());
    // Special register view (LaneID).
    auto sr = s.read_special(0, 0, 7, SpecialReg::kLaneid);
    CHECK(sr.ok() && sr.value() == 7);
    auto sr2 = s.read_special(0, 0, 7, SpecialReg::kTidX);
    CHECK(sr2.ok() && sr2.value() == 7);
    // decode_at returns the schedule word (scoreboard fields) for a pc.
    auto di = s.decode_at(0x0);
    CHECK(di.ok());
    CHECK(di.value().mnemonic == isa::Mnemonic::kS2R);
    CHECK(di.value().schedule.dst_wr_sb >= 0);
    // PC modify: jump lane 0 to the EXIT word; the write is reflected in the
    // live state and the launch then completes.
    CHECK(s.write_pc(0, 0, 0, 0x10).ok());
    auto lpc = s.read_pc(0, 0, 0);
    CHECK(lpc.ok() && lpc.value() == 0x10);
    DebugStepInfo a = s.continue_run();
    CHECK(a.reason == DebugStopReason::kDone);
    (void)pg;
}

TEST(dbg_pc_and_pred_write_continue) {
    auto lk = load_kernel("_Z3kds", kDivSpin);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    // Step the ISETP; then force P0 false on lanes 0..15 so NO lane takes the
    // branch — all lanes fall through to 0x30.
    DebugStepInfo a = s.step();  // S2R
    CHECK(a.reason == DebugStopReason::kStepped);
    DebugStepInfo b = s.step();  // ISETP
    CHECK(b.reason == DebugStopReason::kStepped && b.pc == 0x10);
    for (int lane = 0; lane < 16; ++lane)
        CHECK(s.write_pred(0, 0, lane, 0, false).ok());
    // Step the @P0 BRA: with P0 false everywhere, no lane jumps (the group
    // runs as an all-skipped group), then the fall-through MOV32I executes.
    DebugStepInfo c = s.step();
    CHECK(c.reason == DebugStopReason::kStepped && c.pc == 0x20);
    DebugStepInfo d = s.step();
    CHECK(d.reason == DebugStopReason::kStepped && d.pc == 0x30);
    std::uint32_t r1 = 0;
    for (int lane = 0; lane < 32; ++lane) {
        CHECK(s.read_gpr(0, 0, lane, 1, &r1).ok());
        CHECK(r1 == 0x11111111u);  // all took the fall-through path
    }
}

// ---------------------------------------------------------------------------
// Blocker (Phase 7 re-review): shared/local memory windows require an EXPLICIT
// scope.  There is no first-match scan — a missing scope (or a scope naming a
// CTA/warp that does not exist) is a structured error, and writes can never
// silently hit an unintended window.  Round 2 re-review (High-1): local memory
// in this sim is a PER-WARP window addressed by raw byte offset — there is NO
// scope.lane dimension (lane 0 and lane 1 would point at the same byte by
// design, so the API no longer pretends otherwise).
// ---------------------------------------------------------------------------

TEST(dbg_shared_local_memory_requires_explicit_scope) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {64, 1, 1};  // two warps
    env.grid = {2, 1, 1};    // two CTAs
    RunOptions opts;
    opts.memory.shared_size = 0x400;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());
    const std::vector<std::uint8_t> shw = {0x11, 0x22, 0x33, 0x44};
    std::vector<std::uint8_t> out;

    // Shared WITHOUT scope -> structured rejection (never a first-match scan).
    CHECK(s.read_memory(AddressSpace::kShared, 0, 4, &out).failed());
    CHECK(s.write_memory(AddressSpace::kShared, 0, shw).failed());
    // Local WITHOUT scope (no cta), or with cta but no warp -> rejected.
    CHECK(s.read_memory(AddressSpace::kLocal, 0, 4, &out).failed());
    CHECK(s.write_memory(AddressSpace::kLocal, 0, shw).failed());
    MemoryScope lcta_only;
    lcta_only.cta = 0;
    CHECK(s.read_memory(AddressSpace::kLocal, 0, 4, &out, lcta_only).failed());

    // Shared with explicit CTA scope works, and is per-CTA isolated.
    MemoryScope sc0;
    sc0.cta = 0;
    CHECK(s.write_memory(AddressSpace::kShared, 0, shw, sc0).ok());
    CHECK(s.read_memory(AddressSpace::kShared, 0, 4, &out, sc0).ok());
    CHECK(out == shw);
    MemoryScope sc1;
    sc1.cta = 1;
    CHECK(s.read_memory(AddressSpace::kShared, 0, 4, &out, sc1).ok());
    CHECK(out != shw);  // CTA 1's window is a different buffer (all zeros)

    // Local with explicit (cta, warp) scope works, and is warp-isolated.
    MemoryScope lc0w0;
    lc0w0.cta = 0;
    lc0w0.warp = 0;
    MemoryScope lc0w1;
    lc0w1.cta = 0;
    lc0w1.warp = 1;
    CHECK(s.write_memory(AddressSpace::kLocal, 0, shw, lc0w0).ok());
    CHECK(s.read_memory(AddressSpace::kLocal, 0, 4, &out, lc0w0).ok());
    CHECK(out == shw);
    CHECK(s.read_memory(AddressSpace::kLocal, 0, 4, &out, lc0w1).ok());
    CHECK(out != shw);  // warp 1's local window is untouched

    // Round 2 re-review (High-1): the per-warp window is addressed by RAW byte
    // offset — distinct offsets are distinct bytes, and there is no lane
    // dimension (the API has no scope.lane anymore).  Write two words at two
    // offsets of warp 0's window and read each back at its own offset.
    const std::vector<std::uint8_t> wordA = {0xaa, 0xbb, 0xcc, 0xdd};
    const std::vector<std::uint8_t> wordB = {0x11, 0x22, 0x33, 0x44};
    CHECK(s.write_memory(AddressSpace::kLocal, 0x100, wordA, lc0w0).ok());
    CHECK(s.write_memory(AddressSpace::kLocal, 0x104, wordB, lc0w0).ok());
    CHECK(s.read_memory(AddressSpace::kLocal, 0x100, 4, &out, lc0w0).ok());
    CHECK(out == wordA);
    CHECK(s.read_memory(AddressSpace::kLocal, 0x104, 4, &out, lc0w0).ok());
    CHECK(out == wordB);
    // offset 0 still holds the earlier write (untouched by the offset 0x100
    // writes) — the window is one flat byte array per warp.
    CHECK(s.read_memory(AddressSpace::kLocal, 0, 4, &out, lc0w0).ok());
    CHECK(out == shw);

    // A scope naming a CTA that does not exist -> not found, not first-match.
    MemoryScope nosuch;
    nosuch.cta = 99;
    CHECK(s.read_memory(AddressSpace::kShared, 0, 4, &out, nosuch).failed());

    // global/constant ignore the scope entirely (no scope needed).
    std::vector<std::uint8_t> global(256, 0);
    RunOptions o2;
    o2.memory.global = &global;
    auto g0 = DebugSession::begin(lk.kernel, env, o2, 10000);
    CHECK(g0.ok());
    if (!g0.ok()) return;
    auto g = std::move(g0.value());
    CHECK(g.write_memory(AddressSpace::kGlobal, 0x40, shw).ok());
    CHECK(g.read_memory(AddressSpace::kGlobal, 0x40, 4, &out).ok());
    CHECK(out == shw);
    // Even a bogus scope is ignored for unscoped spaces.
    CHECK(g.read_memory(AddressSpace::kGlobal, 0x40, 4, &out, nosuch).ok());
}

// ---------------------------------------------------------------------------
// Medium (Phase 7 re-review): watchpoint / debugger memory range arithmetic
// must never wrap uint64.  Ranges whose [base, base+size) span would wrap are
// rejected at add time; bounds checks use subtractive comparisons.
// ---------------------------------------------------------------------------

TEST(dbg_watchpoint_range_overflow_rejected) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    Watchpoint wp;
    wp.space = AddressSpace::kGlobal;
    wp.kind = WK_WRITE;
    // [base, base+size) would wrap -> rejected (hits() relies on a
    // non-wrapping window).
    wp.base = UINT64_MAX;
    wp.size = 2;
    CHECK(s.add_watchpoint(wp).failed());
    wp.base = UINT64_MAX - 1;
    wp.size = 2;
    CHECK(s.add_watchpoint(wp).failed());
    // A non-wrapping range just below the top is fine.
    wp.base = UINT64_MAX - 1;
    wp.size = 1;
    auto ok = s.add_watchpoint(wp);
    CHECK(ok.ok());

    // Debugger memory reads reject absurd lengths with a subtractive bounds
    // check (never resize-wrap / bad_alloc before the service rejects it).
    std::vector<std::uint8_t> global(64, 0);
    RunOptions o2;
    o2.memory.global = &global;
    auto g0 = DebugSession::begin(lk.kernel, env, o2, 10000);
    CHECK(g0.ok());
    if (!g0.ok()) return;
    auto g = std::move(g0.value());
    std::vector<std::uint8_t> out;
    CHECK(g.read_memory(AddressSpace::kGlobal, 0, UINT64_MAX, &out).failed());
    CHECK(g.read_memory(AddressSpace::kGlobal, UINT64_MAX, 4, &out).failed());
    (void)ok;
}

// ---------------------------------------------------------------------------
// Medium (Phase 7 re-review): breakpoint step-over keeps the PC as a full
// uint64_t.  A 32-bit field would collapse high PCs; the API round-trips and
// validates 64-bit PCs, and the step-over (GDB) semantics still match by the
// full word address.
// ---------------------------------------------------------------------------

TEST(dbg_breakpoint_step_over_64bit_pc) {
    auto lk = load_kernel("_Z3kds", kDivSpin);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 100000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    // read_pc returns the full uint64_t PC.
    auto pc0 = s.read_pc(0, 0, 3);
    CHECK(pc0.ok() && pc0.value() == 0x0);
    // A PC with bits above 32 set is out of kernel text: structured rejection
    // (a 32-bit truncation would have silently wrapped the address).
    auto bad = s.write_pc(0, 0, 3, 0x100000010ULL);
    CHECK(bad.failed());
    // A valid 64-bit PC write round-trips.
    CHECK(s.write_pc(0, 0, 3, 0x50).ok());
    auto pc50 = s.read_pc(0, 0, 3);
    CHECK(pc50.ok() && pc50.value() == 0x50);
    CHECK(s.write_pc(0, 0, 3, 0x0).ok());

    // Step-over semantics with the 64-bit suspend record: hit the 0x50
    // breakpoint, continue (steps over the matched word once), re-hit on the
    // spin loop at the same 64-bit pc.
    Breakpoint bp;
    bp.kind = BreakpointKind::kPc;
    bp.pc = 0x50;
    auto id = s.add_breakpoint(bp);
    CHECK(id.ok());
    DebugStepInfo st = s.continue_run();
    CHECK(st.reason == DebugStopReason::kPcBreakpoint && st.pc == 0x50);
    DebugStepInfo st2 = s.continue_run();
    CHECK(st2.reason == DebugStopReason::kPcBreakpoint && st2.pc == 0x50);
}

// Medium-1 (round 2 re-review): the step-over identity comparison itself is a
// mutation gate.  The old test only exercised high PCs via the API round-trip
// / rejection path — the REAL step-over stayed at 0x50, so a regression to a
// uint32_t SuspendBp::pc would have gone undetected.  This test drives
// SuspendBp::matches directly with a high 64-bit pc: a truncated (uint32_t)
// identity must never match a full-width query.
TEST(dbg_suspend_bp_identity_64bit) {
    SuspendBp bp;
    bp.cta = 1;
    bp.warp = 2;
    bp.pc = 0x100000050ULL;  // high word address: low 32 bits == 0x50
    // Exact full-width identity matches.
    CHECK(bp.matches(1, 2, 0x100000050ULL));
    // The low-32-bit truncation of the same pc must NOT match: a uint32_t
    // field would have stored 0x50 and wrongly treated these as identical.
    CHECK(!bp.matches(1, 2, 0x50));
    // Neighbouring high addresses / wrong cta / wrong warp must not match.
    CHECK(!bp.matches(1, 2, 0x100000040ULL));
    CHECK(!bp.matches(1, 2, 0x100000060ULL));
    CHECK(!bp.matches(0, 2, 0x100000050ULL));
    CHECK(!bp.matches(1, 3, 0x100000050ULL));
    // The two real drive-group sites use the same predicate (byte-for-byte):
    // the continue-time bypass and the executed-time step-over reset both call
    // SuspendBp::matches, so this single identity test guards both.
}

// ---------------------------------------------------------------------------
// Medium (Phase 7 re-review): breakpoints and watchpoints draw from ONE id
// pool, so `del <id>` / remove_breakpoint(id) / remove_watchpoint(id) are
// unambiguous and cross-kind deletes fail instead of silently deleting a
// same-numbered object of the other kind.
// ---------------------------------------------------------------------------

TEST(dbg_breakpoint_watchpoint_shared_id_pool) {
    auto lk = load_kernel("_Z3kex", kS2rExit);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};
    RunOptions opts;
    auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
    CHECK(s0.ok());
    if (!s0.ok()) return;
    auto s = std::move(s0.value());

    Breakpoint bp;
    bp.kind = BreakpointKind::kPc;
    bp.pc = 0x30;
    auto id_b1 = s.add_breakpoint(bp);
    CHECK(id_b1.ok() && id_b1.value() == 1);
    Watchpoint wp;
    wp.space = AddressSpace::kGlobal;
    wp.base = 0x40;
    wp.size = 4;
    wp.kind = WK_WRITE;
    auto id_w1 = s.add_watchpoint(wp);
    // The watchpoint must NOT reuse the breakpoint's id (2, not 1): ids are
    // globally unique across both kinds.
    CHECK(id_w1.ok() && id_w1.value() == 2);
    Breakpoint bp2;
    bp2.kind = BreakpointKind::kPc;
    bp2.pc = 0x50;
    auto id_b2 = s.add_breakpoint(bp2);
    CHECK(id_b2.ok() && id_b2.value() == 3);

    // Cross-kind deletes by id fail (id 2 is a watchpoint, not a breakpoint).
    CHECK(s.remove_breakpoint(id_w1.value()).failed());
    CHECK(s.remove_watchpoint(id_b1.value()).failed());
    // Correct-kind deletes succeed.
    CHECK(s.remove_watchpoint(id_w1.value()).ok());
    CHECK(s.remove_breakpoint(id_b1.value()).ok());
    CHECK(s.remove_breakpoint(id_b2.value()).ok());
    // Ids are never reused: the next allocation is a fresh number.
    auto id_w2 = s.add_watchpoint(wp);
    CHECK(id_w2.ok() && id_w2.value() == 4);
}

// ---------------------------------------------------------------------------
// Reproducibility: identical scripted sessions produce byte-identical traces.
// ---------------------------------------------------------------------------

TEST(dbg_trace_fully_reproducible) {
    auto lk = load_kernel("_Z3kds", kDivSpin);
    CHECK(!lk.kernel.symbol_name.empty());
    if (lk.kernel.symbol_name.empty()) return;
    LaunchEnv env;
    env.block = {32, 1, 1};
    env.grid = {1, 1, 1};

    auto run_script = [&](std::vector<std::string>* trace_out) {
        RunOptions opts;
        auto s0 = DebugSession::begin(lk.kernel, env, opts, 10000);
        CHECK(s0.ok());
        if (!s0.ok()) return;
        auto s = std::move(s0.value());
        Breakpoint bp;
        bp.kind = BreakpointKind::kPc;
        bp.pc = 0x50;
        auto bid = s.add_breakpoint(bp);
        CHECK(bid.ok());
        // Run the same command sequence both times.
        DebugStepInfo x = s.continue_run();
        trace_out->push_back(x.canonical());
        x = s.step();
        trace_out->push_back(x.canonical());
        x = s.step();
        trace_out->push_back(x.canonical());
        x = s.continue_run();
        trace_out->push_back(x.canonical());
    };

    std::vector<std::string> t1, t2;
    run_script(&t1);
    run_script(&t2);
    CHECK(t1.size() == 4 && t2.size() == 4);
    for (std::size_t i = 0; i < t1.size() && i < t2.size(); ++i) {
        if (t1[i] != t2[i]) {
            std::fprintf(stderr, "trace mismatch at %zu:\n  A: %s\n  B: %s\n",
                         i, t1[i].c_str(), t2[i].c_str());
        }
        CHECK(t1[i] == t2[i]);
    }
}
}  // namespace

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-debugger");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu debugger tests\n");
    }
    return failures == 0 ? 0 : 1;
}
