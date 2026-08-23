#include <semu/core/fault.hpp>

#include <cstdio>

namespace semu {

const char* to_string(FaultKind kind) {
    switch (kind) {
        case FaultKind::kInvalidInstruction: return "InvalidInstruction";
        case FaultKind::kUnsupportedInstruction: return "UnsupportedInstruction";
        case FaultKind::kAmbiguousInstruction: return "AmbiguousInstruction";
        case FaultKind::kIllegalMemoryAccess: return "IllegalMemoryAccess";
        case FaultKind::kAlignmentFault: return "AlignmentFault";
        case FaultKind::kLifecycleFault: return "LifecycleFault";
        case FaultKind::kInstructionLimit: return "InstructionLimit";
        case FaultKind::kNoProgress: return "NoProgress";
        case FaultKind::kBarrierDeadlock: return "BarrierDeadlock";
        case FaultKind::kIllegalState: return "IllegalState";
        case FaultKind::kInternal: return "Internal";
    }
    return "Internal";
}

const char* describe(FaultKind kind) {
    switch (kind) {
        case FaultKind::kInvalidInstruction: return "illegal instruction encoding";
        case FaultKind::kUnsupportedInstruction:
            return "instruction is decode-only (not yet implemented)";
        case FaultKind::kAmbiguousInstruction:
            return "instruction encoding is not uniquely decodable";
        case FaultKind::kIllegalMemoryAccess: return "illegal memory access";
        case FaultKind::kAlignmentFault: return "misaligned memory access";
        case FaultKind::kLifecycleFault: return "device allocation lifecycle fault";
        case FaultKind::kInstructionLimit: return "dynamic instruction limit reached";
        case FaultKind::kNoProgress: return "scheduler made no progress";
        case FaultKind::kBarrierDeadlock: return "barrier deadlock";
        case FaultKind::kIllegalState: return "illegal simulator state";
        case FaultKind::kInternal: return "internal simulator fault";
    }
    return "internal simulator fault";
}

Fault::Fault(FaultKind kind, std::string message)
    : Error(ErrorCode::kFault, std::move(message)), kind_(kind) {}

Fault::Fault(FaultKind kind, std::string message, Error cause)
    : Error(ErrorCode::kFault, std::move(message), std::move(cause)),
      kind_(kind) {}

Fault& Fault::set_kernel(std::string name) {
    kernel_ = std::move(name);
    return *this;
}
Fault& Fault::set_pc(std::uint64_t pc) {
    pc_ = pc;
    return *this;
}
Fault& Fault::set_cta(std::uint32_t cta) {
    cta_ = cta;
    return *this;
}
Fault& Fault::set_warp(std::uint32_t warp) {
    warp_ = warp;
    return *this;
}
Fault& Fault::set_active_mask(std::uint32_t mask) {
    active_mask_ = mask;
    return *this;
}
Fault& Fault::set_instruction(Word128 word) {
    instr_ = word;
    return *this;
}
Fault& Fault::set_mnemonic(std::string mnemonic) {
    mnemonic_ = std::move(mnemonic);
    return *this;
}
Fault& Fault::set_variant(std::string variant_class) {
    variant_ = std::move(variant_class);
    return *this;
}

std::string Fault::to_report() const {
    std::string out;
    out.reserve(256);
    out += "Fault ";
    out += semu::to_string(kind_);
    out += ": ";
    out += semu::describe(kind_);
    out += " -- ";
    out += message();
    if (kernel_) {
        out += "\n  kernel: ";
        out += *kernel_;
    }
    if (pc_) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "\n  pc: 0x%016llX",
                      static_cast<unsigned long long>(*pc_));
        out += buf;
    }
    if (cta_) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "\n  cta: %u", *cta_);
        out += buf;
    }
    if (warp_) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "\n  warp: %u", *warp_);
        out += buf;
    }
    if (active_mask_) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "\n  active_mask: 0x%08X",
                      *active_mask_);
        out += buf;
    }
    if (instr_) {
        char buf[64];
        std::snprintf(buf, sizeof(buf), "\n  instruction: 0x%016llX_%016llX",
                      static_cast<unsigned long long>(instr_->hi),
                      static_cast<unsigned long long>(instr_->lo));
        out += buf;
    }
    if (mnemonic_) {
        out += "\n  mnemonic: ";
        out += *mnemonic_;
    }
    if (variant_) {
        out += "\n  variant: ";
        out += *variant_;
    }
    const auto chain = cause_chain();
    if (chain.size() > 1) {
        out += "\n  caused by: ";
        for (std::size_t i = 1; i < chain.size(); ++i) {
            if (i > 1) out += " -> ";
            out += chain[i]->message();
        }
    }
    return out;
}

}  // namespace semu
