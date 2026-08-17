// Generated file -- do not edit.  Regenerate with:
//   python3 semu/tools/gen_isa.py
#pragma once

#include <cstdint>

namespace semu::isa {

// Modifier/operand enums.
struct EnumEntry {
    const char* name;
    std::int32_t value;   // -1 = valueless (presence means print)
};
struct EnumDef {
    const char* name;
    std::uint32_t n;
    const EnumEntry* entries;
};

// Decode tables (rows' `in` args comma-joined; `out` raw string).
struct TableDef {
    const char* name;
    std::uint32_t n;
    const char* const* in;
    const char* const* out;
    bool illegal;          // *_illegal_encodings rejection table
};

// Encoding field: one or more disjoint bit ranges (MSB-first).
struct Field {
    const char* name;
    std::uint8_t width;
    std::uint8_t nranges;
    const std::uint8_t* ranges;   // flattened [hi,lo] pairs
    const char* rhs;
    std::uint8_t rhs_kind;        // 0 slot,1 slot_attr,2 opcode,
                                 // 3 num,4 star_num,5 star_slot,
                                 // 6 table_fn,7 other_fn
    std::uint8_t scale;           // decode scale (logical = field*scale)
};
// Format slot.
struct Slot {
    const char* name;
    const char* type;
    const char* dflt;             // raw default string, may be null
    bool modifier;
};
// Legality condition.
struct Cond {
    const char* error;
    const char* predicate;
    const char* message;
};
// Size/pipe predicate (IDEST_SIZE, ISRC_*_SIZE, VIRTUAL_QUEUE, ...).
struct Pred {
    const char* key;
    const char* value;
};

struct Variant {
    const char* mnemonic;
    const char* variant_class;
    std::uint16_t opcode;
    std::uint16_t pipe;
    std::uint16_t nslots;   const Slot* slots;
    std::uint16_t nfields;  const Field* fields;
    std::uint16_t nconds;   const Cond* conds;
    std::uint16_t npreds;   const Pred* preds;
    bool alternate;         // ALTERNATE CLASS (not a decode candidate)
};

// Flat storage (all rows in one array for locality).
extern const EnumDef kEnums[];       extern const std::uint32_t kNumEnums;
extern const TableDef kTables[];      extern const std::uint32_t kNumTables;
extern const Variant kVariants[];     extern const std::uint32_t kNumVariants;
// Opcode candidate index: for each of the 8192 13-bit opcodes, the
// [kOpcodeStart[op], kOpcodeStart[op+1]) slice of kVariants.
extern const std::uint32_t kOpcodeStart[8193];
extern const char* const kPipes[];    extern const std::uint32_t kNumPipes;
extern const char* const kParameters[]; extern const std::int64_t kParameterVals[];
extern const std::uint32_t kNumParameters;
extern const char* const kConstants[]; extern const std::int64_t kConstantVals[];
extern const std::uint32_t kNumConstants;

}  // namespace semu::isa
