#pragma once

#include <cstdint>
#include <memory>

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
    // Operand role count (named operand fields), set at fill time.  The
    // interpreter uses this instead of the decode-side ShapeManifest.
    std::uint8_t n_ops = 0;
    int guard_pred = 7;
    bool guard_not = false;

    // 2b-3: the generic operands/modifiers/slot_values/raw_fields vectors and
    // the bounded Operand cache were removed with the typed migration; the
    // derived Decoded<Mnemonic><Ops> object is the only operand/modifier
    // storage (S2R imm8 / BAR barname are surfaced as typed `SRa`/`barname`
    // members).
    ScheduleWord schedule;

    virtual ~DecodedInstruction() = default;
    virtual std::unique_ptr<DecodedInstruction> clone() const {
        return std::make_unique<DecodedInstruction>(*this);
    }
};

}  // namespace semu
