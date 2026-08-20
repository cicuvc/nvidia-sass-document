#pragma once

// Internal decoder plumbing shared between decoder.cpp (pipeline) and
// render.cpp (disassembly rendering).  Not a public API.

#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include <semu/decoder.hpp>
#include <semu/word.hpp>

#include "expr.hpp"

namespace semu::isa {
struct Variant;
struct Field;
}

namespace semu {

struct DecodeCtx {
    const isa::Variant* variant = nullptr;
    Word128 word{};
    std::unordered_map<std::string, std::int64_t> sm;
    std::vector<std::pair<const isa::Field*, std::uint64_t>> fields;
};

const decoder::IsaData& isa_data();
std::uint64_t extract_field(const isa::Field& f, Word128 w);

// Parse an integer literal (0x/0b/decimal); false when not fully consumed.
bool parse_int_full(std::string_view s, std::int64_t* out);
std::int64_t parse_int(std::string_view s);

// Recover a format slot's decoded value (reverse of the encoder).
std::optional<std::int64_t> slot_value(const DecodeCtx& ctx,
                                       const std::string& name);
// slot@attr flag (0 when absent).
std::int64_t slot_attr_val(const DecodeCtx& ctx, const std::string& name,
                           const std::string& attr);

// Render a fully-decoded variant into a DecodedInstruction (render.cpp).
std::unique_ptr<DecodedInstruction> render_instruction(const isa::Variant* v,
                                                       Word128 word,
                                                       const DecodeCtx& ctx);

// Render the normalized disassembly text for an already-decoded instruction
// (render.cpp).  Needs the variant + decode context to re-render operands.
// `full` includes the guard predicate + schedule bracket.
std::string render_disasm_text(const isa::Variant* v, const DecodeCtx& ctx,
                               const DecodedInstruction& inst, bool full);


}  // namespace semu
