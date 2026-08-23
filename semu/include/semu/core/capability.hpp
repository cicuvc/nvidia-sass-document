#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

// Capability manifest: per-encoding-variant implementation state for the
// target arch.  States are:
//
//   decode-only   — decoder unique + round-trip verified; semantics not
//                   implemented (touching this PC raises an
//                   UnsupportedInstruction fault).
//   functional    — semantics implemented and tested.
//   profiled      — functional and producing profiler memory/execution events.
//   unsupported   — not decodable/not handled at all.
//
// The manifest data is generated from sm120.json by semu/tools/gen_capability.py
// into semu/generated/capability_data.{hpp,cpp} and compiled into semu_core;
// regeneration is byte-identical (tested by tests/manifest_regen_test.py).

namespace semu {

enum class CapabilityState {
    kDecodeOnly = 0,
    kFunctional = 1,
    kProfiled = 2,
    kUnsupported = 3,
};

// Stable machine name.
const char* to_string(CapabilityState state);
// Parse the machine name back (returns nullopt for unknown strings).
std::optional<CapabilityState> parse_capability_state(std::string_view name);

struct CapabilityEntry {
    std::string mnemonic;       // e.g. "IMAD"
    std::string variant_class;  // e.g. "imad__RRR_RRR"
    std::uint16_t opcode;       // 13-bit {bit[91], bits[11:0]}
    std::string pipe;           // functional-unit pipe, e.g. "fmalighter_pipe"
    CapabilityState state;
    std::string note;           // reason/evidence for the state
};

struct CapabilityHeader {
    int manifest_version = 0;
    std::string generator;         // tool that produced the data
    std::string generated_from;    // source db
    std::string arch;              // "sm120"
    int variants = 0;              // total encoding variants
    int mnemonics = 0;
    int enums = 0;
    int tables = 0;
    int funit_fields = 0;
    int pipes = 0;
    std::string reference_platform;  // GPU/CUDA/driver used to verify
    std::string baseline_corpus;     // test list snapshot at baseline freeze
};

class CapabilityManifest {
public:
    // The compiled-in manifest for this build.
    static const CapabilityManifest& current();

    const CapabilityHeader& header() const { return header_; }
    const std::vector<CapabilityEntry>& entries() const { return entries_; }

    // Query helpers.
    std::vector<const CapabilityEntry*> by_mnemonic(
        std::string_view mnemonic) const;
    std::vector<const CapabilityEntry*> by_opcode(std::uint16_t opcode) const;
    std::size_t count(CapabilityState state) const;

    // Deterministic serializations (stable field order, stable row order).
    std::string to_text(bool full = false) const;  // summary unless `full`
    std::string to_json() const;
    // Parse a to_json() stream back; returns nullopt on any error.
    static std::optional<CapabilityManifest> from_json(std::string_view json);

private:
    CapabilityHeader header_;
    std::vector<CapabilityEntry> entries_;
};

}  // namespace semu
