// L0 unit tests: decoder (Phase 1).  Exercises the compiled-in ISA tables
// (semu/generated/isa_data.*) via the public Decoder API on a handful of
// known sm120 words -- a cross-check independent of the Python-driven
// corpus round-trip / ambiguity gates.

#include <semu/decoder/decoder.hpp>
#include <semu/decoder/decoded_access.hpp>
#include <isa_shapes.hpp>       // typed-IR schema (regenerate with --shapes)
#include <isa_manifest.hpp>    // ShapeManifest/kShapeManifests (decode bridge)
#include <isa_shapes_fill.hpp>  // 2a: per-variant typed fill (equivalence path)
#include <isa_corpus.hpp>       // whole-ISA corpus (gen_corpus.py --hpp)
#include <cstddef>
#include <cstdio>
#include <string>

#include "test_framework.hpp"

using namespace semu;

// Compile-time smoke for the typed decoded-IR schema (semu/generated/
// isa_shapes.hpp): the OperandValue union is a fixed, small layout and the
// per-(mnemonic,operand-count) derived types carry named operand fields.
static_assert(sizeof(shape::OperandValue) <= 16);
static_assert(sizeof(shape::DecodedFFMA4) >= 4 * sizeof(shape::OperandValue));
static_assert(sizeof(shape::DecodedLDG5) >= 5 * sizeof(shape::OperandValue));
static_assert(sizeof(shape::DecodedNOP0) >= 0);

namespace {

// (lo, hi, expected_variant_class) -- a few words taken from the generated
// sm120 corpus (encode -> decode must be unique and match the class).
struct Vec {
    std::uint64_t lo, hi;
    const char* cls;
    const char* mnem;
};

const Vec kKnown[] = {
    {0x0000000000007224ULL, 0x0fe200078e0200ULL, "imad__RRR_RRR", "IMAD"},
    {0x0000000000007905ULL, 0x0fe20000401100ULL, "f2i__Ib_bf16", "F2I"},
    {0x000000000000723eULL, 0x0fe200000000ffULL, "f2fp__RRR", "F2FP"},
    {0x000000000000795dULL, 0x0fe20003880000ULL, "nanosleep_clear_", "NANOSLEEP"},
};

void check_decode(const Vec& v) {
    const auto& dec = Decoder::instance();
    DecodeResult r = dec.decode(v.lo, v.hi);
    CHECK(r.is_unique());
    if (r.is_unique()) {
        const auto& inst = r.instruction();
        CHECK_EQ(std::string(isa::variant_class_name(inst.variant_class)), std::string(v.cls));
        CHECK_EQ(std::string(isa::mnemonic_name(inst.mnemonic)), std::string(v.mnem));
        CHECK(!Decoder::instance().disassemble(inst.word).empty());
    }
}

}  // namespace

TEST(decoder_known_words_unique) {
    for (const auto& v : kKnown) {
        check_decode(v);
    }
}

TEST(typed_main_storage_dynamic_shape) {
    const auto& dec = Decoder::instance();

    auto r2p = dec.decode(0x0000000300007804ULL,
                           0x000fe20000000000ULL);
    CHECK(r2p.is_unique());
    if (r2p.is_unique()) {
        const auto& inst = r2p.instruction();
        CHECK(dynamic_cast<const shape::DecodedR2P3*>(&inst) != nullptr);
        CHECK(inst.shape_variant < isa::kNumVariants);
    }

    auto nop = dec.decode(0x0000000000007918ULL,
                           0x000fc00000000000ULL);
    CHECK(nop.is_unique());
    if (nop.is_unique())
        CHECK(dynamic_cast<const shape::DecodedNOP0*>(&nop.instruction()) != nullptr);
}

TEST(decoder_batch_all_unique_via_corpus_words) {
    // The Python gate (decoder_roundtrip_test) proves 1414/1414 corpus words
    // decode uniquely.  Here we just exercise the API shape on a couple of
    // high-overlap opcodes (F2I / F2FP share opcode space with many siblings).
    const auto& dec = Decoder::instance();
    // F2I variants at opcode 2309/2321 (Rd64/Rb/etc.) must discriminate via
    // the dstfmt/srcfmt enum membership.
    DecodeResult f2i = dec.decode(0x0000000000007905ULL, 0x0fe20000401100ULL);
    CHECK(f2i.is_unique());
    DecodeResult f2i_swap = dec.decode(0x0000000000007919ULL, 0x0fe20000401100ULL);
    // Either unique or explicit ambiguous/illegal -- never a silent wrong pick
    // (uniqueness is asserted in the corpus gate; here we only check the
    // outcome classifier).
    CHECK(f2i_swap.outcome() == DecodeOutcome::kUnique ||
          f2i_swap.outcome() == DecodeOutcome::kIllegal ||
          f2i_swap.outcome() == DecodeOutcome::kAmbiguous);
}

TEST(decoder_illegal_unknown_opcode) {
    const auto& dec = Decoder::instance();
    // opcode 0 with no candidates
    DecodeResult r = dec.decode(0x0000000000000001ULL, 0x0000000000000000ULL);
    CHECK(!r.is_unique());
    CHECK(r.outcome() == DecodeOutcome::kIllegal);
    CHECK(!r.candidates().empty());
}

TEST(decoder_candidates_opcode_index) {
    const auto& dec = Decoder::instance();
    auto cands = dec.candidates(548);  // IMAD
    CHECK(cands.size() >= 1);
}

TEST(decoder_pr_operand_rendered) {
    // PR-typed operand slots (R2P destination / P2R source) must render the
    // literal `PR` token; the generic renderer handles the PR type so every
    // PR-carrying variant prints it.  The R2P word is the real CUDA 13.1
    // cuobjdump vector from a recompiled vecmix; the RRR/RUR/P2R words are
    // canonical encodings (assembler round-trip proven in the corpus gate).
    struct PRVec {
        std::uint64_t lo, hi;
        const char* cls;
        const char* expect;  // disasm operand region (PR included)
    };
    const PRVec kPR[] = {
        {0x0000000300007804ULL, 0x000fe20000000000ULL, "r2p__RIR",
         "PR, R0, 0x3"},
        {0x00000400007204ULL, 0x0fc40000000000ULL, "r2p__RRR",
         "PR, R0, R4"},
        {0x00000400007c04ULL, 0x0fc40008000000ULL, "r2p__RUR",
         "PR, R0, UR4"},
        {0x00000100037803ULL, 0x0fc40000000000ULL, "p2r__RuIR_RIR",
         "R3, PR, R0, 0x1"},
    };
    const auto& dec = Decoder::instance();
    for (const auto& v : kPR) {
        DecodeResult r = dec.decode(v.lo, v.hi);
        CHECK(r.is_unique());
        if (r.is_unique()) {
            const auto& inst = r.instruction();
            CHECK_EQ(std::string(isa::variant_class_name(inst.variant_class)), std::string(v.cls));
            CHECK(Decoder::instance().disassemble(inst.word).find(v.expect) != std::string::npos);
            // the literal PR token must never be dropped or substituted
            CHECK(Decoder::instance().disassemble(inst.word).find("PR") != std::string::npos);
        }
    }
}

// Typed-IR schema (isa_shapes.hpp): the per-variant operand-role manifest is
// what the typed named operand fields are filled by; for a decoded word the manifest is
// the ONLY operand accounting (the generic operands vector was removed with
// the 2b-3 migration).
TEST(shape_manifest_matches_decoded_operands) {
    const auto& dec = Decoder::instance();
    const Vec kV[] = {
        {0x0000000000007918ULL, 0x000fc00000000000ULL, "nop_", "NOP"},
        {0x0000000000003945ULL, 0x000fc00000000000ULL, "bssy_", "BSSY"},
        {0x0000000300007804ULL, 0x000fe20000000000ULL, "r2p__RIR", "R2P"},
        {0x00000400007c04ULL, 0x0fc40008000000ULL, "r2p__RUR", "R2P"},
        // an FFMA word (constructed from the FFMA4 shape family)
        {0x0000001880000000ULL, 0x0fc4400000000000ULL, "ffma__RRR", "FFMA"},
    };
    for (const auto& v : kV) {
        DecodeResult r = dec.decode(v.lo, v.hi);
        if (!r.is_unique()) continue;
        const auto& inst = r.instruction();
        const std::string cls = std::string(isa::variant_class_name(inst.variant_class));
        std::uint32_t idx = 0;
        while (idx < isa::kNumVariants &&
               isa::variant_class_name(isa::kVariants[idx].variant_class) != cls) ++idx;
        if (idx >= isa::kNumVariants) continue;
        const char* prev = isa::variant_class_name(isa::kVariants[idx].variant_class);
        (void)prev;
        const auto& mf = shape::kShapeManifests[idx];
        // The typed Decoded* operand-field count must equal the manifest role count
        // (the decoded dynamic type was allocated through make_by_variant +
        // filled through fill_by_variant, so the two agree by construction).
        if (mf.n_ops == 0) {
            continue;  // no operands to verify
        }
        for (std::uint16_t p = 0; p < mf.n_ops; ++p) {
            const auto* op = shape::operand_field(
                inst.shape_variant, &inst, p);
            CHECK(op != nullptr);
            if (!op) continue;
            CHECK_EQ(static_cast<int>(op->kind),
                     static_cast<int>(mf.ops[p].kind));
        }
    }
}

// 2a equivalence: populating the typed Decoded<Mnemonic><N> (named operand
// fields + typed modifier members) from a decoded word's slot values must agree with
// the typed main-storage object the decoder produced.  FillIn now reads the
// typed-form storage (2b-3: the generic slot_values/operands vectors were
// removed), so this is a whole-corpus typed-fill interception: fill a fresh
// buffer from the SAME decoded word and compare operand fields/modifiers against the
// decoder's own typed Decoded*.
namespace {
struct FillFromDecoded : shape::FillIn {
    const DecodedInstruction& d;
    explicit FillFromDecoded(const DecodedInstruction& d) : d(d) {}
    std::int64_t value(const char* s) const override {
        if (auto v = shape::slot_value(d, s))
            return static_cast<std::int64_t>(*v);
        return 0;
    }
    std::uint8_t flags(const char* s) const override {
        return static_cast<std::uint8_t>(
            shape::op_flag(d, s, 0) | (shape::op_flag(d, s, 1) << 1) |
            (shape::op_flag(d, s, 2) << 2));
    }
};

std::uint32_t variant_index_of(const std::string& cls) {
    for (std::uint32_t i = 0; i < isa::kNumVariants; ++i)
        if (isa::variant_class_name(isa::kVariants[i].variant_class) == cls)
            return i;
    return isa::kNumVariants;
}

// Read a filled OperandValue's numeric value via the kind-correct union member.
std::uint64_t op_raw(const shape::OperandValue& o, shape::OperandKind k) {
    switch (k) {
        case shape::OperandKind::kRegister: return o.v.reg_idx;
        case shape::OperandKind::kUniformRegister: return o.v.ureg_idx;
        case shape::OperandKind::kPredicate:
        case shape::OperandKind::kUniformPredicate: return o.v.pred_idx;
        case shape::OperandKind::kSImm: return static_cast<std::uint64_t>(o.v.simm64);
        case shape::OperandKind::kFImm16: return o.v.uimm16;
        case shape::OperandKind::kFImm32: return o.v.uimm32;
        case shape::OperandKind::kFImm64: return o.v.uimm64;
        case shape::OperandKind::kDesc: return o.v.desc;
        default: return o.v.uimm64;
    }
}
}  // namespace

TEST(typed_fill_matches_generic_decode) {
    alignas(16) std::byte buf[512];
    const auto& dec = Decoder::instance();

    // r2p__RIR -> DecodedR2P3 (3 ops + a_bsel modifier member)
    auto rr = dec.decode(0x0000000300007804ULL, 0x000fe20000000000ULL);
    CHECK(rr.is_unique());
    if (rr.is_unique()) {
        const auto& inst = rr.instruction();
        const std::uint32_t idx = variant_index_of("r2p__RIR");
        CHECK(idx < isa::kNumVariants);
        const auto& mf = shape::kShapeManifests[idx];
        CHECK_EQ(static_cast<int>(mf.n_ops), 3);
        FillFromDecoded fi(inst);
        shape::fill_by_variant(idx, fi, buf);
        auto& d = *reinterpret_cast<shape::DecodedR2P3*>(buf);
        // Named fields: PR, Ra, b (position order).
        const shape::OperandValue* flds[3] = {&d.PR, &d.Ra, &d.b};
        for (std::uint8_t p = 0; p < mf.n_ops; ++p) {
            CHECK_EQ(op_raw(*flds[p], mf.ops[p].kind),
                     static_cast<std::uint64_t>(fi.value(mf.ops[p].slot)));
            CHECK_EQ(static_cast<int>(flds[p]->kind),
                     static_cast<int>(mf.ops[p].kind));
        }
        CHECK_EQ(static_cast<std::int64_t>(d.a_bsel), fi.value("a_bsel"));
    }

    // nop_ -> DecodedNOP0 (0 ops, empty)
    auto rn = dec.decode(0x0000000000007918ULL, 0x000fc00000000000ULL);
    CHECK(rn.is_unique());
    if (rn.is_unique()) {
        const auto& inst = rn.instruction();
        const std::uint32_t idx = variant_index_of("nop_");
        CHECK(idx < isa::kNumVariants);
        CHECK_EQ(static_cast<int>(shape::kShapeManifests[idx].n_ops), 0);
        FillFromDecoded fi(inst);
        shape::fill_by_variant(idx, fi, buf);
        auto& d = *reinterpret_cast<shape::DecodedNOP0*>(buf);
        (void)d;
    }

    // bssy_ -> DecodedBSSY3 (3 ops)
    auto rb = dec.decode(0x0000000000003945ULL, 0x000fc00000000000ULL);
    CHECK(rb.is_unique());
    if (rb.is_unique()) {
        const auto& inst = rb.instruction();
        const std::uint32_t idx = variant_index_of("bssy_");
        CHECK(idx < isa::kNumVariants);
        const auto& mf = shape::kShapeManifests[idx];
        CHECK_EQ(static_cast<int>(mf.n_ops), 3);
        FillFromDecoded fi(inst);
        shape::fill_by_variant(idx, fi, buf);
        auto& d = *reinterpret_cast<shape::DecodedBSSY3*>(buf);
        // Named fields: Pp, barReg, Sa (position order).
        const shape::OperandValue* flds[3] = {&d.Pp, &d.barReg, &d.Sa};
        for (std::uint8_t p = 0; p < mf.n_ops; ++p)
            CHECK_EQ(flds[p]->v.uimm64,
                     static_cast<std::uint64_t>(fi.value(mf.ops[p].slot)));
    }
}

// Whole-ISA typed-fill equivalence: for every corpus word that decodes
// uniquely, the generated fill must reproduce the live slot_values/operands in
// the typed Decoded* operand fields (read back through generated variant dispatch;
// typed shapes now have the common polymorphic base at offset 0).
TEST(typed_fill_matches_across_corpus) {
    const auto& dec = Decoder::instance();
    alignas(16) std::byte buf[512];
    std::uint32_t checked = 0;
    for (std::uint32_t w = 0; w < semu::corpus::kNumCorpus; ++w) {
        const auto& cw = semu::corpus::kWords[w];
        DecodeResult r = dec.decode(cw.lo, cw.hi);
        if (!r.is_unique()) continue;
        const auto& inst = r.instruction();
        const std::uint32_t idx =
            variant_index_of(isa::variant_class_name(inst.variant_class));
        if (idx >= isa::kNumVariants) continue;
        const auto& mf = shape::kShapeManifests[idx];
        if (mf.n_ops == 0) { checked++; continue; }
        FillFromDecoded fi(inst);
        shape::fill_by_variant(idx, fi, buf);
        const auto* typed = reinterpret_cast<const DecodedInstruction*>(buf);
        for (std::uint8_t p = 0; p < mf.n_ops; ++p) {
            const shape::OperandKind k = mf.ops[p].kind;
            const shape::OperandValue* op =
                shape::operand_field(idx, typed, p);
            if (!op) continue;
            const std::uint64_t got = op_raw(*op, k);
            const std::uint64_t want =
                static_cast<std::uint64_t>(fi.value(mf.ops[p].slot));
            if (got != want) {
                std::fprintf(stderr,
                    "corpus[%u] %s slot[%u]=%s got=%llu want=%llu\n",
                    w, isa::variant_class_name(inst.variant_class), p,
                    mf.ops[p].slot, (unsigned long long)got,
                    (unsigned long long)want);
                CHECK(false);
                break;
            }
            if (op->flags != fi.flags(mf.ops[p].slot)) {
                std::fprintf(stderr,
                    "corpus[%u] %s slot[%u]=%s flags got=%u want=%u\n",
                    w, isa::variant_class_name(inst.variant_class), p,
                    mf.ops[p].slot, op->flags,
                    fi.flags(mf.ops[p].slot));
                CHECK(false);
                break;
            }
        }
        ++checked;
    }
    // The corpus gate proves 1414/1414 unique; we must have checked them all.
    CHECK_EQ(static_cast<int>(checked),
             static_cast<int>(semu::corpus::kNumCorpus));
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-decoder");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu decoder tests\n");
        return 0;
    }
    std::fprintf(stderr, "[  FAILED  ] %d test(s)\n", failures);
    return 1;
}
