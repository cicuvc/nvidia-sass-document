#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include <semu/decoder.hpp>
#include <semu/status.hpp>

// FROZEN (SIM_PLAN Phase 10): this header is part of the decoded-IR contract —
// Kernel / PredecodedWord / KernelMetadata / KernelSectionRef, and the Module
// loader that produces them.  A future JIT backend consumes exactly this IR
// (kDecodedIrVersion in api.hpp).  No breaking change may be made without
// bumping that version and re-freezing.

// Public cubin loader API (SIM_PLAN Phase 2).
//
// The loader parses a raw ELF64 cubin (sm120 only) into a Module: section /
// symbol tables, per-kernel metadata (.nv.info EIATTR records), per-kernel
// section associations (text / constant0 / shared / local) and pre-decoded
// kernel text with a stable IR entry per 16-byte word.  It is a pure parser
// — no CUDA driver linkage.  Decoding is done through the Phase 1 Decoder.
//
// Verification contract (SIM_PLAN Phase 2):
//   - ELF64 little-endian sm120 cubin only (e_flags / OSABI / ABI version
//     checked against an allowlist).
//   - Section/string/symbol tables resolve strictly through ELF sh_link
//     relationships (never by guessing names); all range checks are
//     overflow-safe.
//   - KPARAM ordinal/offset/size, regcount, static shared, barrier, exit
//     offset, cluster and frame/local/stack metadata -> KernelMetadata.
//   - Module load pre-decodes every 16-byte word of every kernel; each word
//     gets a stable IR entry (unique / illegal / ambiguous) so PC indexing
//     never drifts.
//   - Relocations are validated per linked symbol table and applied to
//     executable/data sections with an explicit allowlist; unknown
//     execution-affecting relocations fail.

namespace semu {

// Per-kernel EIATTR_KPARAM_INFO entry: parameter ordinal, byte offset within
// the parameter constant bank, and byte size (recovered from the size code).
struct KernelParam {
    std::uint32_t ordinal = 0;
    std::uint32_t offset = 0;
    std::uint32_t size = 0;
};

// One kernel's resource/launch metadata, aggregated from the device-wide
// .nv.info section and the per-kernel .nv.info.<name> section.  `params` is
// sorted by `ordinal` ascending (see Module load contract); use
// `param_by_ordinal` instead of vector-indexing for ABI-hole safety.
struct KernelMetadata {
    // Raw register count (EIATTR_REGCOUNT), 0 when absent.
    std::uint32_t regcount = 0;
    // Static shared memory bytes (from the .nv.shared.<name> NOBITS section
    // size, minus the driver's 0x400 CTA shared base window).
    std::uint32_t static_shared = 0;
    // Named barrier count (EIATTR_NUM_BARRIERS).
    std::uint32_t num_barriers = 0;
    // mbarrier count (EIATTR_NUM_MBARRIERS).
    std::uint32_t num_mbarriers = 0;
    // Max register count the kernel may use (EIATTR_MAXREG_COUNT).
    std::uint32_t maxreg = 0;
    // Byte size of the parameter constant bank (EIATTR_CBANK_PARAM_SIZE).
    std::uint32_t cbank_param_size = 0;
    // Parameters, sorted by ordinal ascending (EIATTR_KPARAM_INFO records).
    std::vector<KernelParam> params;
    // Exit instruction byte offsets within the kernel text
    // (EIATTR_EXIT_INSTR_OFFSETS).
    std::vector<std::uint32_t> exit_offsets;
    // mbarrier instruction byte offsets (EIATTR_MBARRIER_INSTR_OFFSETS,
    // 16-byte records; only the first u32 offset is kept).
    std::vector<std::uint32_t> mbarrier_offsets;
    // Cluster dims (EIATTR_CTA_PER_CLUSTER), when present.
    std::optional<std::array<std::uint32_t, 3>> cluster_dims;
    // EIATTR_EXPLICIT_CLUSTER marker.
    bool explicit_cluster = false;
    // CUDA API version (EIATTR_CUDA_API_VERSION), e.g. 0x80 = CUDA 12.8.
    std::uint32_t cuda_api_version = 0;
    // Frame / local stack metadata (EIATTR_FRAME_SIZE / MIN_STACK_SIZE /
    // MAX_STACK_SIZE).  `frame_size` != 0 means the kernel uses local
    // memory; the loader exposes it rather than guessing a local section.
    std::uint32_t frame_size = 0;
    std::uint32_t min_stack_size = 0;
    std::uint32_t max_stack_size = 0;
    // Set when any frame/stack EIATTR was present.
    bool has_stack_metadata = false;

    // Parameter by ordinal; nullptr when the ordinal is absent (ABI holes
    // are allowed; do not assume params[ordinal]).
    const KernelParam* param_by_ordinal(std::uint32_t ordinal) const;
};

// A stable per-word IR entry from kernel text pre-decoding.  Every 16-byte
// word of the text section maps to exactly one entry, in order, so entry
// index == kernel-relative PC / 16 always holds — illegal/ambiguous words
// are kept, never dropped.
struct PredecodedWord {
    std::uint64_t pc = 0;        // kernel-relative byte offset (index * 16)
    std::uint64_t file_offset = 0;  // absolute offset within the cubin image
    std::uint64_t lo = 0;        // raw word
    std::uint64_t hi = 0;
    bool unique = false;         // decoded uniquely (inst is valid)
    // Only meaningful when unique; heap-allocated (polymorphic, so it can
    // later be a derived typed-shape instance).  inst->pc is the
    // kernel-relative PC (matching PredecodedWord::pc), never a file offset.
    std::unique_ptr<DecodedInstruction> inst;
    // Human-readable diagnosis for non-unique words.
    std::string reason;

    // Deep-copying (the unique_ptr is copied as a fresh heap object); movable.
    PredecodedWord() = default;
    PredecodedWord(const PredecodedWord& o)
        : pc(o.pc), file_offset(o.file_offset), lo(o.lo), hi(o.hi),
          unique(o.unique),
          inst(o.inst ? o.inst->clone() : nullptr),
          reason(o.reason) {}
    PredecodedWord& operator=(const PredecodedWord& o) {
        if (this == &o) return *this;
        pc = o.pc; file_offset = o.file_offset; lo = o.lo; hi = o.hi;
        unique = o.unique;
        inst = o.inst ? o.inst->clone() : nullptr;
        reason = o.reason;
        return *this;
    }
    PredecodedWord(PredecodedWord&&) noexcept = default;
    PredecodedWord& operator=(PredecodedWord&&) noexcept = default;
};

// Per-kernel section association (text / constant / shared / local).  A
// read-only, bounds-checked byte view of the section image lives in the
// Module (see Module::section_view); for NOBITS sections the logical size
// is reported but the view is empty.
struct KernelSectionRef {
    std::uint32_t section_index = 0;  // ELF section table index
    std::uint64_t size = 0;           // logical size (NOBITS included)
    std::uint64_t align = 0;
    bool nobits = false;
};

// A loaded kernel: association of the function symbol, its text section,
// per-kernel constant/shared/local sections, metadata and the pre-decoded
// instruction stream.
struct Kernel {
    std::string symbol_name;        // mangled, e.g. "_Z5k_addPKfS0_Pfi"
    std::uint32_t text_section = 0; // section table index of .text.<name>
    std::uint64_t text_offset = 0;  // file offset of the text bytes
    std::uint64_t text_size = 0;    // bytes (section sh_size)
    std::vector<PredecodedWord> predecoded;  // one per 16-byte word
    KernelMetadata meta;

    // Per-kernel section associations (from ELF sh_info / symbol shndx
    // links, never name-guessed across kernels).
    std::optional<KernelSectionRef> constant0;   // .nv.constant0.<name>
    std::optional<KernelSectionRef> shared;      // .nv.shared.<name>
    std::optional<KernelSectionRef> local;       // .nv.local.<name>, if any
};

// Raw section table entry (subset of fields the loader consumes).
struct SectionInfo {
    std::string name;
    std::uint32_t type = 0;
    std::uint64_t flags = 0;
    std::uint64_t offset = 0;
    std::uint64_t size = 0;
    std::uint32_t link = 0;  // e.g. linked .symtab for .nv.info
    std::uint32_t info = 0;  // e.g. .text section index for .nv.info.<name>
    std::uint64_t align = 0;
    std::uint64_t entsize = 0;
    bool nobits = false;
};

// Raw symbol table entry.
struct SymbolInfo {
    std::string name;
    std::uint8_t bind = 0;
    std::uint8_t type = 0;
    std::uint8_t other = 0;  // st_other (bit 4 = STO_ENTRY for kernels)
    std::uint16_t shndx = 0;
    std::uint64_t value = 0;
    std::uint64_t size = 0;
};

// A warning raised during a load that is not fatal (e.g. unknown but
// explicitly allow-listed skippable metadata).
struct LoadWarning {
    std::string message;
};

// Loaded ELF64 cubin.  Immutable after construction.
//
// Loading policy (P2-GAP-08): `load` is the *executable* entry point —
// unknown EIATTR ids and unknown execution-affecting relocations are hard
// errors (kUnsupportedMetadata).  `load_for_inspection` is the permissive
// inspection mode: unknown-but-skippable metadata and non-unique words are
// tolerated with warnings, and the resulting module must not be executed.
class Module {
public:
    // Strict (executable) load.  kBadCubin for malformed ELF / wrong arch /
    // inconsistent tables; kUnsupportedMetadata for unknown metadata that
    // could affect execution.
    static StatusOr<Module> load(std::vector<std::uint8_t> data);

    // Permissive inspection-only load (P2-GAP-03/P2-GAP-08): unknown
    // EIATTR ids warn instead of failing, non-unique words get placeholder
    // entries, and relocations on non-executable sections warn instead of
    // failing.  The module is not executable.
    static StatusOr<Module> load_for_inspection(
        std::vector<std::uint8_t> data);

    // ELF header facts (for `inspect` and arch validation).
    std::uint32_t e_flags() const { return e_flags_; }
    std::uint8_t osabi() const { return osabi_; }
    std::uint8_t abi_version() const { return abi_version_; }

    // Execution eligibility.  Strict `load` returns true; inspection-only
    // loads return false and their kernels must never be executed (the
    // interpreter/backend checks this before running).
    bool executable() const { return executable_; }

    const std::vector<SectionInfo>& sections() const { return sections_; }
    const std::vector<SymbolInfo>& symbols() const { return symbols_; }
    const std::vector<Kernel>& kernels() const { return kernels_; }
    const std::vector<LoadWarning>& warnings() const { return warnings_; }

    // Kernel by mangled symbol name; nullptr when absent.
    const Kernel* find_kernel(const std::string& symbol_name) const;

    // Read-only byte view of a section's file image (empty for NOBITS
    // sections).  Bounds-checked.
    std::span<const std::uint8_t> section_view(
        std::uint32_t section_index) const;

    // Pre-decoded IR entry at a kernel-relative PC (byte offset within the
    // kernel's text).  nullptr when out of range.  `pc` is the kernel PC,
    // never a file offset (P2-GAP-03).
    const PredecodedWord* word_at(const Kernel& kernel,
                                  std::uint64_t kernel_pc) const;

    // The raw ELF image (for callers that need the bytes, e.g. debuggers).
    const std::vector<std::uint8_t>& raw() const { return data_; }

private:
    Module() = default;

    // Shared implementation: strict executable mode (inspect_mode=false) or
    // permissive inspection-only mode (inspect_mode=true).
    static StatusOr<Module> load_impl(std::vector<std::uint8_t> data,
                                      bool inspect_mode);

    std::vector<std::uint8_t> data_;
    std::uint32_t e_flags_ = 0;
    std::uint8_t osabi_ = 0;
    std::uint8_t abi_version_ = 0;
    bool executable_ = false;
    std::vector<SectionInfo> sections_;
    std::vector<SymbolInfo> symbols_;
    std::vector<Kernel> kernels_;
    std::vector<LoadWarning> warnings_;
};

}  // namespace semu
