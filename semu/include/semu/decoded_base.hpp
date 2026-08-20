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

    // 2b-3: the generic operands/modifiers/slot_values vectors and the
    // bounded Operand cache were removed with the typed migration; only the
    // schedule word and the raw encoded fields remain on the base.  raw_fields
    // is still consumed by field_value for a few genuinely unsurfaced raw
    // fields (S2R imm8 / BAR barname) — see HANDOFF_v2.md §7 before deleting.
    ScheduleWord schedule;
    std::vector<std::pair<std::string, std::uint64_t>> raw_fields;

    virtual ~DecodedInstruction() = default;
    virtual std::unique_ptr<DecodedInstruction> clone() const {
        return std::make_unique<DecodedInstruction>(*this);
    }
};

}  // namespace semu
