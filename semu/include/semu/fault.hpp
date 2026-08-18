#pragma once

#include <cstdint>
#include <optional>
#include <string>

#include <semu/status.hpp>
#include <semu/word.hpp>

// FROZEN (SIM_PLAN Phase 10): the fault ABI — Fault / FaultKind / to_string /
// describe — locked by kFaultAbiVersion (api.hpp).  SIM_PLAN Phase 0 promised
// later phases only ENRICH the context fields (set_kernel/set_pc/set_cta/...);
// they never change the surface.  The mock backend reports decode-only
// instructions through exactly this ABI.

// Runtime simulator fault.  A Fault is an Error enriched with the execution
// context needed to localize a failure to a dynamic warp instruction:
//
//   kernel name, byte PC, CTA id, warp id, 32-bit active (lane) mask, the raw
//   128-bit instruction word, the decoded mnemonic/variant, and a cause chain.
//
// SIM_PLAN Phase 0 contract: every functional/memory/decode failure is
// reported through Fault, and later phases must not need to extend the error
// model (they may only enrich the context fields).

namespace semu {

enum class FaultKind {
    kInvalidInstruction,      // reserved/discriminator bits violate the ISA
    kUnsupportedInstruction,  // decode-only: instruction not yet implemented
    kAmbiguousInstruction,    // encoding is not uniquely decodable
    kIllegalMemoryAccess,     // address-space violation / OOB
    kAlignmentFault,          // misaligned access rejected by the model
    kLifecycleFault,          // use-after-free / double-free / leak
    kInstructionLimit,        // dynamic instruction cap reached
    kNoProgress,              // scheduler detected a non-advancing warp
    kBarrierDeadlock,         // barrier/wait participants can never complete
    kIllegalState,
    kInternal,
};

// Stable machine name for a fault kind.
const char* to_string(FaultKind kind);

// Short human description.
const char* describe(FaultKind kind);

class Fault : public Error {
public:
    Fault() = default;
    Fault(FaultKind kind, std::string message);
    Fault(FaultKind kind, std::string message, Error cause);

    FaultKind kind() const { return kind_; }

    // Fluent setters (faults are usually built at the fault site).
    Fault& set_kernel(std::string name);
    Fault& set_pc(std::uint64_t pc);
    Fault& set_cta(std::uint32_t cta);
    Fault& set_warp(std::uint32_t warp);
    Fault& set_active_mask(std::uint32_t mask);
    Fault& set_instruction(Word128 word);
    Fault& set_mnemonic(std::string mnemonic);
    Fault& set_variant(std::string variant_class);

    const std::optional<std::string>& kernel() const { return kernel_; }
    const std::optional<std::uint64_t>& pc() const { return pc_; }
    const std::optional<std::uint32_t>& cta() const { return cta_; }
    const std::optional<std::uint32_t>& warp() const { return warp_; }
    const std::optional<std::uint32_t>& active_mask() const {
        return active_mask_;
    }
    const std::optional<Word128>& instruction() const { return instr_; }
    const std::optional<std::string>& mnemonic() const { return mnemonic_; }
    const std::optional<std::string>& variant() const { return variant_; }

    // Multi-line report including all populated context + cause chain.
    std::string to_report() const;

private:
    FaultKind kind_ = FaultKind::kInternal;
    std::optional<std::string> kernel_;
    std::optional<std::uint64_t> pc_;
    std::optional<std::uint32_t> cta_;
    std::optional<std::uint32_t> warp_;
    std::optional<std::uint32_t> active_mask_;
    std::optional<Word128> instr_;
    std::optional<std::string> mnemonic_;
    std::optional<std::string> variant_;
};

}  // namespace semu
