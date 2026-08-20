#pragma once

// Typed decode accessors (2b-3 typed-storage migration).
//
// These are the replacement for the former generic `Operand` vectors: every
// mirrored symbol reads an operand/modifier directly out of the generated
// typed `Decoded<Mnemonic><Ops>` derived storage through the per-variant
// ShapeManifest (slot -> position in the typed ops[] array).  There is no
// per-instruction vector scan and no `const Operand*`.
//
// op_lookup / op_value / op_kind / op_flag resolve an operand ROLE by its
// FORMAT slot name.  slot_value resolves any FORMAT slot (operands AND
// modifiers) through the generated per-variant reader, returning the decoded
// value as a uint64.  Keep the 16-bit immediate sign/zero-extension rule
// (operand_set_value / operand_value_as_i64) intact: 16-bit sleeps/offsets
// are widened to 32 bits exactly as the typed fill did.

#include <cstdint>
#include <cstring>
#include <optional>

#include <semu/decoded_base.hpp>
#include <isa_shapes.hpp>
#include <isa_shapes_fill.hpp>

namespace semu::shape {

// Pointer to the typed operand slot's OperandValue in the derived ops[]
// array, or nullptr when the slot is not an operand of this variant.
inline const OperandValue* op_lookup(const DecodedInstruction& inst,
                                     const char* slot) {
    if (inst.shape_variant >= isa::kNumVariants) return nullptr;
    const auto& mf = kShapeManifests[inst.shape_variant];
    const OperandValue* ops =
        operand_values_by_variant(inst.shape_variant, &inst);
    if (!ops) return nullptr;
    for (std::uint16_t p = 0; p < mf.n_ops; ++p) {
        if (std::strcmp(mf.ops[p].slot, slot) == 0) return &ops[p];
    }
    return nullptr;
}

// Value of an operand role (kind-widened i64; nullopt when absent).
inline std::optional<std::int64_t> op_value(const DecodedInstruction& inst,
                                            const char* slot) {
    if (const OperandValue* o = op_lookup(inst, slot)) {
        return operand_value_as_i64(*o);
    }
    return std::nullopt;
}

// Operand kind of a role, or kRegister (cannot-be) sentinel semantics via an
// out-param bool.  Returns false when the slot is not an operand role.
inline bool op_kind(const DecodedInstruction& inst, const char* slot,
                    OperandKind* out) {
    if (const OperandValue* o = op_lookup(inst, slot)) {
        if (out) *out = static_cast<OperandKind>(o->kind);
        return true;
    }
    return false;
}

// Operand flag: 0 = negate, 1 = absolute, 2 = pred_not.  Returns false when
// the slot is absent or the flag not set.
inline bool op_flag(const DecodedInstruction& inst, const char* slot,
                    unsigned flag) {
    if (const OperandValue* o = op_lookup(inst, slot)) {
        return (o->flags & (1u << flag)) != 0;
    }
    return false;
}

// Any FORMAT slot value (operands and modifiers) as a uint64.  Resolves
// through the generated per-variant reader rather than the typed ops[] array
// so modifier member names (which differ per variant) are covered too.
inline std::optional<std::uint64_t> slot_value(
    const DecodedInstruction& inst, const char* name) {
    if (inst.shape_variant >= isa::kNumVariants) return std::nullopt;
    return slot_value_by_variant(inst.shape_variant, &inst, name);
}

}  // namespace semu::shape
