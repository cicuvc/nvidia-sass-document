#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <isa_data.hpp>
#include <semu/word.hpp>

namespace semu {

struct Operand {
    std::string slot;
    std::string kind;
    std::string text;
    std::int64_t value = 0;
    bool negated = false;
    bool absolute = false;
    bool pred_not = false;
};

struct ScheduleWord {
    int dst_wr_sb = 7;
    int src_rel_sb = 7;
    int req_bit_set = 0;
    int opex = 0;
    int usched = 0;
    int stall = 0;
    int yield_off = 0;
    int batch_t = 0;
};

class DecodedInstruction {
public:
    Word128 word{};
    std::uint64_t pc = 0;
    isa::Mnemonic mnemonic = isa::Mnemonic::kUnknown;
    isa::VariantClass variant_class = isa::VariantClass::kUnknown;
    isa::Pipe pipe = isa::Pipe::kUnknown;
    std::uint32_t shape_variant = 0xFFFFFFFFu;
    int guard_pred = 7;
    bool guard_not = false;

    // Temporary 2b bridge. The typed derived object is already the main
    // storage; the interpreter still consumes these until the next slice.
    std::vector<Operand> operands;
    std::vector<std::string> modifiers;
    ScheduleWord schedule;
    std::vector<std::pair<std::string, std::uint64_t>> raw_fields;
    std::vector<std::pair<std::string, std::uint64_t>> slot_values;
    mutable std::array<Operand, 9> operand_cache{};

    virtual ~DecodedInstruction() = default;
    virtual std::unique_ptr<DecodedInstruction> clone() const {
        return std::make_unique<DecodedInstruction>(*this);
    }
};

}  // namespace semu
