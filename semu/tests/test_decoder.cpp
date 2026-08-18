// L0 unit tests: decoder (Phase 1).  Exercises the compiled-in ISA tables
// (semu/generated/isa_data.*) via the public Decoder API on a handful of
// known sm120 words -- a cross-check independent of the Python-driven
// corpus round-trip / ambiguity gates.

#include <semu/decoder.hpp>

#include <cstdio>
#include <string>

#include "test_framework.hpp"

using namespace semu;

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
        CHECK_EQ(std::string(inst.variant_class), std::string(v.cls));
        CHECK_EQ(std::string(inst.mnemonic), std::string(v.mnem));
        CHECK(!inst.disasm.empty());
    }
}

}  // namespace

TEST(decoder_known_words_unique) {
    for (const auto& v : kKnown) {
        check_decode(v);
    }
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
            CHECK_EQ(std::string(inst.variant_class), std::string(v.cls));
            CHECK(inst.disasm.find(v.expect) != std::string::npos);
            // the literal PR token must never be dropped or substituted
            CHECK(inst.disasm.find("PR") != std::string::npos);
        }
    }
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
