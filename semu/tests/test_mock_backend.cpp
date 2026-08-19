// Mock backend tests (SIM_PLAN Phase 10).
//
// Verify the frozen backend contract a future JIT plugs into:
//   1. the mock RECEIVES the decoded IR and classifies every word (lowered /
//      interpreter-fallback / decode-only);
//   2. the mock ACCESSES the runtime services (constant bank read + a device
//      memory write/read probe);
//   3. un-lowered FUNCTIONAL instructions fall back to the interpreter and the
//      launch executes successfully (GPR result verified);
//   4. decode-only instructions (UTMALDG / UTMASTG / UTMAREDG — the TMA family)
//      are reported through the FAULT ABI as FaultKind::kUnsupportedInstruction
//      and nothing runs.
//
// The service constant bank feeds the fallback interpreter (params land at
// c[0x0][0x380] on both sides), proving the whole chain end-to-end.

#include <semu/mock_backend.hpp>

#include <cstdint>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

#include <semu/capability.hpp>
#include <semu/context.hpp>
#include <semu/cubin.hpp>
#include <semu/status.hpp>
#include "test_framework.hpp"

namespace {

void push16(std::vector<std::uint8_t>* out, std::uint16_t v) {
    out->push_back(v & 0xff);
    out->push_back((v >> 8) & 0xff);
}

// Minimal ELF64 sm120 cubin with a single kernel.  `params` describes KPARAM
// records as (ordinal, offset, size); `words` is the kernel text as (lo, hi)
// 64-bit halves.
std::vector<std::uint8_t> make_cubin(
    const std::string& mangled,
    const std::vector<std::tuple<std::uint32_t, std::uint32_t, std::uint32_t>>&
        params,
    const std::vector<std::pair<std::uint64_t, std::uint64_t>>& words) {
    struct S {
        std::string name;
        std::uint32_t type = 0;
        std::uint64_t flags = 0;
        std::vector<std::uint8_t> data;
        std::uint32_t link = 0;
        std::uint32_t info = 0;
        std::uint64_t align = 4;
        std::uint64_t entsize = 0;
    };
    std::vector<S> secs(7);
    secs[0].name = "";
    secs[1].name = ".shstrtab"; secs[1].type = 3;
    secs[2].name = ".strtab"; secs[2].type = 3;
    secs[3].name = ".symtab"; secs[3].type = 2; secs[3].link = 2;
    secs[3].entsize = 24; secs[3].align = 8;
    secs[4].name = ".text." + mangled; secs[4].type = 1;
    secs[4].flags = 2 | 4; secs[4].align = 128;
    secs[5].name = ".nv.info"; secs[5].type = 0x70000000;
    secs[6].name = ".nv.info." + mangled; secs[6].type = 0x70000000;
    secs[6].info = 4;

    auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
        for (int i = 0; i < 4; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
        for (int i = 0; i < 8; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto eia = [&](std::vector<std::uint8_t>* v, std::uint8_t fmt,
                   std::uint8_t etype, std::uint64_t size,
                   const std::vector<std::uint8_t>& payload) {
        v->push_back(fmt); v->push_back(etype);
        if (fmt == 4) {
            v->push_back(size & 0xff); v->push_back((size >> 8) & 0xff);
        }
        v->insert(v->end(), payload.begin(), payload.end());
    };

    std::vector<std::uint8_t> kern_info;
    std::uint32_t cbank = 0;
    for (const auto& [ord, off, size] : params) {
        std::vector<std::uint8_t> p;
        push32(&p, 0);
        push32(&p, (off << 16) | ord);
        push32(&p, (((size << 2) | 1) << 16) | 0xf000);
        eia(&kern_info, 4, 0x17, 12, p);
        cbank = std::max(cbank, off + size);
    }
    if (cbank > 0) {
        // EIATTR_CBANK_PARAM_SIZE (0x19): the loader's cbank_param_size.
        std::vector<std::uint8_t> p;
        push32(&p, cbank);
        eia(&kern_info, 4, 0x19, 4, p);
    }

    std::vector<std::uint8_t> text;
    for (const auto& [lo, hi] : words) {
        push64(&text, lo);
        push64(&text, hi);
    }

    std::vector<std::uint8_t> symtab(24, 0);
    auto sym = [&](std::uint32_t name_off, std::uint8_t info,
                   std::uint8_t other, std::uint16_t shndx,
                   std::uint64_t value, std::uint64_t size) {
        std::vector<std::uint8_t> e;
        push32(&e, name_off); e.push_back(info); e.push_back(other);
        e.push_back(shndx & 0xff); e.push_back(shndx >> 8);
        push64(&e, value); push64(&e, size);
        symtab.insert(symtab.end(), e.begin(), e.end());
    };
    const std::string textsec = ".text." + mangled;
    const std::string constant0 = ".nv.constant0." + mangled;
    std::string strtab = std::string(1, '\0') + textsec + '\0' + mangled +
                         '\0' + constant0 + '\0';
    // strtab overoffsets: "" at 0, textsec at 1, mangled at 1+textsec.size()+1,
    // constant0 after.
    const std::uint32_t m_off = static_cast<std::uint32_t>(1 + textsec.size() + 1);
    const std::uint32_t c_off = m_off + static_cast<std::uint32_t>(mangled.size() + 1);
    sym(1, 0x03, 0x00, 4, 0, 0);  // .text section
    sym(m_off, 0x12, 0x10, 4, 0, static_cast<std::uint64_t>(words.size() * 16));  // func
    sym(c_off, 0x03, 0x00, 4, 0, 0);  // constant0

    secs[4].data = text;
    secs[6].data = kern_info;
    secs[3].data = symtab;
    secs[2].data.assign(strtab.begin(), strtab.end());

    std::string shstr(1, '\0');
    for (std::size_t i = 1; i < secs.size(); ++i) shstr += secs[i].name + '\0';
    secs[1].data.assign(shstr.begin(), shstr.end());

    std::vector<std::uint64_t> offs(secs.size(), 0);
    std::uint64_t cur = 64;
    for (std::size_t i = 0; i < secs.size(); ++i) {
        if (i == 0) continue;
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
    push16(&out, 2);       // ET_EXEC
    push16(&out, 190);     // EM_CUDA
    push32(&out, 1);
    push64(&out, 0);
    push64(&out, 0);
    push64(&out, shoff);
    push32(&out, 0x06007802);
    push16(&out, 64); push16(&out, 56); push16(&out, 0);
    push16(&out, 64); push16(&out, static_cast<std::uint16_t>(secs.size()));
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

// One-param (8 bytes) cubin helpers.
std::vector<std::uint8_t> make_one_param_cubin(
    const std::string& mangled,
    const std::vector<std::pair<std::uint64_t, std::uint64_t>>& words) {
    return make_cubin(mangled, {{0, 0, 8}}, words);
}

constexpr std::pair<std::uint64_t, std::uint64_t> kLdc380 = {
    0x0000e000ff007b82ULL, 0x000fc00000000800ULL};  // LDC R0, c[0x0][0x380]
constexpr std::pair<std::uint64_t, std::uint64_t> kMovR1R0 = {
    0x0000000000017202ULL, 0x000fc00000000f00ULL};  // MOV R1, R0
constexpr std::pair<std::uint64_t, std::uint64_t> kIaddR2 = {
    0x0000000100027810ULL, 0x000fc00007ffe0ffULL};  // IADD3 R2, R0, 1, RZ
constexpr std::pair<std::uint64_t, std::uint64_t> kExit = {
    0x000000000000794dULL, 0x000fc00003800000ULL};  // EXIT
constexpr std::pair<std::uint64_t, std::uint64_t> kMov32iR3 = {
    0x0000002a00037802ULL, 0x000fc00000000f00ULL};  // MOV R3, 42
constexpr std::pair<std::uint64_t, std::uint64_t> kUtmaldg = {
    0x00000008040075b4ULL, 0x0025e20008008000ULL};  // UTMALDG.2D
constexpr std::pair<std::uint64_t, std::uint64_t> kUtmastg = {
    0x00000008100073b5ULL, 0x0025e20008008000ULL};  // UTMASTG.2D
constexpr std::pair<std::uint64_t, std::uint64_t> kUtmaredg = {
    0x00000008100073b6ULL, 0x0025e20008008000ULL};  // UTMAREDG.2D.ADD

// Phase 9 tensor-core words.  The dense F32-accumulator HMMA kernel below is
// the same word list test_interp.cpp:3369-3383 feeds the reference
// interpreter (interp_phase9_hmma_bf16_k16); the sparse / scale / MXQMMA
// words are the sm120 corpus's encoder-generated representatives (each
// decodes uniquely to the named variant class).
const std::vector<std::pair<std::uint64_t, std::uint64_t>> kDenseHmmaKernel = {
    {0x3f80000000047802ULL, 0x000fca0000000f00ULL},  // MOV32I R4, 0x3F800000
    {0x3f80000000057802ULL, 0x000fca0000000f00ULL},  // MOV32I R5, 0x3F800000
    {0x3f80000000067802ULL, 0x000fca0000000f00ULL},  // MOV32I R6, 0x3F800000
    {0x3f80000000077802ULL, 0x000fca0000000f00ULL},  // MOV32I R7, 0x3F800000
    {0x3f80000000027802ULL, 0x000fca0000000f00ULL},  // MOV32I R2, 0x3F800000
    {0x3f80000000037802ULL, 0x000fca0000000f00ULL},  // MOV32I R3, 0x3F800000
    {0x41200000000c7802ULL, 0x000fca0000000f00ULL},  // MOV32I R12, 10.0
    {0x41300000000d7802ULL, 0x000fca0000000f00ULL},  // MOV32I R13, 11.0
    {0x41400000000e7802ULL, 0x000fca0000000f00ULL},  // MOV32I R14, 12.0
    {0x41500000000f7802ULL, 0x000fca0000000f00ULL},  // MOV32I R15, 13.0
    {0x00000002041c723cULL, 0x020fe2000004180cULL},  // HMMA.16816.F32.BF16
    {0x0000000000007918ULL, 0x000fca0000000000ULL},  // NOP
    {0x000000000000794dULL, 0x000fea0003800000ULL},  // EXIT
};

// Non-dense tensor alternatives (decode-only boundary): sparse HMMA, scale
// OMMA, and the scale-only MXQMMA family.
constexpr std::pair<std::uint64_t, std::uint64_t> kHmmaSparseWord = {
    0x00020000000723cULL, 0x000fe20000081200ULL};  // HMMA.SP.1688.F32.TF32
constexpr std::pair<std::uint64_t, std::uint64_t> kOmmaSpScaleWord = {
    0x000000000000747fULL, 0x000fe20000090000ULL};  // OMMA.SF.SP.168128.F32.E2M1.E2M1.E8
constexpr std::pair<std::uint64_t, std::uint64_t> kMxQmmaScaleWord = {
    0x000000000000747eULL, 0x000fe20000000000ULL};  // MXQMMA.SF.16832.F32.S2_6.S2_6.E8

}  // namespace

// ---------------------------------------------------------------------------
// Fallback path: functional-but-un-lowered instructions execute via the
// interpreter and the launch SUCCEEDS.
// ---------------------------------------------------------------------------
TEST(mock_backend_fallback_interpreter) {
    // LDC R0, c[0x0][0x380] ; MOV R1, R0 ; IADD3 R2, R0, 1, RZ ; EXIT
    // LDC/IADD3 are NOT in the default lowered set -> interpreter fallback.
    const auto cubin = make_one_param_cubin(
        "_Z4kmockv", {kLdc380, kMovR1R0, kIaddR2, kExit});
    auto ctx = semu::Context::create(
        std::make_shared<semu::MockBackend>());
    if (!ctx.ok()) { CHECK(false); return; }
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4kmockv");
    if (!fn.ok()) { CHECK(fn.ok()); return; }

    // param0 = 0x12345678 (8 bytes).  The mock slices the SERVICE constant
    // bank at 0x380 into the interpreter's params, so R0 must observe it.
    semu::LaunchConfig cfg;
    auto res = ctx.value().launch(fn.value(), cfg,
                                  {semu::KernelArg::integer(0x12345678, "p0")});
    // The launch must SUCCEED (fallback ran the interpreter).
    CHECK(res.ok());
    if (!res.ok()) {
        std::fprintf(stderr, "mock fallback launch failed: %s\n",
                     res.take_error().describe().c_str());
        return;
    }

    const auto* bk = dynamic_cast<const semu::MockBackend*>(ctx.value().backend().get());
    CHECK(bk != nullptr);
    if (!bk) return;
    const auto& st = bk->stats();
    CHECK_EQ(st.kernel, std::string("_Z4kmockv"));
    CHECK(st.words_seen == 4);
    CHECK(st.lowered == 2);             // MOV + EXIT
    CHECK(st.interpreter_fallback == 2);  // LDC + IADD3
    CHECK(!st.decode_only_fault.has_value());
    CHECK(st.decode_only_mnemonics.empty());
    CHECK(st.interpreter_ran);
    CHECK(!st.interpreter_fault.has_value());
    CHECK(st.interpreter_dynamic_instructions > 0);
    CHECK(st.service_constant_bank_reads >= 1);
    CHECK(st.interpreter_result.has_value());
    if (!st.interpreter_result) return;
    const auto& t = st.interpreter_result->ctas[0].warps[0].threads[0];
    // R0 read param0 via LDC through the service constant bank.
    CHECK(t.gpr[0] == 0x12345678u);
    // R1 = MOV R0.
    CHECK(t.gpr[1] == 0x12345678u);
    // R2 = R0 + 1 via IADD3 (interpreter fallback path).
    CHECK(t.gpr[2] == 0x12345679u);
}

// ---------------------------------------------------------------------------
// Lowered-only launch: no interpreter run needed, clean success.
// ---------------------------------------------------------------------------
TEST(mock_backend_lowered_only) {
    // MOV R3, 42 ; EXIT — both in the default lowered set.
    const auto cubin = make_one_param_cubin("_Z4kmockv",
                                            {kMov32iR3, kExit});
    auto ctx = semu::Context::create(
        std::make_shared<semu::MockBackend>());
    if (!ctx.ok()) { CHECK(false); return; }
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4kmockv");
    if (!fn.ok()) { CHECK(fn.ok()); return; }
    auto res = ctx.value().launch(fn.value(), semu::LaunchConfig{}, {semu::KernelArg::integer(0, "p")});
    CHECK(res.ok());
    if (!res.ok()) return;
    const auto* bk = dynamic_cast<const semu::MockBackend*>(ctx.value().backend().get());
    CHECK(bk != nullptr);
    if (!bk) return;
    const auto& st = bk->stats();
    CHECK(st.words_seen == 2);
    CHECK(st.lowered == 2);
    CHECK(st.interpreter_fallback == 0);
    CHECK(!st.interpreter_ran);
    CHECK(!st.decode_only_fault.has_value());
}

// ---------------------------------------------------------------------------
// Decode-only fault path: the TMA family cannot be lowered -> the fault ABI
// reports FaultKind::kUnsupportedInstruction and nothing executes.
// ---------------------------------------------------------------------------
TEST(mock_backend_decode_only_fault_utmaldg) {
    const auto cubin = make_one_param_cubin("_Z4ktmav", {kUtmaldg, kExit});
    auto ctx = semu::Context::create(
        std::make_shared<semu::MockBackend>());
    if (!ctx.ok()) { CHECK(false); return; }
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4ktmav");
    if (!fn.ok()) { CHECK(fn.ok()); return; }
    auto res = ctx.value().launch(fn.value(), semu::LaunchConfig{}, {semu::KernelArg::integer(0, "p")});
    CHECK(res.failed());
    if (!res.failed()) return;
    const auto err = res.take_error();
    // The fault is surfaced through the Error model (Fault IS an Error).
    CHECK(err.code() == semu::ErrorCode::kFault ||
          err.code() == semu::ErrorCode::kDecodeUnsupported ||
          err.code() == semu::ErrorCode::kUnimplemented);
    const auto* bk = dynamic_cast<const semu::MockBackend*>(ctx.value().backend().get());
    CHECK(bk != nullptr);
    if (!bk) return;
    const auto& st = bk->stats();
    CHECK(st.decode_only_fault.has_value());
    if (!st.decode_only_fault) return;
    CHECK(st.decode_only_fault->kind() ==
          semu::FaultKind::kUnsupportedInstruction);
    CHECK(st.decode_only_fault->mnemonic() == std::string("UTMALDG"));
    CHECK(st.decode_only_fault->kernel() == std::string("_Z4ktmav"));
    CHECK(st.decode_only_fault->pc().has_value());
    CHECK(!st.interpreter_ran);
}

TEST(mock_backend_decode_only_fault_utmastg) {
    const auto cubin = make_one_param_cubin("_Z4ktmav", {kUtmastg, kExit});
    auto ctx = semu::Context::create(
        std::make_shared<semu::MockBackend>());
    if (!ctx.ok()) { CHECK(false); return; }
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4ktmav");
    if (!fn.ok()) { CHECK(fn.ok()); return; }
    auto res = ctx.value().launch(fn.value(), semu::LaunchConfig{}, {semu::KernelArg::integer(0, "p")});
    CHECK(res.failed());
    if (!res.failed()) return;
    const auto* bk = dynamic_cast<const semu::MockBackend*>(ctx.value().backend().get());
    CHECK(bk != nullptr);
    if (!bk) return;
    const auto& st = bk->stats();
    CHECK(st.decode_only_fault.has_value() &&
          st.decode_only_fault->kind() ==
              semu::FaultKind::kUnsupportedInstruction);
    CHECK(st.decode_only_fault->mnemonic() == std::string("UTMASTG"));
    CHECK(!st.interpreter_ran);
}

TEST(mock_backend_decode_only_fault_utmaredg) {
    const auto cubin = make_one_param_cubin("_Z4ktmav", {kUtmaredg, kExit});
    auto ctx = semu::Context::create(
        std::make_shared<semu::MockBackend>());
    if (!ctx.ok()) { CHECK(false); return; }
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4ktmav");
    if (!fn.ok()) { CHECK(fn.ok()); return; }
    auto res = ctx.value().launch(fn.value(), semu::LaunchConfig{}, {semu::KernelArg::integer(0, "p")});
    CHECK(res.failed());
    if (!res.failed()) return;
    const auto* bk = dynamic_cast<const semu::MockBackend*>(ctx.value().backend().get());
    CHECK(bk != nullptr);
    if (!bk) return;
    const auto& st = bk->stats();
    CHECK(st.decode_only_fault.has_value() &&
          st.decode_only_fault->kind() ==
              semu::FaultKind::kUnsupportedInstruction);
    CHECK(st.decode_only_fault->mnemonic() == std::string("UTMAREDG"));
    CHECK(!st.interpreter_ran);
}

// Same TMA coverage through the CAPABILITY MANIFEST (not the forced-decode-only
// list): clear the forced list and confirm the manifest still faults TMA.
TEST(mock_backend_tma_fault_via_manifest) {
    semu::MockBackend::Policy policy;
    policy.forced_decode_only.clear();  // manifest is the only authority
    auto bk = std::make_shared<semu::MockBackend>(std::move(policy));
    // Safety: the manifest must actually mark TMA decode-only.
    for (const auto* e :
         semu::CapabilityManifest::current().by_mnemonic("UTMALDG")) {
        CHECK(e->state == semu::CapabilityState::kDecodeOnly);
    }
    auto ctx = semu::Context::create(bk);
    if (!ctx.ok()) { CHECK(false); return; }
    const auto cubin = make_one_param_cubin("_Z4ktmav", {kUtmaldg, kExit});
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4ktmav");
    if (!fn.ok()) { CHECK(fn.ok()); return; }
    auto res = ctx.value().launch(fn.value(), semu::LaunchConfig{}, {semu::KernelArg::integer(0, "p")});
    CHECK(res.failed());
    if (!res.failed()) return;
    const auto& st = bk->stats();
    CHECK(st.decode_only_fault.has_value() &&
          st.decode_only_fault->kind() ==
              semu::FaultKind::kUnsupportedInstruction);
    CHECK(st.decode_only_fault->mnemonic() == std::string("UTMALDG"));
}

// ---------------------------------------------------------------------------
// Runtime-services access: the mock performs a device memory write + read
// round-trip through IRuntimeServices; the caller observes the magic byte.
// ---------------------------------------------------------------------------
TEST(mock_backend_runtime_services_probe) {
    auto bk = std::make_shared<semu::MockBackend>();
    auto ctx = semu::Context::create(bk);
    if (!ctx.ok()) { CHECK(false); return; }
    const auto cubin = make_one_param_cubin("_Z4kmockv", {kMov32iR3, kExit});
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4kmockv");
    if (!fn.ok()) { CHECK(fn.ok()); return; }

    // A live global allocation the mock may write through the services.
    auto ptr = ctx.value().memory().allocate(semu::AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    if (!ptr.ok()) return;
    bk->set_service_probe(ptr.value());

    auto res = ctx.value().launch(fn.value(), semu::LaunchConfig{}, {semu::KernelArg::integer(0, "p")});
    CHECK(res.ok());
    if (!res.ok()) return;
    std::uint64_t magic = 0;
    CHECK(ctx.value().memory().read(ptr.value(), &magic, sizeof(magic)).ok());
    // The mock's magic (0x4D4F434B5B5B4247 "MOCK[BG") must be observable.
    CHECK(magic == 0x4D4F434B5B5B4247ULL);
    CHECK(bk->stats().service_probe_writes == 1);
    CHECK(bk->stats().service_probe_reads == 1);
}

// ---------------------------------------------------------------------------
// Fallback through the Context launch path with a global buffer: the mock
// feeds the interpreter a caller-owned global buffer (LDG reads it).
// ---------------------------------------------------------------------------
TEST(mock_backend_fallback_with_global_memory) {
    // MOV32I R0, 0 ; MOV32I R1, 0; LDG.E R2, desc[{UR4,UR5}][{R0,R1}] ; EXIT
    // (LDG is not lowered -> interpreter fallback; the global buffer contents
    //  must be observable in R2.)
    const auto cubin = make_one_param_cubin("_Z4kmemv",
        {{0x0000000000007802ULL, 0x001fca0000000f00ULL},  // MOV32I R0, 0
         {0x0000000000017802ULL, 0x001fca0000000f00ULL},  // MOV32I R1, 0
         {0x0000000400047981ULL, 0x001fd0000c1e1900ULL},  // LDG.E R4, desc[UR4][R0]
         kExit});
    std::vector<std::uint8_t> global(64, 0);
    global[0] = 0xAB;
    global[1] = 0xCD;
    global[2] = 0xEF;
    global[3] = 0x01;
    semu::MockBackend::Policy policy;
    policy.lowered = {"MOV", "EXIT", "NOP"};
    policy.global_buffer = &global;
    auto bk = std::make_shared<semu::MockBackend>(std::move(policy));
    auto ctx = semu::Context::create(bk);
    if (!ctx.ok()) { CHECK(false); return; }
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z4kmemv");
    if (!fn.ok()) { CHECK(fn.ok()); return; }
    auto res = ctx.value().launch(fn.value(), semu::LaunchConfig{}, {semu::KernelArg::integer(0, "p")});
    CHECK(res.ok());
    if (!res.ok()) return;
    const auto& st = bk->stats();
    CHECK(st.interpreter_ran);
    CHECK(!st.interpreter_fault.has_value());
    CHECK(st.interpreter_fallback >= 1);  // LDG
    if (!st.interpreter_result) return;
    // R4 must hold the seeded 0x01EFCDAB little-endian word.
    const auto& t = st.interpreter_result->ctas[0].warps[0].threads[0];
    CHECK(t.gpr[4] == 0x01EFCDABu);
}

// ---------------------------------------------------------------------------
// Interface-freeze smoke: the version markers exist and are stable.
// ---------------------------------------------------------------------------
TEST(mock_backend_freeze_markers) {
    CHECK(semu::kBackendApiVersion == 1);
    CHECK(semu::kDecodedIrVersion == 2);
    CHECK(semu::kRuntimeServicesVersion == 1);
    CHECK(semu::kEventStreamVersion == 1);
    CHECK(semu::kFaultAbiVersion == 1);
    CHECK(semu::kErrorModelVersion == std::string("1"));
}

// ---------------------------------------------------------------------------
// Phase 10 tensor boundary: the frozen decode-only boundary must hold for the
// non-dense tensor alternatives.  Dense F32-accumulator shapes (hmma_x8_ /
// qmma_ / omma_scale_) are functional -> interpreter fallback; sparse / scale
// / MXQMMA variants are decode-only -> FaultKind::kUnsupportedInstruction.
// ---------------------------------------------------------------------------

// Dense HMMA.16816.F32.BF16 kernel (words identical to test_interp.cpp
// interp_phase9_hmma_bf16_k16): A=B=1.0 bf16, C=10..13 -> D=18,19,20,21 in
// R28..R31.  HMMA is functional but not in the mock's lowered set, so the
// launch falls back to the reference interpreter and SUCCEEDS with the GPR
// result verifiable.
TEST(mock_backend_dense_tensor_falls_back) {
    const auto cubin = make_one_param_cubin("_Z8ktensorv", kDenseHmmaKernel);
    auto ctx = semu::Context::create(std::make_shared<semu::MockBackend>());
    if (!ctx.ok()) { CHECK(false); return; }
    auto mod = ctx.value().load_module(cubin, "mock");
    if (!mod.ok()) { CHECK(mod.ok()); return; }
    auto fn = ctx.value().function(mod.value(), "_Z8ktensorv");
    if (!fn.ok()) { CHECK(fn.ok()); return; }

    // One full warp, as the interpreter's own HMMA test uses.
    semu::LaunchConfig cfg;
    cfg.block_x = 32;
    auto res = ctx.value().launch(fn.value(), cfg,
                                  {semu::KernelArg::integer(0, "p")});
    CHECK(res.ok());
    if (!res.ok()) return;
    const auto* bk =
        dynamic_cast<const semu::MockBackend*>(ctx.value().backend().get());
    CHECK(bk != nullptr);
    if (!bk) return;
    const auto& st = bk->stats();
    CHECK(st.words_seen == 13);
    CHECK(st.lowered == 12);              // 10 MOV + NOP + EXIT
    CHECK(st.interpreter_fallback == 1);  // the HMMA word
    CHECK(!st.decode_only_fault.has_value());
    CHECK(st.interpreter_ran);
    CHECK(!st.interpreter_fault.has_value());
    CHECK(st.interpreter_dynamic_instructions > 0);
    CHECK(st.interpreter_result.has_value());
    if (!st.interpreter_result) return;
    // The dense HMMA fallback must have computed D = 18,19,20,21 (R28..R31),
    // matching test_interp.cpp's interp_phase9_hmma_bf16_k16.
    const auto& t = st.interpreter_result->ctas[0].warps[0].threads[0];
    CHECK(t.gpr[28] == 0x41900000u);
    CHECK(t.gpr[29] == 0x41980000u);
    CHECK(t.gpr[30] == 0x41a00000u);
    CHECK(t.gpr[31] == 0x41a80000u);
}

// Sparse / scale tensor words must fault through the fault ABI (decode-only
// boundary fires BEFORE any interpreter fallback) and nothing executes.
TEST(mock_backend_non_dense_tensor_decode_only) {
    const struct {
        std::string mnemonic;
        std::string variant;
        std::pair<std::uint64_t, std::uint64_t> word;
    } kCases[] = {
        {"HMMA", "hmma_sparse_", kHmmaSparseWord},
        {"OMMA", "omma_sp_scale_", kOmmaSpScaleWord},
        {"MXQMMA", "mxqmma_scale_", kMxQmmaScaleWord},
    };
    for (const auto& c : kCases) {
        const auto cubin = make_one_param_cubin("_Z8ktmav", {c.word, kExit});
        auto ctx = semu::Context::create(std::make_shared<semu::MockBackend>());
        if (!ctx.ok()) { CHECK(false); continue; }
        auto mod = ctx.value().load_module(cubin, "mock");
        if (!mod.ok()) { CHECK(mod.ok()); continue; }
        auto fn = ctx.value().function(mod.value(), "_Z8ktmav");
        if (!fn.ok()) { CHECK(fn.ok()); continue; }
        auto res = ctx.value().launch(
            fn.value(), semu::LaunchConfig{},
            {semu::KernelArg::integer(0, "p")});
        CHECK(res.failed());
        if (!res.failed()) continue;
        const auto* bk = dynamic_cast<const semu::MockBackend*>(
            ctx.value().backend().get());
        CHECK(bk != nullptr);
        if (!bk) continue;
        const auto& st = bk->stats();
        CHECK(st.decode_only_fault.has_value());
        if (!st.decode_only_fault) continue;
        CHECK(st.decode_only_fault->kind() ==
              semu::FaultKind::kUnsupportedInstruction);
        CHECK(st.decode_only_fault->mnemonic() == c.mnemonic);
        CHECK(st.decode_only_fault->variant() == c.variant);
        CHECK(!st.interpreter_ran);
    }
}

int main() { return semu_test::run_all("mock_backend"); }