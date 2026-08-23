#pragma once

// ISA lookup tables shared by the decoder pipeline and the renderer.
// The former runtime predicate evaluator (a port of assembler/sass_cond.py)
// is gone: legality conditions run through the generated cond_check_* thunks
// and operand widths through the generated metadata SizeFn table, so no
// predicate string is parsed at runtime anymore.  What remains here is the
// data-access layer: enum/table lookups used by build_decode_ctx (reverse
// table_fn slot recovery, star_slot discriminator checks) and by the
// renderer (modifier name printing, enum value resolution).

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

    // value of `Type@Name` (returns nullopt when unresolvable).
    std::optional<std::int64_t> enum_value(std::string_view type,
                                           std::string_view name) const;
    // name for an enum value (prefers non-INVALID / non-fp8 / non-"no" names),
    // matching the reference disassembler's preference order.
    std::optional<std::string> enum_name(std::string_view type,
                                         std::int64_t value) const;
    std::optional<std::string> enum_first(std::string_view type) const;
    // True when `type` is an enum type in the DB and `value` is a member.
    bool enum_has_value(std::string_view type, std::int64_t value) const;
    const isa::TableDef* table(std::string_view name) const;
};

// Table row membership + reverse lookup helpers.
// rows: `in` args are comma-joined; returns arg index split.
std::vector<std::string> split_row_args(std::string_view in);

}  // namespace decoder
}  // namespace semu