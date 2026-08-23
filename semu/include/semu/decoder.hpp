#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <isa_data.hpp>
#include <semu/decoded_base.hpp>
#include <semu/word.hpp>
#include <isa_shapes.hpp>

// FROZEN (SIM_PLAN Phase 10): this header is part of the decoded-IR contract —
// DecodedInstruction / DecodeResult / Operand / ScheduleWord / slot_values /
// raw_fields, the flattened IR execution backends dispatch on
// (kDecodedIrVersion in api.hpp).  Extensions must ADD fields, never remove or
// renumber them.
//
// v1 -> v2 (kDecodedIrVersion bump): mnemonic / variant_class / pipe changed
// from std::string to the generated isa::Mnemonic / isa::VariantClass /
// isa::Pipe enums (see isa_data.hpp), and the disasm / disasm_full fields
// were removed (now rendered on demand via Decoder::disassemble).
// The human-readable names are still available via isa::mnemonic_name() /
// isa::variant_class_name() / isa::pipe_name(), and isa::*_from_name() maps a
// name back to the enum.  Execution backends dispatch on the enum values
// directly (no per-instruction string allocation or comparison), and the
// hot decode/predecode path no longer builds disassembly text it only reads
// under an opt-in trace / debugger / CLI consumer.

// Public decoder API (SIM_PLAN Phase 1).
//
// The decoder turns a raw 128-bit sm120 instruction word into a unique
// DecodedInstruction (mnemonic, variant, typed operands, modifiers, schedule
// word, normalized disassembly) or an explicit illegal / ambiguous result
// with per-candidate reasons.  It consumes only the generated ISA tables
// (semu/generated/isa_data.*); execution backends depend solely on the
// resulting IR.

namespace semu {

namespace isa {
struct Variant;
}

enum class DecodeOutcome {
    kUnique,    // exactly one variant matched
    kIllegal,   // no variant matched (reserved bits / no table row / cond)
    kAmbiguous, // more than one variant matched
};

// One candidate's disposition during an illegal/ambiguous decode.
struct CandidateRejection {
    std::string variant_class;
    std::string reason;  // empty = candidate actually matched (ambiguous set)
};

class DecodeResult {
public:
    DecodeResult() = default;
    DecodeResult(const DecodeResult& o);
    DecodeResult& operator=(const DecodeResult& o);
    DecodeResult(DecodeResult&&) noexcept = default;
    DecodeResult& operator=(DecodeResult&&) noexcept = default;

    DecodeOutcome outcome() const { return outcome_; }
    bool is_unique() const { return outcome_ == DecodeOutcome::kUnique; }
    const DecodedInstruction& instruction() const { return *instruction_; }
    const std::vector<CandidateRejection>& candidates() const {
        return candidates_;
    }

private:
    friend class Decoder;
    DecodeOutcome outcome_ = DecodeOutcome::kIllegal;
    std::unique_ptr<DecodedInstruction> instruction_;
    std::vector<CandidateRejection> candidates_;
};

// Stateless decoder built from the generated ISA tables.
class Decoder {
public:
    static const Decoder& instance();

    DecodeResult decode(Word128 word) const;
    DecodeResult decode(std::uint64_t lo, std::uint64_t hi) const;

    // Render one word's normalized disassembly (re-decodes on demand; empty
    // on illegal/ambiguous).  `full=false` -> plain operands text;
    // `full=true`  -> guard predicate + schedule bracket included.
    std::string disassemble(Word128 word, bool full = false) const;

    // All encoding variants sharing an opcode (in generated order).
    std::vector<const isa::Variant*> candidates(std::uint16_t opcode) const;

private:
    Decoder();
};

}  // namespace semu
