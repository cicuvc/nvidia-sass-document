// ELF64 cubin loader for sm120 (SIM_PLAN Phase 2).
//
// Parses a raw cubin byte image into sections, symbols, per-kernel metadata
// and pre-decoded kernel text:
//
//   - ELF64 little-endian validation (magic, class, data, machine EM_CUDA,
//     sm120 e_flags / OSABI / ABI version allowlist).
//   - Section header table + string tables, resolved strictly through ELF
//     sh_link relationships; every range check is overflow-safe
//     (offset <= size && size <= size - offset form).
//   - Symbol tables: each symtab resolves names through its own sh_link
//     string table; kernel entry detection via STB_GLOBAL | STT_FUNC |
//     STO_ENTRY.
//   - .nv.info (device-wide) + .nv.info.<mangled> (per-kernel) EIATTR
//     records -> KernelMetadata.  Unknown EIATTR ids are hard errors in
//     executable mode (kUnsupportedMetadata); a reviewed skippable
//     allowlist warns instead.
//   - Per-kernel section associations: .nv.constant0.<name> /
//     .nv.shared.<name> / .nv.local.<name> via ELF sh_info links, exposed
//     as KernelSectionRef + byte views.
//   - .text.<mangled> pre-decoding through the Phase 1 Decoder with a
//     stable IR entry per 16-byte word (unique / illegal / ambiguous kept).
//   - Relocations (.rela.*): validated against each section's own linked
//     symtab, applied by relocation width with an explicit allowlist on
//     executable/data targets; unknown execution-affecting types fail.

#include <semu/cubin.hpp>

#include <algorithm>
#include <cstring>
#include <limits>
#include <span>

#include <semu/decoder.hpp>

namespace semu {
namespace {

constexpr std::uint16_t kMachineCuda = 190;  // EM_CUDA
constexpr std::uint32_t kFlagsSm120 = 0x06007802;
// OSABI/ABI version allowlist for raw sm120 cubins (nvcc 12.8 emits
// 0x41/0x08).  Unknown values are rejected in executable mode.
constexpr std::uint8_t kOsabiCuda = 0x41;
constexpr std::uint8_t kAbiVersionSm120 = 0x08;

constexpr std::uint32_t kShTypeProgbits = 1;
constexpr std::uint32_t kShTypeSymtab = 2;
constexpr std::uint32_t kShTypeStrtab = 3;
constexpr std::uint32_t kShTypeRela = 4;
constexpr std::uint32_t kShTypeNobits = 8;
constexpr std::uint32_t kShTypeCudaInfo = 0x70000000;

constexpr std::uint64_t kShfAlloc = 0x2;
constexpr std::uint64_t kShfExec = 0x4;

constexpr std::uint8_t kStbGlobal = 1;
constexpr std::uint8_t kSttFunc = 2;
constexpr std::uint8_t kStoEntry = 0x10;

// Instruction word size for SASS (sm120: 128-bit).
constexpr std::uint64_t kInstrSize = 16;
constexpr std::uint64_t kTextAlign = 128;

// EIATTR ids consumed by the loader (verified against nvcc 12.8 + the repo
// assembler's eiattr_* builders).
enum EiaType : std::uint8_t {
    kEiaParamCbank = 0x0a,          // PARAM_CBANK: sym_idx + (base|size)
    kEiaFrameSize = 0x11,           // FRAME_SIZE: func_sym + u32
    kEiaMinStackSize = 0x12,        // MIN_STACK_SIZE
    kEiaKparamInfo = 0x17,          // KPARAM_INFO: ordinal/offset/size
    kEiaCbankParamSize = 0x19,      // CBANK_PARAM_SIZE: u16
    kEiaMaxregCount = 0x1b,         // MAXREG_COUNT: u16
    kEiaExitInstrOffsets = 0x1c,    // EXIT_INSTR_OFFSETS: u32[]
    kEiaMaxStackSize = 0x23,        // MAX_STACK_SIZE
    kEiaRegcount = 0x2f,            // REGCOUNT: func_sym + u32
    kEiaSwWar = 0x36,               // SW_WAR: u32
    kEiaCudaApiVersion = 0x37,      // CUDA_API_VERSION: u32
    kEiaNumMbarriers = 0x38,        // NUM_MBARRIERS: u16
    kEiaMbarrierOffsets = 0x39,     // MBARRIER_INSTR_OFFSETS: 16B records
    kEiaCtaPerCluster = 0x3d,       // CTA_PER_CLUSTER: 3 x u32
    kEiaExplicitCluster = 0x3e,     // EXPLICIT_CLUSTER: marker (fmt=1)
    kEiaShaderType = 0x49,          // SHADER_TYPE: func_sym + u32
    kEiaVrcCtaInit = 0x4a,          // VRC_CTA_INIT_COUNT: u8
    kEiaNumBarriers = 0x4c,         // NUM_BARRIERS: u8
    kEiaSparseMmaMask = 0x50,       // SPARSE_MMA_MASK: u16
};

// Reviewed EIATTR ids that are known *skippable* (informational; do not
// change execution semantics): warn instead of failing when encountered
// (P2-GAP-08).  Everything else unknown is a kUnsupportedMetadata error in
// executable mode.
bool is_skippable_eiattr(std::uint8_t etype) {
    switch (etype) {
        case 0x1e:   // seen in nvcc 12.8 per-kernel info; 4-byte zero value
            return true;
        default:
            return false;
    }
}

// Relocation types from the CUDA ELF ABI (R_CUDA_*).  The loader applies
// the absolute family and pointer/symbol-offset forms on executable/data
// sections; everything else fails as unsupported.
constexpr std::uint32_t kRcudaNone = 0;
constexpr std::uint32_t kRcudaPtr = 1;
constexpr std::uint32_t kRcudaSymoff = 2;
constexpr std::uint32_t kRcudaAbs64 = 0x1a;
constexpr std::uint32_t kRcudaAbs32 = 0x1b;
constexpr std::uint32_t kRcudaAbs16 = 0x1c;
constexpr std::uint32_t kRcudaAbs8 = 0x1d;

// Byte width written by a relocation type (0 = not applicable / none).
std::uint64_t relocation_width(std::uint32_t type) {
    switch (type) {
        case kRcudaAbs64:
        case kRcudaPtr:
        case kRcudaSymoff:
            return 8;
        case kRcudaAbs32:
            return 4;
        case kRcudaAbs16:
            return 2;
        case kRcudaAbs8:
            return 1;
        default:
            return 0;
    }
}

// Overflow-safe range check: [off, off+size) must fit within [0, file_size).
bool range_fits(std::uint64_t off, std::uint64_t size,
                std::uint64_t file_size) {
    return off <= file_size && size <= file_size - off;
}

std::uint16_t rd16(const std::vector<std::uint8_t>& d, std::uint64_t off,
                   Error* err) {
    if (!range_fits(off, 2, d.size())) {
        *err = Error::out_of_range(
            "ELF field read past end of file at offset " +
            std::to_string(off));
        return 0;
    }
    std::uint16_t v;
    std::memcpy(&v, d.data() + off, 2);
    return v;
}

std::uint32_t rd32(const std::vector<std::uint8_t>& d, std::uint64_t off,
                   Error* err) {
    if (!range_fits(off, 4, d.size())) {
        *err = Error::out_of_range(
            "ELF field read past end of file at offset " +
            std::to_string(off));
        return 0;
    }
    std::uint32_t v;
    std::memcpy(&v, d.data() + off, 4);
    return v;
}

std::uint64_t rd64(const std::vector<std::uint8_t>& d, std::uint64_t off,
                   Error* err) {
    if (!range_fits(off, 8, d.size())) {
        *err = Error::out_of_range(
            "ELF field read past end of file at offset " +
            std::to_string(off));
        return 0;
    }
    std::uint64_t v;
    std::memcpy(&v, d.data() + off, 8);
    return v;
}

Error bad_cubin(const std::string& msg, Error cause) {
    return Error(ErrorCode::kBadCubin, msg, std::move(cause));
}

// Read a NUL-terminated string from `data` starting at `off` within
// [str_off, str_off+str_size) (bounds checked; empty + *err on failure).
std::string read_cstr(const std::vector<std::uint8_t>& d, std::uint64_t str_off,
                      std::uint64_t str_size, std::uint64_t off, Error* err) {
    if (!range_fits(off, 1, str_size)) {
        *err = Error::out_of_range(
            "string offset 0x" + std::to_string(off) +
            " past end of string table");
        return {};
    }
    const std::uint8_t* base = d.data() + str_off;
    const std::size_t avail = static_cast<std::size_t>(str_size - off);
    const std::uint8_t* p =
        static_cast<const std::uint8_t*>(std::memchr(base + off, 0, avail));
    if (!p) {
        *err = Error::out_of_range("unterminated string at 0x" +
                                   std::to_string(off));
        return {};
    }
    return std::string(reinterpret_cast<const char*>(base + off),
                       static_cast<std::size_t>(p - (base + off)));
}

// ---------------------------------------------------------------------------
// EIATTR record iteration
// ---------------------------------------------------------------------------

struct EiaRecord {
    std::uint8_t fmt = 0;
    std::uint8_t etype = 0;
    std::uint64_t payload_off = 0;  // file offset of payload
    std::uint64_t payload_size = 0;
    std::uint64_t record_size = 0;  // whole record bytes
};

// Iterate the records of an EIATTR section; yields false + *err on malformed
// framing (an overrun is a kBadCubin, not a silent skip).  Trailing zero
// padding (alignment) ends the iteration silently.
bool eia_next(const std::vector<std::uint8_t>& d, std::uint64_t sec_off,
              std::uint64_t sec_size, std::uint64_t* cur, EiaRecord* rec,
              Error* err) {
    if (*cur >= sec_size) return false;
    // All-zero remainder = section alignment padding.
    bool all_zero = true;
    for (std::uint64_t i = *cur; i < sec_size; ++i) {
        if (d[sec_off + i] != 0) {
            all_zero = false;
            break;
        }
    }
    if (all_zero) return false;
    const std::uint64_t rec_off = sec_off + *cur;
    if (!range_fits(rec_off, 4, d.size())) {
        *err = bad_cubin("EIATTR record header past end of file",
                         Error::out_of_range("offset 0x" +
                                             std::to_string(rec_off)));
        return false;
    }
    rec->fmt = d[rec_off];
    rec->etype = d[rec_off + 1];
    std::uint64_t payload = 0;
    switch (rec->fmt) {
        case 1:  // marker: no payload
            payload = 0;
            break;
        case 2:  // bval: 1 byte value
            payload = 1;
            break;
        case 3:  // hval: 2 byte value
            payload = 2;
            break;
        case 4:  // sized payload
            payload = static_cast<std::uint64_t>(rd16(d, rec_off + 2, err));
            if (!err->ok()) return false;
            break;
        default:
            *err = bad_cubin("unknown EIATTR fmt=" + std::to_string(rec->fmt),
                             Error::invalid_argument("record at 0x" +
                                                     std::to_string(rec_off)));
            return false;
    }
    // fmt=1/2/3 records carry their value inline at rec_off+2 (marker /
    // bval / hval); fmt=4 carries a size field and its payload starts at
    // rec_off+4.
    rec->payload_off = (rec->fmt == 4) ? rec_off + 4 : rec_off + 2;
    rec->payload_size = payload;
    // fmt=1/2/3 records are fixed 4 bytes (fmt, etype, value/pad); only
    // fmt=4 carries a size field and a variable-length payload.
    rec->record_size = (rec->fmt == 4) ? 4 + payload : 4;
    if (rec->fmt == 4 &&
        !range_fits(rec->payload_off, payload, d.size())) {
        *err = bad_cubin("EIATTR payload past end of file",
                         Error::out_of_range("record at 0x" +
                                             std::to_string(rec_off)));
        return false;
    }
    if (!range_fits(*cur, rec->record_size, sec_size)) {
        *err = bad_cubin("EIATTR record overruns its section",
                         Error::out_of_range("record at 0x" +
                                             std::to_string(rec_off)));
        return false;
    }
    *cur += rec->record_size;
    return true;
}

// ---------------------------------------------------------------------------
// .nv.info parsing
// ---------------------------------------------------------------------------

struct NvInfoAttrs {
    std::uint32_t regcount = 0;
    bool has_regcount = false;
    std::uint32_t maxreg = 0;
    std::uint32_t num_barriers = 0;
    std::uint32_t num_mbarriers = 0;
    std::uint32_t cuda_api_version = 0;
    std::uint32_t cbank_param_size = 0;
    std::uint32_t cbank_base = 0;
    std::vector<KernelParam> kparams;
    std::vector<std::uint32_t> exit_offsets;
    std::vector<std::uint32_t> mbarrier_offsets;
    std::optional<std::array<std::uint32_t, 3>> cluster_dims;
    bool explicit_cluster = false;
    std::uint32_t frame_size = 0;
    std::uint32_t min_stack_size = 0;
    std::uint32_t max_stack_size = 0;
    bool has_stack_metadata = false;
    std::vector<LoadWarning> warnings;
};

// Parse one EIATTR record into NvInfoAttrs.  In inspection mode unknown
// (non-allowlisted) ids degrade to warnings instead of failing
// (P2-GAP-08 strict/permissive contract).
void parse_eia_record(const EiaRecord& rec, const std::vector<std::uint8_t>& d,
                      NvInfoAttrs* out, bool inspect_mode, Error* err) {
    const std::uint64_t po = rec.payload_off;
    switch (rec.etype) {
        case kEiaRegcount:
            if (rec.payload_size >= 8) {
                out->regcount = rd32(d, po + 4, err);
                out->has_regcount = err->ok();
            }
            break;
        case kEiaMaxregCount:
            if (rec.payload_size >= 2) out->maxreg = rd16(d, po, err);
            break;
        case kEiaCudaApiVersion:
            if (rec.payload_size >= 4) out->cuda_api_version = rd32(d, po, err);
            break;
        case kEiaCbankParamSize:
            if (rec.payload_size >= 2) out->cbank_param_size = rd16(d, po, err);
            break;
        case kEiaParamCbank: {
            // PARAM_CBANK: [sym_idx u32][(base<<16)|size u32]
            if (rec.payload_size >= 8) {
                const std::uint32_t packed = rd32(d, po + 4, err);
                if (err->ok()) {
                    out->cbank_base = packed & 0xFFFF;
                    out->cbank_param_size = packed >> 16;
                }
            }
            break;
        }
        case kEiaKparamInfo: {
            // KPARAM_INFO: [0 u32][(offset<<16)|ordinal u32][flags u32]
            // flags: size code in bits 16-31 = (size << 2) | 1; low 16 bits
            // 0xf000 fixed marker.
            if (rec.payload_size < 12) break;
            const std::uint32_t ord = rd32(d, po + 4, err);
            const std::uint32_t flags = rd32(d, po + 8, err);
            if (!err->ok()) break;
            KernelParam p;
            p.ordinal = ord & 0xFFFF;
            p.offset = ord >> 16;
            const std::uint32_t code = flags >> 16;
            if (code >= 5) {
                const std::uint32_t sz = (code - 1) >> 2;
                p.size = sz;
            }
            out->kparams.push_back(p);
            break;
        }
        case kEiaExitInstrOffsets:
            for (std::uint64_t o = 0; o + 4 <= rec.payload_size; o += 4)
                out->exit_offsets.push_back(rd32(d, po + o, err));
            break;
        case kEiaMbarrierOffsets:
            // 16-byte records: {u32 offset, u32 0xff, u32 0, u32 flags}.
            for (std::uint64_t o = 0; o + 16 <= rec.payload_size; o += 16)
                out->mbarrier_offsets.push_back(rd32(d, po + o, err));
            break;
        case kEiaCtaPerCluster:
            if (rec.payload_size >= 12) {
                out->cluster_dims = std::array<std::uint32_t, 3>{
                    rd32(d, po, err), rd32(d, po + 4, err),
                    rd32(d, po + 8, err)};
            }
            break;
        case kEiaExplicitCluster:
            out->explicit_cluster = true;
            break;
        case kEiaNumBarriers:
            if (rec.payload_size >= 1) out->num_barriers = d[po];
            break;
        case kEiaNumMbarriers:
            if (rec.payload_size >= 2) out->num_mbarriers = rd16(d, po, err);
            break;
        case kEiaFrameSize:
            if (rec.payload_size >= 8) {
                out->frame_size = rd32(d, po + 4, err);
                out->has_stack_metadata = err->ok();
            }
            break;
        case kEiaMinStackSize:
            if (rec.payload_size >= 8) {
                out->min_stack_size = rd32(d, po + 4, err);
                out->has_stack_metadata = err->ok();
            }
            break;
        case kEiaMaxStackSize:
            if (rec.payload_size >= 8) {
                out->max_stack_size = rd32(d, po + 4, err);
                out->has_stack_metadata = err->ok();
            }
            break;
        case kEiaShaderType:
            // Recognized; shader-kind tag is informational for the loader
            // (compute kernels default to CS).  Parsed but not exposed.
            break;
        case kEiaSwWar:
        case kEiaVrcCtaInit:
        case kEiaSparseMmaMask:
            // Known informational records; parsed structurally, not exposed.
            break;
        default: {
            // Reviewed skippable ids warn; anything else is unsupported in
            // strict (executable) mode and degrades to a warning in
            // inspection mode.
            char b[8];
            std::snprintf(b, sizeof(b), "%02x", rec.etype);
            if (is_skippable_eiattr(rec.etype) || inspect_mode) {
                out->warnings.push_back(LoadWarning{
                    "unknown EIATTR id 0x" + std::string(b) + " (fmt=" +
                    std::to_string(rec.fmt) + ")" +
                    (inspect_mode && !is_skippable_eiattr(rec.etype)
                         ? " (inspection mode) preserved as skippable "
                           "metadata"
                         : " preserved as skippable metadata")});
                break;
            }
            *err = Error(ErrorCode::kUnsupportedMetadata,
                         "unknown EIATTR id 0x" + std::string(b) +
                             " may affect execution and is not supported",
                         Error::invalid_argument("section record"));
            break;
        }
    }
}

// ---------------------------------------------------------------------------
// KPARAM validation (P2-GAP-02)
// ---------------------------------------------------------------------------

// Validate + normalize a raw KPARAM list: no duplicate ordinals, no zero
// sizes, no overlapping byte ranges, no range past the parameter cbank.
// On success `params` is sorted by ordinal ascending.  `cbank_size` is the
// kernel's declared cbank param size (0 = unknown/not validated).
Status normalize_kparams(std::vector<KernelParam> params,
                         std::uint32_t cbank_size,
                         std::vector<KernelParam>* out) {
    // Overlap detection must be independent of the ordinal<->offset
    // ordering: a legal ABI may place params at non-monotonic offsets.
    // Sort a copy by offset for range checking, then sort the canonical
    // result by ordinal.
    std::vector<KernelParam> by_offset = params;
    std::sort(by_offset.begin(), by_offset.end(),
              [](const KernelParam& a, const KernelParam& b) {
                  return a.offset < b.offset;
              });
    for (std::size_t i = 0; i < by_offset.size(); ++i) {
        const KernelParam& p = by_offset[i];
        if (p.size == 0) {
            return Status::failure(Error(
                ErrorCode::kBadCubin,
                "KPARAM ordinal " + std::to_string(p.ordinal) +
                    " has zero size",
                Error::invalid_argument("")));
        }
        if (p.offset > std::numeric_limits<std::uint32_t>::max() - p.size) {
            return Status::failure(Error(
                ErrorCode::kBadCubin,
                "KPARAM ordinal " + std::to_string(p.ordinal) +
                    " range overflows",
                Error::invalid_argument("")));
        }
        if (cbank_size != 0 && p.offset + p.size > cbank_size) {
            return Status::failure(Error(
                ErrorCode::kBadCubin,
                "KPARAM ordinal " + std::to_string(p.ordinal) +
                    " range @0x" + std::to_string(p.offset) + "+" +
                    std::to_string(p.size) + " exceeds cbank param size " +
                    std::to_string(cbank_size),
                Error::invalid_argument("")));
        }
        if (i > 0) {
            const KernelParam& prev = by_offset[i - 1];
            if (p.offset < prev.offset + prev.size) {
                return Status::failure(Error(
                    ErrorCode::kBadCubin,
                    "overlapping KPARAM ranges: ordinal " +
                        std::to_string(prev.ordinal) + " @0x" +
                        [&]() {
                            char b[16];
                            std::snprintf(b, sizeof(b), "%x", prev.offset);
                            return std::string(b);
                        }() +
                        " size " + std::to_string(prev.size) + " vs ordinal " +
                        std::to_string(p.ordinal) + " @0x" +
                        [&]() {
                            char b[16];
                            std::snprintf(b, sizeof(b), "%x", p.offset);
                            return std::string(b);
                        }(),
                    Error::invalid_argument("")));
            }
        }
    }
    // Duplicate-ordinal detection on the canonical (ordinal-sorted) order.
    std::sort(params.begin(), params.end(),
              [](const KernelParam& a, const KernelParam& b) {
                  return a.ordinal < b.ordinal;
              });
    for (std::size_t i = 1; i < params.size(); ++i) {
        if (params[i - 1].ordinal == params[i].ordinal) {
            return Status::failure(Error(
                ErrorCode::kBadCubin,
                "duplicate KPARAM ordinal " +
                    std::to_string(params[i].ordinal),
                Error::invalid_argument("")));
        }
    }
    *out = std::move(params);
    return Status::success();
}

}  // namespace

// ---------------------------------------------------------------------------
// Module
// ---------------------------------------------------------------------------

namespace {

struct RawSection {
    std::uint32_t name_off;
    std::uint32_t type;
    std::uint64_t flags;
    std::uint64_t offset;
    std::uint64_t size;
    std::uint32_t link;
    std::uint32_t info;
    std::uint64_t align;
    std::uint64_t entsize;
    std::string name;
    bool nobits = false;
};

struct RawSymbol {
    std::string name;
    std::uint8_t bind = 0;
    std::uint8_t type = 0;
    std::uint8_t other = 0;
    std::uint16_t shndx = 0;
    std::uint64_t value = 0;
    std::uint64_t size = 0;
};

// Per-symtab parsed table: entries + the symtab's own strtab offset/size.
struct ParsedSymtab {
    std::uint32_t section = 0;
    std::uint64_t strtab_off = 0;
    std::uint64_t strtab_size = 0;
    std::vector<RawSymbol> symbols;
};

struct LoadContext {
    bool inspect_mode = false;
    Error err;
    std::vector<LoadWarning> warnings;
};

// Parse one .rela section using the *linked* symtab (P2-GAP-05/P2-GAP-06).
// Returns an error Status when a relocation cannot be applied or is
// unsupported on an execution-relevant target.
Status apply_relocations(std::vector<std::uint8_t>& d,
                         const RawSection& rela,
                         const std::vector<ParsedSymtab>& symtabs,
                         const std::vector<RawSection>& sections,
                         const std::vector<std::string>& section_names,
                         LoadContext* ctx) {
    // Helper: safe name lookup for messages (rela.info may be garbage).
    auto sec_name = [&](std::uint32_t idx) -> std::string {
        if (idx < section_names.size()) return section_names[idx];
        return "<out-of-range " + std::to_string(idx) + ">";
    };
    // Target section is sh_info; linked symtab is sh_link.  Bounds check
    // MUST happen before any section_names/[...] access (the index is
    // attacker-controlled; the caller's name vector is not index-aligned).
    if (rela.info >= sections.size()) {
        return Status::failure(bad_cubin(
            "relocation section with sh_info=" + std::to_string(rela.info) +
                " targets out-of-range section",
            Error::out_of_range("")));
    }
    // The linked symtab is sh_link *as a section index*; find it among the
    // parsed symtabs (they are compact, not section-indexed).
    const ParsedSymtab* linked = nullptr;
    for (const auto& st : symtabs) {
        if (st.section == rela.link) {
            linked = &st;
            break;
        }
    }
    if (!linked) {
        return Status::failure(bad_cubin(
            "relocation section '" + sec_name(rela.info) +
                "' has invalid sh_link " + std::to_string(rela.link),
            Error::invalid_argument("")));
    }
    const ParsedSymtab& symtab = *linked;
    const RawSection& target = sections[rela.info];
    if (rela.entsize != 0 && rela.entsize < 24) {
        return Status::failure(bad_cubin(
            "relocation section '" + sec_name(rela.info) +
                "' has malformed entsize " + std::to_string(rela.entsize),
            Error::invalid_argument("")));
    }
    const std::uint64_t entsize = rela.entsize ? rela.entsize : 24;
    if (rela.size % entsize != 0) {
        return Status::failure(bad_cubin(
            "relocation section '" + sec_name(rela.info) +
                "' size not a multiple of its entry size",
            Error::invalid_argument("")));
    }
    if (!range_fits(rela.offset, rela.size, d.size())) {
        return Status::failure(bad_cubin(
            "relocation section '" + sec_name(rela.info) +
                "' data past end of file",
            Error::out_of_range("")));
    }
    const bool target_exec = (target.flags & kShfExec) != 0;
    const bool target_data = (target.type == kShTypeProgbits) &&
                             !target_exec && (target.flags & kShfAlloc);
    // Debug-only targets are an *exact name allowlist* (DWARF / debug
    // sections).  Everything else that is neither executable nor alloc
    // data (e.g. CUDA metadata sections) is NOT treated as skippable
    // "debug": unknown targets fail in strict mode, warn in inspection.
    const std::string& tname = sec_name(rela.info);
    const bool target_debug =
        !target_exec && !target_data && target.type != kShTypeNobits &&
        (tname.rfind(".debug_", 0) == 0 || tname.rfind(".zdebug_", 0) == 0 ||
         tname.rfind(".eh_frame", 0) == 0);
    // NOBITS targets have no file payload: a relocation would write into
    // whatever section happens to share the file offset.  Reject outright
    // (structured error), never write the raw image.
    if (target.type == kShTypeNobits) {
        return Status::failure(bad_cubin(
            "relocation section '" + sec_name(rela.info) +
                "' targets NOBITS section '" + sec_name(rela.info) +
                "' which has no file payload",
            Error::invalid_argument("")));
    }
    const std::uint64_t nrel = rela.size / entsize;
    for (std::uint64_t r = 0; r < nrel; ++r) {
        const std::uint64_t ro = rela.offset + r * entsize;
        Error err;
        const std::uint64_t r_off = rd64(d, ro, &err);
        const std::uint64_t r_info = rd64(d, ro + 8, &err);
        const std::int64_t r_addend =
            static_cast<std::int64_t>(rd64(d, ro + 16, &err));
        if (!err.ok()) {
            return Status::failure(Error(
                ErrorCode::kBadCubin,
                "relocation entry read failed in '" +
                    sec_name(rela.info) + "'",
                std::move(err)));
        }
        const std::uint64_t sym = r_info >> 32;
        const std::uint32_t type = r_info & 0xffffffff;
        if (sym >= symtab.symbols.size()) {
            return Status::failure(bad_cubin(
                "relocation in '" + sec_name(rela.info) +
                    "' references out-of-range symbol " +
                    std::to_string(sym) + " in linked symtab",
                Error::out_of_range("")));
        }
        const std::uint64_t width = relocation_width(type);
        if (type == kRcudaNone) continue;
        if (target_debug) {
            // Debug-only relocation (e.g. .rela.debug_frame): skip with a
            // warning; it never affects execution.
            ctx->warnings.push_back(LoadWarning{
                "relocation type " + std::to_string(type) + " in '" +
                sec_name(rela.info) +
                "' (debug-only target) skipped"});
            continue;
        }
        // Neither executable, nor alloc data, nor an allowlisted debug
        // target: an unknown CUDA/metadata section with a relocation is not
        // provably harmless.  Strict mode fails; inspection mode warns.
        if (!target_exec && !target_data) {
            if (!ctx->inspect_mode) {
                return Status::failure(Error(
                    ErrorCode::kUnsupportedMetadata,
                    "relocation type " + std::to_string(type) + " in '" +
                        sec_name(rela.info) + "' targets non-executable, "
                        "non-data section '" + tname +
                        "' which is not on the debug allowlist",
                    Error::invalid_argument("")));
            }
            ctx->warnings.push_back(LoadWarning{
                "relocation type " + std::to_string(type) + " in '" +
                sec_name(rela.info) + "' targeting section '" + tname +
                "' (inspection mode) skipped"});
            continue;
        }
        if (width == 0) {
            // Unknown type on an execution-relevant (exec or alloc data)
            // target: hard failure in executable mode; warning in
            // inspection mode.
            if (!ctx->inspect_mode) {
                return Status::failure(Error(
                    ErrorCode::kUnsupportedMetadata,
                    "unsupported relocation type " + std::to_string(type) +
                        " in '" + sec_name(rela.info) + "' targeting " +
                        (target_exec ? "executable" : "data") + " section '" +
                        sec_name(rela.info) + "'",
                    Error::invalid_argument("")));
            }
            ctx->warnings.push_back(LoadWarning{
                "unsupported relocation type " + std::to_string(type) +
                " in '" + sec_name(rela.info) +
                "' (inspection mode) skipped"});
            continue;
        }
        if (!range_fits(r_off, width, target.size)) {
            return Status::failure(bad_cubin(
                "relocation in '" + sec_name(rela.info) +
                    "' targets offset past end of section",
                Error::out_of_range("")));
        }
        const std::uint64_t val =
            symtab.symbols[sym].value + static_cast<std::uint64_t>(r_addend);
        const std::uint64_t dst = target.offset + r_off;
        if (!range_fits(dst, width, d.size())) {
            return Status::failure(bad_cubin(
                "relocation in '" + sec_name(rela.info) +
                    "' writes past end of file",
                Error::out_of_range("")));
        }
        std::memcpy(d.data() + dst, &val, width);
        ctx->warnings.push_back(LoadWarning{
            "applied relocation type " + std::to_string(type) + " in '" +
            sec_name(rela.info) + "'"});
    }
    return Status::success();
}

}  // namespace

StatusOr<Module> Module::load(std::vector<std::uint8_t> data) {
    // Shared implementation: strict executable mode.
    return load_impl(std::move(data), false);
}

StatusOr<Module> Module::load_for_inspection(
    std::vector<std::uint8_t> data) {
    return load_impl(std::move(data), true);
}

StatusOr<Module> Module::load_impl(std::vector<std::uint8_t> data,
                                   bool inspect_mode) {
    Module m;
    m.data_ = std::move(data);
    const auto& d = m.data_;
    LoadContext ctx;
    ctx.inspect_mode = inspect_mode;
    m.executable_ = !inspect_mode;

    // --- ELF header -----------------------------------------------------
    if (d.size() < 64) {
        return Result<Module>::failure(bad_cubin(
            "cubin too small for an ELF64 header",
            Error::invalid_argument(std::to_string(d.size()) + " bytes")));
    }
    if (!(d[0] == 0x7f && d[1] == 'E' && d[2] == 'L' && d[3] == 'F')) {
        return Result<Module>::failure(bad_cubin(
            "not an ELF file",
            Error::invalid_argument("bad magic")));
    }
    if (d[4] != 2 || d[5] != 1) {
        return Result<Module>::failure(bad_cubin(
            "not a 64-bit little-endian ELF",
            Error::invalid_argument("class/data mismatch")));
    }
    const std::uint16_t machine = rd16(d, 18, &ctx.err);
    if (!ctx.err.ok() || machine != kMachineCuda) {
        return Result<Module>::failure(bad_cubin(
            "not a CUDA cubin (e_machine != EM_CUDA)",
            Error::invalid_argument("machine=" + std::to_string(machine))));
    }
    m.osabi_ = d[7];
    m.abi_version_ = d[8];
    m.e_flags_ = rd32(d, 48, &ctx.err);
    if (!ctx.err.ok()) return Result<Module>::failure(ctx.err);
    if (m.e_flags_ != kFlagsSm120) {
        return Result<Module>::failure(bad_cubin(
            "not an sm120 cubin (e_flags mismatch)",
            Error::invalid_argument("e_flags=0x" + [&]() {
                char b[16];
                std::snprintf(b, sizeof(b), "%08x", m.e_flags_);
                return std::string(b);
            }())));
    }
    // OSABI/ABI version allowlist (P2-GAP-07): a raw sm120 cubin must carry
    // the CUDA ELF OSABI and the sm120 ABI version.
    if (m.osabi_ != kOsabiCuda || m.abi_version_ != kAbiVersionSm120) {
        return Result<Module>::failure(bad_cubin(
            "not an sm120 cubin (OSABI/ABI version mismatch)",
            Error::invalid_argument("osabi=0x" + [&]() {
                char b[8];
                std::snprintf(b, sizeof(b), "%02x", m.osabi_);
                return std::string(b);
            }() + " abi_version=0x" + [&]() {
                char b[8];
                std::snprintf(b, sizeof(b), "%02x", m.abi_version_);
                return std::string(b);
            }())));
    }

    const std::uint64_t shoff = rd64(d, 40, &ctx.err);
    const std::uint16_t shentsize = rd16(d, 58, &ctx.err);
    const std::uint16_t shnum = rd16(d, 60, &ctx.err);
    const std::uint16_t shstrndx = rd16(d, 62, &ctx.err);
    if (!ctx.err.ok()) return Result<Module>::failure(ctx.err);
    if (shnum == 0 || shentsize < 64) {
        return Result<Module>::failure(bad_cubin(
            "empty or malformed section header table",
            Error::invalid_argument("shnum=" + std::to_string(shnum))));
    }
    // Overflow-safe section-header-table bounds.
    if (shnum > (std::numeric_limits<std::uint64_t>::max() - shoff) / shentsize ||
        !range_fits(shoff, static_cast<std::uint64_t>(shnum) * shentsize,
                    d.size())) {
        return Result<Module>::failure(bad_cubin(
            "section header table past end of file",
            Error::out_of_range("shoff=0x" + std::to_string(shoff))));
    }

    // --- Section headers -------------------------------------------------
    std::uint64_t shstr_off = 0, shstr_size = 0;
    std::vector<RawSection> raw(shnum);
    for (std::uint16_t i = 0; i < shnum; ++i) {
        const std::uint64_t sh = shoff + static_cast<std::uint64_t>(i) * shentsize;
        raw[i].name_off = rd32(d, sh, &ctx.err);
        raw[i].type = rd32(d, sh + 4, &ctx.err);
        raw[i].flags = rd64(d, sh + 8, &ctx.err);
        raw[i].offset = rd64(d, sh + 24, &ctx.err);
        raw[i].size = rd64(d, sh + 32, &ctx.err);
        raw[i].link = rd32(d, sh + 40, &ctx.err);
        raw[i].info = rd32(d, sh + 44, &ctx.err);
        raw[i].align = rd64(d, sh + 48, &ctx.err);
        raw[i].entsize = rd64(d, sh + 56, &ctx.err);
        if (!ctx.err.ok()) return Result<Module>::failure(ctx.err);
        raw[i].nobits = raw[i].type == kShTypeNobits;
        if (!raw[i].nobits && !range_fits(raw[i].offset, raw[i].size,
                                          d.size())) {
            return Result<Module>::failure(bad_cubin(
                "section " + std::to_string(i) + " data past end of file",
                Error::out_of_range("offset=0x" +
                                    std::to_string(raw[i].offset) + " size=0x" +
                                    std::to_string(raw[i].size))));
        }
        if (i == shstrndx) {
            shstr_off = raw[i].offset;
            shstr_size = raw[i].size;
        }
    }
    if (shstrndx >= shnum || shstr_size == 0) {
        return Result<Module>::failure(bad_cubin(
            "missing .shstrtab", Error::invalid_argument("shstrndx=" +
                                                         std::to_string(shstrndx))));
    }

    // Section names (invalid sh_name is a hard error, not empty).
    for (std::uint16_t i = 0; i < shnum; ++i) {
        if (raw[i].name_off >= shstr_size) {
            return Result<Module>::failure(bad_cubin(
                "section " + std::to_string(i) + " has invalid sh_name 0x" +
                    std::to_string(raw[i].name_off),
                Error::out_of_range("")));
        }
        raw[i].name = read_cstr(d, shstr_off, shstr_size,
                                raw[i].name_off, &ctx.err);
        if (!ctx.err.ok()) return Result<Module>::failure(ctx.err);
        SectionInfo si;
        si.name = raw[i].name;
        si.type = raw[i].type;
        si.flags = raw[i].flags;
        si.offset = raw[i].offset;
        si.size = raw[i].size;
        si.link = raw[i].link;
        si.info = raw[i].info;
        si.align = raw[i].align;
        si.entsize = raw[i].entsize;
        si.nobits = raw[i].nobits;
        m.sections_.push_back(std::move(si));
    }

    // --- Symbol tables: resolve through each symtab's own sh_link -------
    // (P2-GAP-06: never guess a global .strtab by name.)
    std::vector<ParsedSymtab> symtabs;
    for (std::uint16_t i = 0; i < shnum; ++i) {
        if (raw[i].type != kShTypeSymtab) continue;
        if (raw[i].entsize < 24) {
            return Result<Module>::failure(bad_cubin(
                "malformed .symtab entry size",
                Error::invalid_argument("section " + std::to_string(i) +
                                        " entsize=" +
                                        std::to_string(raw[i].entsize))));
        }
        if (raw[i].size % raw[i].entsize != 0) {
            return Result<Module>::failure(bad_cubin(
                "malformed .symtab size",
                Error::invalid_argument("section " + std::to_string(i) +
                                        " size not a multiple of entsize")));
        }
        if (raw[i].link >= shnum || raw[raw[i].link].type != kShTypeStrtab) {
            return Result<Module>::failure(bad_cubin(
                "symtab " + std::to_string(i) +
                    " has invalid sh_link (not a strtab)",
                Error::invalid_argument("")));
        }
        ParsedSymtab st;
        st.section = i;
        st.strtab_off = raw[raw[i].link].offset;
        st.strtab_size = raw[raw[i].link].size;
        const std::uint64_t nsyms = raw[i].size / raw[i].entsize;
        st.symbols.reserve(nsyms);
        for (std::uint64_t s = 0; s < nsyms; ++s) {
            const std::uint64_t so = raw[i].offset + s * raw[i].entsize;
            const std::uint32_t name_off = rd32(d, so, &ctx.err);
            const std::uint8_t info = d[so + 4];
            const std::uint8_t other = d[so + 5];
            const std::uint16_t shndx = rd16(d, so + 6, &ctx.err);
            const std::uint64_t value = rd64(d, so + 8, &ctx.err);
            const std::uint64_t size = rd64(d, so + 16, &ctx.err);
            if (!ctx.err.ok()) return Result<Module>::failure(ctx.err);
            // Validate st_shndx: must be a valid section index or a
            // special value (SHN_UNDEF=0; SHN_ABS=0xfff1, SHN_COMMON=0xfff2).
            if (shndx >= shnum && shndx != 0xfff1 && shndx != 0xfff2) {
                return Result<Module>::failure(bad_cubin(
                    "symtab " + std::to_string(i) + " entry " +
                        std::to_string(s) + " has invalid st_shndx " +
                        std::to_string(shndx),
                    Error::out_of_range("")));
            }
            RawSymbol sym;
            sym.bind = info >> 4;
            sym.type = info & 0xF;
            sym.other = other;
            sym.shndx = shndx;
            sym.value = value;
            sym.size = size;
            if (name_off < st.strtab_size) {
                sym.name = read_cstr(d, st.strtab_off, st.strtab_size,
                                     name_off, &ctx.err);
                if (!ctx.err.ok()) return Result<Module>::failure(ctx.err);
            }
            st.symbols.push_back(std::move(sym));
        }
        symtabs.push_back(std::move(st));
    }
    // The public symbol list is the first (primary) symtab's entries.
    for (const auto& st : symtabs) {
        if (st.section == 3 || m.symbols_.empty()) {
            for (const auto& s : st.symbols) {
                SymbolInfo si;
                si.name = s.name;
                si.bind = s.bind;
                si.type = s.type;
                si.other = s.other;
                si.shndx = s.shndx;
                si.value = s.value;
                si.size = s.size;
                m.symbols_.push_back(si);
            }
            break;
        }
    }
    // Fallback: first symtab in table order when section 3 is absent.
    if (m.symbols_.empty() && !symtabs.empty()) {
        for (const auto& s : symtabs[0].symbols) {
            SymbolInfo si;
            si.name = s.name;
            si.bind = s.bind;
            si.type = s.type;
            si.other = s.other;
            si.shndx = s.shndx;
            si.value = s.value;
            si.size = s.size;
            m.symbols_.push_back(si);
        }
    }

    // --- Relocations ------------------------------------------------------
    for (std::uint16_t i = 0; i < shnum; ++i) {
        if (raw[i].type != kShTypeRela) continue;
        Status st = apply_relocations(m.data_, raw[i], symtabs, raw,
                                      /*section_names=*/[&]() {
                                          std::vector<std::string> n;
                                          for (const auto& r : raw)
                                              n.push_back(r.name);
                                          return n;
                                      }(),
                                      &ctx);
        if (st.failed()) return Result<Module>::failure(st.take_error());
    }

    // --- .nv.info (device-wide) + per-kernel ------------------------------
    struct InfoSection {
        std::uint16_t sec_idx;
        std::uint16_t text_sec;  // 0xffff when device-wide
    };
    std::vector<InfoSection> info_secs;
    std::uint16_t device_info = 0xffff;
    for (std::uint16_t i = 0; i < shnum; ++i) {
        const std::string& n = raw[i].name;
        if (raw[i].type != kShTypeCudaInfo) continue;
        if (n == ".nv.info") {
            device_info = i;
        } else if (n.rfind(".nv.info.", 0) == 0) {
            info_secs.push_back(InfoSection{i, static_cast<std::uint16_t>(
                                                    raw[i].info)});
        }
    }

    // Kernel detection: global function symbols with STO_ENTRY whose shndx
    // points at an executable .text.* section.
    std::vector<std::uint16_t> text_secs;
    for (std::uint16_t i = 0; i < shnum; ++i) {
        if ((raw[i].flags & (kShfAlloc | kShfExec)) == (kShfAlloc | kShfExec) &&
            raw[i].name.rfind(".text.", 0) == 0) {
            text_secs.push_back(i);
        }
    }

    for (const auto& sym : m.symbols_) {
        if (sym.bind != kStbGlobal || sym.type != kSttFunc ||
            (sym.other & kStoEntry) == 0)
            continue;
        const auto it = std::find(text_secs.begin(), text_secs.end(),
                                  sym.shndx);
        if (it == text_secs.end()) continue;
        Kernel k;
        k.symbol_name = sym.name;
        k.text_section = sym.shndx;
        const RawSection& t = raw[sym.shndx];
        k.text_offset = t.offset;
        k.text_size = t.size;

        // P2-GAP-04: executable SASS text must be 16-byte aligned.
        if (k.text_size % kInstrSize != 0) {
            return Result<Module>::failure(bad_cubin(
                "kernel '" + k.symbol_name + "' text size " +
                    std::to_string(k.text_size) +
                    " is not a multiple of 16",
                Error::invalid_argument("")));
        }
        // sh_addralign == 0 is NOT an exemption: a raw cubin must declare
        // the full sm120 text alignment (128), not default to unaligned.
        if (t.align < kTextAlign) {
            return Result<Module>::failure(bad_cubin(
                "kernel '" + k.symbol_name + "' text section alignment " +
                    std::to_string(t.align) + " below " +
                    std::to_string(kTextAlign),
                Error::invalid_argument("")));
        }
        // Function symbol range must lie within the text section.
        if (sym.size > k.text_size ||
            sym.value > k.text_size - sym.size) {
            return Result<Module>::failure(bad_cubin(
                "kernel '" + k.symbol_name + "' symbol range [0x" +
                    std::to_string(sym.value) + ",+0x" +
                    std::to_string(sym.size) + ") outside text section " +
                    std::to_string(k.text_size) + " bytes",
                Error::out_of_range("")));
        }

        // Per-kernel info section: sh_info == this text section index.
        for (const auto& inf : info_secs) {
            if (inf.text_sec != sym.shndx) continue;
            NvInfoAttrs attrs;
            const RawSection& is = raw[inf.sec_idx];
            std::uint64_t cur = 0;
            EiaRecord rec;
            Error perr;
            while (eia_next(d, is.offset, is.size, &cur, &rec, &perr)) {
                parse_eia_record(rec, d, &attrs, ctx.inspect_mode, &perr);
                if (!perr.ok()) {
                    perr.push_context("while parsing EIATTR in section '" +
                                      raw[inf.sec_idx].name + "'");
                    return Result<Module>::failure(std::move(perr));
                }
            }
            if (!perr.ok()) return Result<Module>::failure(std::move(perr));
            k.meta.regcount = attrs.regcount;
            k.meta.maxreg = attrs.maxreg;
            k.meta.num_barriers = attrs.num_barriers;
            k.meta.num_mbarriers = attrs.num_mbarriers;
            k.meta.cuda_api_version = attrs.cuda_api_version;
            k.meta.cbank_param_size = attrs.cbank_param_size;
            k.meta.exit_offsets = std::move(attrs.exit_offsets);
            k.meta.mbarrier_offsets = std::move(attrs.mbarrier_offsets);
            k.meta.cluster_dims = attrs.cluster_dims;
            k.meta.explicit_cluster = attrs.explicit_cluster;
            k.meta.frame_size = attrs.frame_size;
            k.meta.min_stack_size = attrs.min_stack_size;
            k.meta.max_stack_size = attrs.max_stack_size;
            k.meta.has_stack_metadata = attrs.has_stack_metadata;
            for (auto& w : attrs.warnings) m.warnings_.push_back(std::move(w));

            // P2-GAP-02: validate + normalize KPARAM order.
            Status kp = normalize_kparams(std::move(attrs.kparams),
                                          k.meta.cbank_param_size,
                                          &k.meta.params);
            if (kp.failed()) {
                // Take the error exactly once (the second take_error on a
                // moved-from Status yields an empty error).
                Error kp_err = kp.take_error();
                kp_err.push_context("in kernel '" + k.symbol_name + "'");
                return Result<Module>::failure(std::move(kp_err));
            }
            break;
        }

        // Device-wide .nv.info: REGCOUNT / FRAME_SIZE etc. carry their own
        // func_sym symbol index; match by symbol position in m.symbols_.
        if (device_info != 0xffff) {
            const RawSection& is = raw[device_info];
            std::uint64_t cur = 0;
            EiaRecord rec;
            Error perr;
            const std::uint64_t sym_idx =
                static_cast<std::uint64_t>(&sym - m.symbols_.data());
            while (eia_next(d, is.offset, is.size, &cur, &rec, &perr)) {
                if (rec.etype == kEiaRegcount && rec.payload_size >= 8 &&
                    rd32(d, rec.payload_off, &perr) == sym_idx) {
                    if (perr.ok()) {
                        k.meta.regcount = rd32(d, rec.payload_off + 4, &perr);
                    }
                }
                if (rec.etype == kEiaFrameSize && rec.payload_size >= 8 &&
                    rd32(d, rec.payload_off, &perr) == sym_idx && perr.ok()) {
                    k.meta.frame_size = rd32(d, rec.payload_off + 4, &perr);
                    k.meta.has_stack_metadata = perr.ok();
                }
                if (rec.etype == kEiaMinStackSize && rec.payload_size >= 8 &&
                    rd32(d, rec.payload_off, &perr) == sym_idx && perr.ok()) {
                    k.meta.min_stack_size = rd32(d, rec.payload_off + 4, &perr);
                    k.meta.has_stack_metadata = perr.ok();
                }
                if (rec.etype == kEiaMaxStackSize && rec.payload_size >= 8 &&
                    rd32(d, rec.payload_off, &perr) == sym_idx && perr.ok()) {
                    k.meta.max_stack_size = rd32(d, rec.payload_off + 4, &perr);
                    k.meta.has_stack_metadata = perr.ok();
                }
                if (!perr.ok()) break;
            }
            if (!perr.ok()) return Result<Module>::failure(std::move(perr));
        }

        // Per-kernel section associations via ELF sh_info links (P2-GAP-01):
        // .nv.constant0.<name> / .nv.shared.<name> / .nv.local.<name> all
        // point at this kernel's text section through sh_info.
        for (std::uint16_t i = 0; i < shnum; ++i) {
            if (raw[i].info != sym.shndx) continue;
            const std::string& n = raw[i].name;
            KernelSectionRef ref;
            ref.section_index = i;
            ref.size = raw[i].size;
            ref.align = raw[i].align;
            ref.nobits = raw[i].nobits;
            if (n.rfind(".nv.constant0.", 0) == 0) {
                k.constant0 = ref;
            } else if (n.rfind(".nv.shared.", 0) == 0) {
                k.shared = ref;
                if (ref.nobits) {
                    k.meta.static_shared =
                        ref.size > 0x400 ? ref.size - 0x400 : ref.size;
                }
            } else if (n.rfind(".nv.local.", 0) == 0) {
                k.local = ref;
            }
        }

        // Pre-decode the kernel text: one stable IR entry per word
        // (P2-GAP-03).  Illegal/ambiguous words are kept with a diagnosis.
        k.predecoded.reserve(k.text_size / kInstrSize);
        const Decoder& dec = Decoder::instance();
        for (std::uint64_t off = 0; off + kInstrSize <= k.text_size;
             off += kInstrSize) {
            PredecodedWord w;
            w.pc = off;
            w.file_offset = k.text_offset + off;
            std::memcpy(&w.lo, d.data() + k.text_offset + off, 8);
            std::memcpy(&w.hi, d.data() + k.text_offset + off + 8, 8);
            DecodeResult r = dec.decode(w.lo, w.hi);
            if (r.is_unique()) {
                w.unique = true;
                w.inst = std::make_unique<DecodedInstruction>(r.instruction());
                // Kernel-relative PC (matching PredecodedWord::pc); the
                // file offset lives in PredecodedWord::file_offset.
                w.inst->pc = off;
            } else if (r.outcome() == DecodeOutcome::kAmbiguous) {
                w.reason = "ambiguous (" + std::to_string(r.candidates().size()) +
                           " candidates)";
                if (!ctx.inspect_mode) {
                    return Result<Module>::failure(Error(
                        ErrorCode::kBadCubin,
                        "kernel '" + k.symbol_name + "' word at +0x" +
                            [&]() {
                                char b[16];
                                std::snprintf(b, sizeof(b), "%llx",
                                              static_cast<unsigned long long>(
                                                  off));
                                return std::string(b);
                            }() + " decodes ambiguously",
                        Error::invalid_argument("")));
                }
            } else {
                w.reason = "illegal (" + std::to_string(r.candidates().size()) +
                           " candidates rejected)";
                if (!ctx.inspect_mode) {
                    return Result<Module>::failure(Error(
                        ErrorCode::kBadCubin,
                        "kernel '" + k.symbol_name + "' word at +0x" +
                            [&]() {
                                char b[16];
                                std::snprintf(b, sizeof(b), "%llx",
                                              static_cast<unsigned long long>(
                                                  off));
                                return std::string(b);
                            }() + " decodes as illegal",
                        Error::invalid_argument("")));
                }
            }
            k.predecoded.push_back(std::move(w));
        }

        m.kernels_.push_back(std::move(k));
    }

    for (auto& w : ctx.warnings) m.warnings_.push_back(std::move(w));
    return Result<Module>::success(std::move(m));
}

const Kernel* Module::find_kernel(const std::string& symbol_name) const {
    for (const auto& k : kernels_) {
        if (k.symbol_name == symbol_name) return &k;
    }
    return nullptr;
}

std::span<const std::uint8_t> Module::section_view(
    std::uint32_t section_index) const {
    if (section_index >= sections_.size()) return {};
    const SectionInfo& s = sections_[section_index];
    if (s.nobits) return {};
    if (!range_fits(s.offset, s.size, data_.size())) return {};
    return std::span<const std::uint8_t>(data_.data() + s.offset,
                                         static_cast<std::size_t>(s.size));
}

const PredecodedWord* Module::word_at(const Kernel& kernel,
                                      std::uint64_t kernel_pc) const {
    if (kernel_pc % kInstrSize != 0) return nullptr;
    const std::uint64_t idx = kernel_pc / kInstrSize;
    if (idx >= kernel.predecoded.size()) return nullptr;
    const PredecodedWord& w = kernel.predecoded[idx];
    if (w.pc != kernel_pc) return nullptr;
    return &w;
}

const KernelParam* KernelMetadata::param_by_ordinal(
    std::uint32_t ordinal) const {
    for (const auto& p : params) {
        if (p.ordinal == ordinal) return &p;
    }
    return nullptr;
}

}  // namespace semu
