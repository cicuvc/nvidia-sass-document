// Generated file -- do not edit.  Regenerate with:
//   python3 semu/tools/gen_capability.py
#pragma once
#include <semu/core/capability.hpp>

namespace semu::generated {
struct CapabilityRow {
    const char* mnemonic;
    const char* variant_class;
    std::uint16_t opcode;
    const char* pipe;
    semu::CapabilityState state;
    const char* note;
};

struct CapabilityManifestData {
    int manifest_version;
    const char* generator;
    const char* generated_from;
    const char* arch;
    int variants;
    int mnemonics;
    int enums;
    int tables;
    int funit_fields;
    int pipes;
    const char* reference_platform;
    const char* baseline_corpus;
    int num_rows;
    const CapabilityRow* rows;
};

extern const CapabilityManifestData kCapabilityManifest;
}  // namespace semu::generated
