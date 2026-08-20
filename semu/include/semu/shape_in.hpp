#pragma once

// Hand-written glue for the typed decoded-IR schema (isa_shapes.hpp +
// generated isa_shapes_fill.hpp).  Hide: an opaque decoded-slot source (FillIn)
// and a kind->union-member setter used by the generated per-variant fill.

#include <cstdint>
#include <cstring>
#include <optional>

#include <isa_shapes.hpp>

namespace semu::shape {

// Provides decoded slot values + operand flags (bit0 negate, bit1 absolute,
// bit2 pred_not) by slot name, so the generated fill can populate a typed
// Decoded<Mnemonic><Ops> without depending on the decoder's storage.
struct FillIn {
    virtual ~FillIn() = default;
    virtual std::int64_t value(const char* slot) const = 0;
    virtual std::uint8_t flags(const char* slot) const = 0;
};

// Set an OperandValue union member from its kind (16-bit immediates are
// sign/zero extended into the 32/64-bit member; the caller supplies raw).
inline void operand_set_value(OperandValue& ov, OperandKind k, std::int64_t v) {
    switch (k) {
        case OperandKind::kRegister:
            ov.v.reg_idx = static_cast<std::int32_t>(v);        break;
        case OperandKind::kUniformRegister:
            ov.v.ureg_idx = static_cast<std::int32_t>(v);       break;
        case OperandKind::kPredicate:
        case OperandKind::kUniformPredicate:
            ov.v.pred_idx = static_cast<std::uint8_t>(v);       break;
        case OperandKind::kSImm:
            ov.v.simm64 = static_cast<std::int64_t>(v);         break;
        case OperandKind::kUImm:
            ov.v.uimm64 = static_cast<std::uint64_t>(v);        break;
        case OperandKind::kFImm16:
            ov.v.uimm16 = static_cast<std::uint16_t>(v);        break;
        case OperandKind::kFImm32:
            ov.v.fimm32 = *reinterpret_cast<const float*>(&v);  break;
        case OperandKind::kFImm64:
            ov.v.dimm64 = *reinterpret_cast<const double*>(&v); break;
        case OperandKind::kDesc:
            ov.v.desc = static_cast<std::uint64_t>(v);          break;
        default:
            ov.v.uimm64 = static_cast<std::uint64_t>(v);        break;
    }
}

inline std::int64_t operand_value_as_i64(const OperandValue& ov) {
    switch (static_cast<OperandKind>(ov.kind)) {
        case OperandKind::kRegister: return ov.v.reg_idx;
        case OperandKind::kUniformRegister: return ov.v.ureg_idx;
        case OperandKind::kPredicate:
        case OperandKind::kUniformPredicate: return ov.v.pred_idx;
        case OperandKind::kSImm: return ov.v.simm64;
        case OperandKind::kUImm: return static_cast<std::int64_t>(ov.v.uimm64);
        case OperandKind::kFImm16: return ov.v.uimm16;
        case OperandKind::kFImm32: {
            std::uint32_t bits = 0;
            std::memcpy(&bits, &ov.v.fimm32, sizeof(bits));
            return bits;
        }
        case OperandKind::kFImm64: {
            std::uint64_t bits = 0;
            std::memcpy(&bits, &ov.v.dimm64, sizeof(bits));
            return static_cast<std::int64_t>(bits);
        }
        case OperandKind::kDesc:
        case OperandKind::kSpecial: return static_cast<std::int64_t>(ov.v.uimm64);
    }
    return 0;
}

}  // namespace semu::shape
