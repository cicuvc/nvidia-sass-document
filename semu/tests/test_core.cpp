// L0 unit tests: error model, fault reporting, capability manifest, word/bit
// helpers, version/build info.  No CUDA, no GPU.

#include <semu/capability.hpp>
#include <semu/fault.hpp>
#include <semu/status.hpp>
#include <semu/version.hpp>
#include <semu/word.hpp>

#include <cstdio>
#include <string>

#include "test_framework.hpp"

using namespace semu;

// ---------------------------------------------------------------------------
// Status / Error / cause chain
// ---------------------------------------------------------------------------

TEST(error_basic_construction) {
    Error e = Error::invalid_argument("bad x");
    CHECK(e.code() == ErrorCode::kInvalidArgument);
    CHECK(e.message() == "bad x");
    CHECK(!e.ok());
    CHECK(!e.has_cause());
    CHECK_EQ(std::string(to_string(ErrorCode::kBadCubin)),
             std::string("kBadCubin"));
}

TEST(error_cause_chain) {
    Error root = Error::io_error("disk died");
    Error mid(ErrorCode::kBadCubin, "bad elf", std::move(root));
    Error top(ErrorCode::kNotSupported, "cannot load", std::move(mid));
    CHECK(top.has_cause());
    auto chain = top.cause_chain();
    CHECK(chain.size() == 3);
    CHECK(chain[0]->message() == "cannot load");
    CHECK(chain[1]->message() == "bad elf");
    CHECK(chain[2]->message() == "disk died");
    // describe() flattens message + chain
    std::string d = top.describe();
    CHECK(d.find("cannot load") != std::string::npos);
    CHECK(d.find("disk died") != std::string::npos);
}

TEST(error_context_frames) {
    Error e = Error::not_found("symbol 'foo'");
    e.push_context("while loading kernel 'k'");
    CHECK(e.context().size() == 1);
    std::string s = e.to_string();
    CHECK(s.find("symbol 'foo'") != std::string::npos);
    CHECK(s.find("while loading kernel 'k'") != std::string::npos);
}

TEST(status_ok_and_failure) {
    Status ok = Status::success();
    CHECK(ok.ok());
    CHECK(!ok.failed());

    Status bad = Status::failure(Error::out_of_range("reg 300"));
    CHECK(bad.failed());
    CHECK(bad.error().code() == ErrorCode::kOutOfRange);
}

TEST(status_with_context) {
    Status bad = Status::failure(Error::unimplemented("int8 mm")).with_context(
        "in kernel 'conv'");
    CHECK(bad.failed());
    CHECK(bad.error().context().size() == 1);
}

TEST(result_value_or_error) {
    Result<int> ok = Result<int>::success(42);
    CHECK(ok.ok());
    CHECK_EQ(ok.value(), 42);

    Result<int> bad = Result<int>::failure(Error::internal("boom"));
    CHECK(bad.failed());
    CHECK(bad.status().failed());
}

// ---------------------------------------------------------------------------
// Fault
// ---------------------------------------------------------------------------

TEST(fault_context_and_report) {
    Fault f(FaultKind::kUnsupportedInstruction, "HMMA not implemented");
    f.set_kernel("matmul")
        .set_pc(0x40)
        .set_cta(2)
        .set_warp(3)
        .set_active_mask(0x0000000F)
        .set_instruction(Word128{0x1122334455667788ULL, 0xAABBCCDDEEFF0011ULL})
        .set_mnemonic("HMMA")
        .set_variant("hmma_");
    CHECK(f.kind() == FaultKind::kUnsupportedInstruction);
    CHECK_EQ(std::string(to_string(f.kind())),
             std::string("UnsupportedInstruction"));
    CHECK(f.kernel() && *f.kernel() == "matmul");
    CHECK(f.pc() && *f.pc() == 0x40);
    CHECK(f.cta() && *f.cta() == 2);
    CHECK(f.warp() && *f.warp() == 3);
    CHECK(f.active_mask() && *f.active_mask() == 0x0F);
    CHECK(f.mnemonic() && *f.mnemonic() == "HMMA");
    CHECK(f.variant() && *f.variant() == "hmma_");
    CHECK(f.instruction().has_value());

    std::string rep = f.to_report();
    CHECK(rep.find("kernel: matmul") != std::string::npos);
    CHECK(rep.find("pc: 0x0000000000000040") != std::string::npos);
    CHECK(rep.find("cta: 2") != std::string::npos);
    CHECK(rep.find("warp: 3") != std::string::npos);
    CHECK(rep.find("active_mask: 0x0000000F") != std::string::npos);
    CHECK(rep.find("0xAABBCCDDEEFF0011") != std::string::npos);
    CHECK(rep.find("mnemonic: HMMA") != std::string::npos);
}

TEST(fault_with_cause_chain) {
    Error cause(ErrorCode::kDecodeIllegal, "reserved bits set");
    Fault f(FaultKind::kInvalidInstruction, "bad encoding", std::move(cause));
    CHECK(f.has_cause());
    auto chain = f.cause_chain();
    CHECK(chain.size() == 2);
    std::string rep = f.to_report();
    CHECK(rep.find("reserved bits set") != std::string::npos);
}

// ---------------------------------------------------------------------------
// Capability manifest
// ---------------------------------------------------------------------------

TEST(capability_states_roundtrip) {
    CHECK_EQ(std::string(to_string(CapabilityState::kDecodeOnly)),
             std::string("decode-only"));
    CHECK_EQ(std::string(to_string(CapabilityState::kFunctional)),
             std::string("functional"));
    CHECK_EQ(std::string(to_string(CapabilityState::kProfiled)),
             std::string("profiled"));
    CHECK_EQ(std::string(to_string(CapabilityState::kUnsupported)),
             std::string("unsupported"));
    CHECK(parse_capability_state("functional").has_value());
    CHECK(!parse_capability_state("nope").has_value());
}

TEST(capability_manifest_scale) {
    const auto& m = CapabilityManifest::current();
    const auto& h = m.header();
    CHECK(h.manifest_version == kCapabilityManifestVersion);
    CHECK_EQ(h.arch, std::string("sm120"));
    // frozen sm120 data scale
    CHECK(h.variants == 1414);
    CHECK(h.mnemonics == 259);
    CHECK(h.enums == 451);
    CHECK(h.tables == 89);
    CHECK(h.funit_fields == 2142);
    CHECK(h.pipes == 300);
    CHECK_EQ(std::string(h.generator),
             std::string("semu/tools/gen_capability.py"));
    CHECK(m.entries().size() == 1414);
    // Phase 1 baseline: everything decode-only (decoder uniquely decodes all).
    // Phase 9 promotes the dense F32-accumulator tensor shapes to functional
    // (HMMA hmma_x8_, QMMA qmma_, OMMA omma_scale_) and the TMA/mbarrier
    // subset stays decode-only, so the manifest is 1411 decode-only + 3
    // functional.
    CHECK(m.count(CapabilityState::kDecodeOnly) == 1411);
    CHECK(m.count(CapabilityState::kFunctional) == 3);
    CHECK(m.count(CapabilityState::kUnsupported) == 0);
}

TEST(capability_queries) {
    const auto& m = CapabilityManifest::current();
    auto imad = m.by_mnemonic("IMAD");
    CHECK(imad.size() >= 1);
    // entries are deterministic: (opcode, mnemonic, variant_class) sort
    const auto& first = *imad.front();
    CHECK(first.state == CapabilityState::kDecodeOnly);
    CHECK(!first.pipe.empty());
    CHECK(!first.variant_class.empty());

    auto by_op = m.by_opcode(first.opcode);
    CHECK(by_op.size() >= 1);
}

TEST(capability_json_byte_identical_roundtrip) {
    const auto& m = CapabilityManifest::current();
    const std::string json1 = m.to_json();
    auto parsed = CapabilityManifest::from_json(json1);
    CHECK(parsed.has_value());
    const std::string json2 = parsed->to_json();
    CHECK_EQ(json1, json2);  // byte-for-byte stable serialization
    CHECK(parsed->entries().size() == m.entries().size());
}

// ---------------------------------------------------------------------------
// Word / bit helpers (decoder primitives)
// ---------------------------------------------------------------------------

TEST(word_opcode_extraction) {
    // opcode = {bit[91], bits[11:0]}
    Word128 w{0x0000000000000000ULL, 0x0000000000000000ULL};
    CHECK(opcode_of(w.lo, w.hi) == 0);
    // set bit 91 (hi bit 27) and bits[11:0]
    w.hi |= (1ULL << 27);
    w.lo |= 0x0FFF;
    CHECK(opcode_of(w.lo, w.hi) == 0x1FFF);
}

TEST(word_extract_bits_crossing_boundary) {
    Word128 w{0, 0};
    // field [68:60] spans the lo/hi boundary (bit 64 boundary)
    w.lo |= 0x0FULL << 60;              // bits 63..60 = 0x0F
    w.hi |= 0x0AULL;                    // bits 68..64 = 0x0A
    // value = hi(68:64)<<4 | lo(63:60) = 0x0A * 16 + 0x0F = 0xAF
    CHECK_EQ(extract_bits(w.lo, w.hi, 68, 60), 0xAFULL);
}

TEST(word_extract_multi_range) {
    // two ranges [10:8] and [3:0] concatenated MSB-first
    Word128 w{0, 0};
    w.lo = (0b101ULL << 8) | 0b1100;
    CHECK_EQ(extract_bits(w.lo, w.hi,
                          {BitRange{10, 8}, BitRange{3, 0}}),
             0b1011100ULL);
}

TEST(word_extract_full_64bit_range) {
    // a single 64-bit range must not shift by 64 (UB guard)
    Word128 w{0x0123456789ABCDEFULL, 0xFEDCBA9876543210ULL};
    CHECK_EQ(extract_bits(w.lo, w.hi, 63, 0), w.lo);
    CHECK_EQ(extract_bits(w.lo, w.hi, 127, 64), w.hi);
    // [87:24] is the mov_imm64 Sb field: 64 bits spanning the boundary
    // lo bits [63:24] ++ hi bits [87:64]
    const std::uint64_t expect =
        ((w.hi & 0xFFFFFFULL) << 40) | ((w.lo >> 24) & 0xFFFFFFFFFFULL);
    CHECK_EQ(extract_bits(w.lo, w.hi, 87, 24), expect);
}

TEST(word_extract_boundary_lo_zero) {
    // 64-bit range [70:7] spans the boundary with lo == 7 (lo_w = 57 < 64,
    // so the hi part shifts into place); exercises the boundary path.
    Word128 w{0, 0};
    w.lo |= 0x0FFULL << 7;          // bits [63:7] = 0x1FE ... low 57 bits
    w.hi |= 0x3FULL;                // bits [70:64]
    const std::uint64_t expect =
        (0x3FULL << 57) | ((w.lo >> 7) & 0x1FFFFFFFFFFFFFFULL);
    CHECK_EQ(extract_bits(w.lo, w.hi, 70, 7), expect);
}

TEST(word_sign_extend) {
    // 11-bit signed: range [-1024, 1023]
    CHECK_EQ(sign_extend(0x000, 11), 0);
    CHECK_EQ(sign_extend(0x3FF, 11), 1023);
    CHECK_EQ(sign_extend(0x400, 11), -1024);
    CHECK_EQ(sign_extend(0x7FF, 11), -1);
    CHECK_EQ(sign_extend(0xFFFFFFFFULL, 32), -1);
    CHECK_EQ(sign_extend(0x7FFFFFFFULL, 32), 2147483647);
    CHECK_EQ(sign_extend(0xFFFFFFFFFFFFFFFFULL, 64), -1);
}

// ---------------------------------------------------------------------------
// Version / build info
// ---------------------------------------------------------------------------

TEST(version_string) {
    std::string v = semu_version_string();
    CHECK(v == "0.1.0");
}

TEST(build_info_accessors) {
    // These are defined in every build; only shape is asserted.
    CHECK(!build_cxx_compiler().empty());
    CHECK(!build_mode().empty());
}

// ---------------------------------------------------------------------------

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu core tests\n");
        return 0;
    }
    std::fprintf(stderr, "[  FAILED  ] %d test(s)\n", failures);
    return 1;
}
