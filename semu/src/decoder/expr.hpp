#pragma once

// Port of assembler/sass_cond.py: evaluates the sm120 legality-condition
// predicate language against a slot map.  Used both for variant
// disambiguation (conditions) and register-width size predicates (eval_int).

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace semu {
namespace isa {
struct EnumDef;
struct TableDef;
}

namespace decoder {

// Precomputed ISA lookup tables built once from the generated data.
struct IsaData {
    std::unordered_map<std::string, const isa::EnumDef*> enums;
    std::unordered_map<std::string, const isa::TableDef*> tables;
    std::unordered_map<std::string, std::int64_t> parameters;
    std::unordered_map<std::string, std::int64_t> constants;

    // value of `Type@Name (returns nullopt when unresolvable).
    std::optional<std::int64_t> enum_value(std::string_view type,
                                           std::string_view name) const;
    // name for an enum value (prefers non-INVALID / non-fp8 / non-"no" names),
    // matching the reference disassembler's preference order.
    std::optional<std::string> enum_name(std::string_view type,
                                         std::int64_t value) const;
    std::optional<std::string> enum_first(std::string_view type) const;
    // True when `type` is an enum type in the DB and `value` is a member.
    bool enum_has_value(std::string_view type, std::int64_t value) const;
    std::optional<std::int64_t> parameter(std::string_view name) const;
    std::optional<std::int64_t> constant(std::string_view name) const;
    const isa::TableDef* table(std::string_view name) const;
};

// Table row membership + reverse lookup helpers.
// rows: `in` args are comma-joined; returns arg index split.
std::vector<std::string> split_row_args(std::string_view in);

class ExprEvaluator {
public:
    explicit ExprEvaluator(const IsaData& data) : data_(data) {}

    void set_slots(const std::unordered_map<std::string, std::int64_t>& sm) {
        slots_ = &sm;
    }

    // Predicate evaluation; parse/resolve failures return true (never falsely
    // reject an encoding).
    bool eval_bool(std::string_view predicate);

    // Three-state predicate evaluation (GAP-04): returns true/false when the
    // predicate fully parsed and resolved, nullopt when the tokenizer or
    // grammar hit something unsupported (unknown char, unconsumed tokens,
    // unresolvable reference).  Legality decisions must never treat an
    // unresolved predicate as authoritative.
    std::optional<bool> eval_bool_tristate(std::string_view predicate);

    // Arithmetic (size) evaluation; failures return nullopt.
    std::optional<std::int64_t> eval_int(std::string_view predicate);

    // Direct slot access used by the renderer (0 when absent).
    std::int64_t slot(std::string_view name) const;
    std::int64_t slot_attr(std::string_view slot, std::string_view attr) const;

    // Tokenizer diagnostics (GAP-04): true when the last tokenize() saw a
    // character it could not classify.
    bool had_unknown_char() const { return had_unknown_char_; }

private:
    const IsaData& data_;
    const std::unordered_map<std::string, std::int64_t>* slots_ = nullptr;
    std::vector<std::pair<int, std::string>> toks_;
    std::size_t pos_ = 0;
    bool had_unknown_char_ = false;

    void tokenize(std::string_view pred);
    std::optional<std::int64_t> eval();
    std::optional<std::int64_t> or_expr();
    std::optional<std::int64_t> and_expr();
    std::optional<std::int64_t> bitand_expr();
    std::optional<std::int64_t> cmp();
    std::optional<std::int64_t> shift();
    std::optional<std::int64_t> add();
    std::optional<std::int64_t> mul();
    std::optional<std::int64_t> unary();
    std::optional<std::int64_t> atom();
    std::optional<std::int64_t> defined();
    std::string resolve_arg();
};

}  // namespace decoder
}  // namespace semu
