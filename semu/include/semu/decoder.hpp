#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include <isa_data.hpp>
#include <semu/word.hpp>

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

struct Operand {
    std::string slot;   // format slot name
    std::string kind;   // slot type, e.g. "Register" / "SImm"
    std::string text;   // rendered text, e.g. "R8", "-0x10", "c[0x0][0x380]"
    std::int64_t value = 0;
    bool negated = false;
    bool absolute = false;
    bool pred_not = false;
};

// Schedule / control word (bits [124:110] + opex [109:105] + req [121:116]).
struct ScheduleWord {
    int dst_wr_sb = 7;   // bits [112:110], 7 = no scoreboard
    int src_rel_sb = 7;  // bits [115:113]
    int req_bit_set = 0; // bits [121:116]
    int opex = 0;        // bits [124:122] + [109:105]
    int usched = 0;      // opex & 0x1F
    int stall = 0;       // usched & 0xF
    int yield_off = 0;   // 0 = yield, 1 = no-yield (usched >= 16)
    int batch_t = 0;     // opex >> 5 (batch_t or reuse bitfield)
};

class DecodedInstruction {
public:
    Word128 word{};
    std::uint64_t pc = 0;   // byte address (set by the loader/debugger)
    isa::Mnemonic mnemonic = isa::Mnemonic::kUnknown;
    isa::VariantClass variant_class = isa::VariantClass::kUnknown;
    isa::Pipe pipe = isa::Pipe::kUnknown;

    // Guard predicate: 0..6 = P0..P6, 7 = PT (always).
    int guard_pred = 7;
    bool guard_not = false;

    std::vector<Operand> operands;
    std::vector<std::string> modifiers;  // ".MOD" tokens in source order
    ScheduleWord schedule;

    // Normalized disassembly is NOT stored here: it is rendered on demand via
    // Decoder::disassemble(word, full) so the per-instruction hot path (LOAD +
    // per-predecoded-word copies) never pays for disassembly text it never
    // reads.  `full=false` omits the guard + schedule bracket;
    // `full=true` includes both (round-trip-able in the assembler dialect).

    // Raw extracted field values (name -> value) for the debugger.
    std::vector<std::pair<std::string, std::uint64_t>> raw_fields;

    // FORMAT slot values (name -> value) for every non-schedule slot,
    // including modifier slots (rnd/ftz/sat/fcomp/dstfmt.srcfmt/...).  This is
    // the stable interface the interpreter uses for modifier dispatch.
    std::vector<std::pair<std::string, std::uint64_t>> slot_values;

    // Polymorphic: the decoded-IR migration stores concrete instructions as
    // base pointers (PredecodedWord::inst is a unique_ptr) so a future typed
    // derived Decoded<Mnemonic><Ops> can be allocated and deleted through this.
    virtual ~DecodedInstruction() = default;
};

// One candidate's disposition during an illegal/ambiguous decode.
struct CandidateRejection {
    std::string variant_class;
    std::string reason;  // empty = candidate actually matched (ambiguous set)
};

class DecodeResult {
public:
    DecodeOutcome outcome() const { return outcome_; }
    bool is_unique() const { return outcome_ == DecodeOutcome::kUnique; }
    const DecodedInstruction& instruction() const { return instruction_; }
    const std::vector<CandidateRejection>& candidates() const {
        return candidates_;
    }

private:
    friend class Decoder;
    DecodeOutcome outcome_ = DecodeOutcome::kIllegal;
    DecodedInstruction instruction_;
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

// Condition-parser coverage scan (GAP-04 gate): evaluate every legality
// condition of every variant with the built-in default slot values using the
// three-state evaluator.  Returns the number of conditions the parser could
// not fully consume/resolve (0 = full coverage).  `report` receives one line
// per unresolved condition when non-null.
std::size_t scan_condition_parse_gaps(
    bool report, std::size_t* total_conds = nullptr,
    std::size_t* resolved_conds = nullptr);

// Per-condition verdict for a variant against a *specific* word's decoded
// slot map (GAP-09): verdict 1 = true, 0 = false, 2 = unresolved (parser gap
// or unresolvable reference).  Unlike scan_condition_parse_gaps this uses the
// real decoded slot values, so the Python reference evaluator can be compared
// condition-by-condition on identical inputs.
struct ConditionVerdict {
    std::string error;
    std::string predicate;
    int verdict;  // 1 true, 0 false, 2 unresolved
};
// Evaluate every legality condition of the given variant class against the
// word's decoded slot map.  Returns empty when the class is unknown.
std::vector<ConditionVerdict> condition_verdicts(
    const std::string& variant_class, Word128 word);

// Direct three-state evaluation of an arbitrary predicate against an explicit
// slot map (GAP-09): 1 = true, 0 = false, 2 = unresolved (unknown char, parse
// gap, or unconsumed tokens).  This lets tests feed the SAME expression and
// slot values to both the C++ evaluator and the Python reference evaluator.
int eval_predicate(const std::string& predicate,
                   const std::vector<std::pair<std::string, std::int64_t>>&
                       slots);

}  // namespace semu
