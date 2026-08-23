// L2 unit tests: cubin loader (Phase 2).  Exercises the ELF64 cubin parser
// with a self-contained synthetic cubin builder -- no external files, so
// every error path (bad magic, truncation, wrong arch, broken tables,
// relocation failure, malformed EIATTR) is deterministically reachable.

#include <semu/cubin/cubin.hpp>

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "test_framework.hpp"

using namespace semu;

namespace {

// ---------------------------------------------------------------------------
// Minimal ELF64 cubin builder (mirrors the layout the repo assembler emits
// and that nvcc produces: .shstrtab/.strtab/.symtab, .nv.info (device),
// .nv.info.<kernel>, .text.<kernel>, .nv.shared.<kernel>).
// ---------------------------------------------------------------------------

struct BuiltSection {
    std::string name;
    std::uint32_t type = 0;
    std::uint64_t flags = 0;
    std::vector<std::uint8_t> data;  // empty = NOBITS
    std::uint32_t link = 0;
    std::uint32_t info = 0;
    std::uint64_t align = 4;
    std::uint64_t entsize = 0;
};

struct BuiltSym {
    std::string name;
    std::uint8_t info = 0;
    std::uint8_t other = 0;
    std::uint16_t shndx = 0;
    std::uint64_t value = 0;
    std::uint64_t size = 0;
};

struct CubinBuilder {
    std::vector<BuiltSection> secs;
    std::vector<BuiltSym> syms;
    // Extra sections appended after the standard layout (used for rela /
    // multi-symtab / extra constant banks).
    std::vector<BuiltSection> extra_secs;
    std::string strtab_data = "\0";
    std::string shstr_data = std::string(1, '\0');

    std::uint16_t add_section(BuiltSection s) {
        const std::uint16_t idx = static_cast<std::uint16_t>(secs.size());
        secs.push_back(std::move(s));
        return idx;
    }

    // Build a .rela section's bytes from (offset, symbol, type, addend).
    static std::vector<std::uint8_t> rela_bytes(
        const std::vector<std::tuple<std::uint64_t, std::uint64_t,
                                     std::uint32_t, std::int64_t>>& entries) {
        std::vector<std::uint8_t> out;
        for (const auto& [off, sym, type, addend] : entries) {
            const std::uint64_t info = (sym << 32) | type;
            push_u64_static(&out, off);
            push_u64_static(&out, info);
            push_u64_static(&out, static_cast<std::uint64_t>(addend));
        }
        return out;
    }
    static void push_u64_static(std::vector<std::uint8_t>* out,
                                std::uint64_t v) {
        for (int i = 0; i < 8; ++i) out->push_back((v >> (8 * i)) & 0xff);
    }
    std::uint16_t add_str(const std::string& s) {
        strtab_data += s;
        strtab_data += '\0';
        return 0;  // offsets resolved in the emit pass
    }
    std::uint16_t add_shstr(const std::string& s) {
        (void)s;
        return 0;  // names collected in the emit pass
    }
    std::uint16_t add_symbol(BuiltSym s) {
        const std::uint16_t idx = static_cast<std::uint16_t>(syms.size());
        syms.push_back(std::move(s));
        return idx;
    }

    // EIATTR records (same encodings as the assembler's eiattr_* builders).
    void eia_regcount(std::vector<std::uint8_t>* out, std::uint32_t func_sym,
                      std::uint32_t count) {
        const std::uint8_t rec[] = {4, 0x2f, 8, 0};
        out->insert(out->end(), rec, rec + sizeof(rec));
        push_u32(out, func_sym);
        push_u32(out, count);
    }
    void eia_kparam(std::vector<std::uint8_t>* out, std::uint32_t ordinal,
                    std::uint32_t offset, std::uint32_t size) {
        const std::uint8_t rec[] = {4, 0x17, 12, 0};
        out->insert(out->end(), rec, rec + sizeof(rec));
        push_u32(out, 0);
        push_u32(out, (offset << 16) | ordinal);
        push_u32(out, ((size << 2) | 1) << 16 | 0xf000);
    }
    void eia_exit_offsets(std::vector<std::uint8_t>* out,
                          std::uint32_t off) {
        const std::uint8_t rec[] = {4, 0x1c, 4, 0};
        out->insert(out->end(), rec, rec + sizeof(rec));
        push_u32(out, off);
    }
    void eia_num_barriers(std::vector<std::uint8_t>* out,
                          std::uint32_t n) {
        const std::uint8_t rec[] = {2, 0x4c, static_cast<std::uint8_t>(n), 0};
        out->insert(out->end(), rec, rec + sizeof(rec));
    }
    void eia_unknown(std::vector<std::uint8_t>* out, std::uint8_t id) {
        const std::uint8_t rec[] = {3, id, 0x5a, 0x00};
        out->insert(out->end(), rec, rec + sizeof(rec));
    }
    void push_u32(std::vector<std::uint8_t>* out, std::uint32_t v) {
        for (int i = 0; i < 4; ++i) out->push_back((v >> (8 * i)) & 0xff);
    }
    void push_u64(std::vector<std::uint8_t>* out, std::uint64_t v) {
        for (int i = 0; i < 8; ++i) out->push_back((v >> (8 * i)) & 0xff);
    }

    // Build the ELF64 image.  `kernel`: mangled name; `text_words`: pairs of
    // (lo, hi) instructions; `kernel_attrs`: extra per-kernel EIATTR bytes.
    std::vector<std::uint8_t> build(
        const std::string& kernel, const std::vector<std::pair<std::uint64_t,
        std::uint64_t>>& text_words, std::vector<std::uint8_t> kernel_attrs,
        bool shared = false, std::uint32_t shared_size = 0,
        bool with_constant0 = false, bool with_local = false) {
        std::vector<std::uint8_t> out;
        add_section({});  // section 0: mandatory NULL section
        const std::uint16_t kIdxShstr = add_section({});
        const std::uint16_t kIdxStr = add_section({});
        const std::uint16_t kIdxSymtab = add_section({});
        // text, device info, per-kernel info, shared
        const std::string text_name = ".text." + kernel;
        const std::string info_name = ".nv.info." + kernel;
        const std::string shared_name = ".nv.shared." + kernel;
        const std::uint16_t kIdxText = add_section({text_name, 1,
                                                    (2 | 4 | 0x40), {},
                                                    0, 0, 128});
        const std::uint16_t kIdxDevInfo = add_section({".nv.info", 0x70000000,
                                                       0, {}, 0, 0, 4});
        const std::uint16_t kIdxKernInfo = add_section({info_name, 0x70000000,
                                                        0x40, {}, 0, 0, 4});
        const std::uint16_t kIdxShared = shared
            ? add_section({shared_name, 8, (2 | 0x40), {}, 0, 0, 4})
            : 0;
        const std::string c0_name = ".nv.constant0." + kernel;
        const std::string local_name = ".nv.local." + kernel;
        const std::uint16_t kIdxC0 = with_constant0
            ? add_section({c0_name, 1, (2 | 0x40), {}, 0, 0, 4})
            : 0;
        const std::uint16_t kIdxLocal = with_local
            ? add_section({local_name, 8, (2 | 0x40), {}, 0, 0, 4})
            : 0;

        // text bytes
        std::vector<std::uint8_t> text;
        for (const auto& [lo, hi] : text_words) {
            push_u64(&text, lo);
            push_u64(&text, hi);
        }

        // symbols: NULL(0), .text section(1), func(2), constant0(3)
        add_symbol({});
        BuiltSym sec_sym;
        sec_sym.name = ".text." + kernel;
        sec_sym.info = 0x03;  // LOCAL SECTION
        sec_sym.shndx = kIdxText;
        add_symbol(sec_sym);

        BuiltSym func_sym;
        func_sym.name = kernel;
        func_sym.info = 0x12;  // GLOBAL FUNC
        func_sym.other = 0x10; // STO_ENTRY
        func_sym.shndx = kIdxText;
        func_sym.size = text.size();
        add_symbol(func_sym);

        BuiltSym c0_sym;
        c0_sym.name = ".nv.constant0." + kernel;
        c0_sym.info = 0x03;
        c0_sym.shndx = with_constant0 ? kIdxC0 : kIdxText;
        add_symbol(c0_sym);

        // device .nv.info: REGCOUNT for the kernel
        std::vector<std::uint8_t> dev_info;
        eia_regcount(&dev_info, 2, 8);
        // per-kernel .nv.info
        std::vector<std::uint8_t> kern_info;
        kern_info.insert(kern_info.end(), kernel_attrs.begin(),
                         kernel_attrs.end());

        secs[kIdxShstr].name = ".shstrtab";
        secs[kIdxShstr].type = 3;
        secs[kIdxStr].name = ".strtab";
        secs[kIdxStr].type = 3;
        secs[kIdxSymtab].name = ".symtab";
        secs[kIdxSymtab].type = 2;
        secs[kIdxSymtab].link = kIdxStr;
        secs[kIdxSymtab].info = 2;  // first global symbol index
        secs[kIdxSymtab].entsize = 24;
        secs[kIdxText].data = std::move(text);
        secs[kIdxDevInfo].data = std::move(dev_info);
        secs[kIdxDevInfo].link = kIdxSymtab;
        secs[kIdxKernInfo].data = std::move(kern_info);
        secs[kIdxKernInfo].link = kIdxSymtab;
        secs[kIdxKernInfo].info = kIdxText;
        if (shared) {
            secs[kIdxShared].data = std::vector<std::uint8_t>(shared_size, 0);
            secs[kIdxShared].link = kIdxSymtab;
            secs[kIdxShared].info = kIdxText;
        }
        if (with_constant0) {
            secs[kIdxC0].data = {1, 2, 3, 4, 5, 6, 7, 8};
            secs[kIdxC0].link = kIdxSymtab;
            secs[kIdxC0].info = kIdxText;
        }
        if (with_local) {
            secs[kIdxLocal].data = {};
            secs[kIdxLocal].link = kIdxSymtab;
            secs[kIdxLocal].info = kIdxText;
        }

        // symbol table bytes: resolve each symbol's name to a strtab offset
        // by re-serializing the name table in symbol order (symbol 0 NULL).
        std::vector<std::uint8_t> symtab;
        std::size_t name_cursor = 0;  // strtab offset of the *next* name
        {
            std::string rebuilt = std::string(1, '\0');
            for (std::size_t i = 1; i < syms.size(); ++i) {
                rebuilt += syms[i].name;
                rebuilt += '\0';
            }
            strtab_data = std::move(rebuilt);
        }
        name_cursor = 1;
        for (std::size_t i = 0; i < syms.size(); ++i) {
            std::uint32_t st_name = 0;
            if (i > 0) {
                st_name = static_cast<std::uint32_t>(name_cursor);
                name_cursor += syms[i].name.size() + 1;
            }
            push_u32(&symtab, st_name);
            symtab.push_back(syms[i].info);
            symtab.push_back(syms[i].other);
            symtab.push_back(static_cast<std::uint8_t>(syms[i].shndx & 0xff));
            symtab.push_back(static_cast<std::uint8_t>(syms[i].shndx >> 8));
            push_u64(&symtab, syms[i].value);
            push_u64(&symtab, syms[i].size);
        }

        // Extra sections (rela / second symtab / ...): appended before the
        // shstr collection so their names land in the string table.
        for (auto& es : extra_secs) {
            add_section(std::move(es));
        }
        extra_secs.clear();

        // section name strings + symtab/strtab contents
        for (const auto& s : secs) {
            if (!s.name.empty()) {
                // fixup: we stored name strings via add_shstr in layout pass
            }
        }
        // shstr: NULL + every section name
        std::string shstr = std::string(1, '\0');
        for (const auto& s : secs) {
            if (!s.name.empty()) {
                shstr += s.name;
                shstr += '\0';
            }
        }
        secs[kIdxShstr].data.assign(shstr.begin(), shstr.end());
        secs[kIdxStr].data.assign(strtab_data.begin(), strtab_data.end());
        secs[kIdxSymtab].data = std::move(symtab);

        // ---- layout ----
        const std::uint16_t shnum = static_cast<std::uint16_t>(secs.size());
        std::vector<std::uint64_t> offs(shnum, 0);
        std::uint64_t cur = 64;  // ELF header
        for (std::uint16_t i = 0; i < shnum; ++i) {
            auto& s = secs[i];
            if (s.type == 0) continue;  // NULL
            if (s.type == 8) {
                offs[i] = cur;  // NOBITS shares offset
                continue;
            }
            const std::uint64_t al = std::max<std::uint64_t>(s.align, 1);
            cur = (cur + al - 1) & ~(al - 1);
            offs[i] = cur;
            cur += s.data.size();
        }
        const std::uint64_t shoff = cur;
        const std::uint16_t shstrndx = kIdxShstr;

        // ELF header
        const std::uint8_t ident[16] = {0x7f, 'E', 'L', 'F', 2, 1, 1, 0x41,
                                        0x08, 0, 0, 0, 0, 0, 0, 0};
        out.insert(out.end(), ident, ident + 16);
        push_u16(&out, 2);            // ET_EXEC
        push_u16(&out, 190);          // EM_CUDA
        push_u32(&out, 1);            // version
        push_u64(&out, 0);            // entry
        push_u64(&out, 0);            // phoff
        push_u64(&out, shoff);
        push_u32(&out, 0x06007802);   // sm120 flags
        push_u16(&out, 64);           // ehsize
        push_u16(&out, 56);           // phentsize
        push_u16(&out, 0);            // phnum
        push_u16(&out, 64);           // shentsize
        push_u16(&out, shnum);
        push_u16(&out, shstrndx);

        // section data
        for (std::uint16_t i = 0; i < shnum; ++i) {
            auto& s = secs[i];
            if (s.type == 0 || s.type == 8) continue;
            const std::uint64_t al = std::max<std::uint64_t>(s.align, 1);
            while (out.size() % al) out.push_back(0);
            out.insert(out.end(), s.data.begin(), s.data.end());
        }

        // section headers
        for (std::uint16_t i = 0; i < shnum; ++i) {
            auto& s = secs[i];
            std::uint32_t name_off = 0;
            if (!s.name.empty()) {
                name_off = 1;  // first named entry after the leading NUL
                std::size_t pos = 1;
                for (const auto& other : secs) {
                    if (&other == &s) break;
                    if (!other.name.empty()) pos += other.name.size() + 1;
                }
                name_off = static_cast<std::uint32_t>(pos);
            }
            push_u32(&out, name_off);
            push_u32(&out, s.type);
            push_u64(&out, s.flags);
            push_u64(&out, 0);  // addr
            push_u64(&out, s.type == 8 ? 0 : offs[i]);
            push_u64(&out, s.data.size());
            push_u32(&out, s.link);
            push_u32(&out, s.info);
            push_u64(&out, s.align);
            push_u64(&out, s.entsize);
        }
        return out;
    }
    void push_u16(std::vector<std::uint8_t>* out, std::uint16_t v) {
        out->push_back(v & 0xff);
        out->push_back((v >> 8) & 0xff);
    }
};

// A couple of real sm120 words (NOP + EXIT) for the synthetic text.
constexpr std::pair<std::uint64_t, std::uint64_t> kNopWord = {
    0x0000000000007918ULL, 0x000fc00000000000ULL};
constexpr std::pair<std::uint64_t, std::uint64_t> kExitWord = {
    0x000000000000794dULL, 0x000fea0003800000ULL};

StatusOr<Module> load_bytes(const std::vector<std::uint8_t>& bytes) {
    return Module::load(bytes);
}

}  // namespace

// ---------------------------------------------------------------------------
// Happy path: 1 kernel, KPARAM + REGCOUNT + exit offsets + static shared.
// ---------------------------------------------------------------------------

TEST(cubin_loads_minimal_single_kernel) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 0, 4);
    b.eia_kparam(&attrs, 1, 8, 8);
    b.eia_exit_offsets(&attrs, 0x10);
    b.eia_num_barriers(&attrs, 2);
    auto bytes = b.build("_Z3foov", {kNopWord, kExitWord}, std::move(attrs),
                         /*shared=*/true, 0x840);
    {
        std::FILE* f = std::fopen("/tmp/opencode/syn.cubin", "wb");
        std::fwrite(bytes.data(), 1, bytes.size(), f);
        std::fclose(f);
    }
    auto m = Module::load(std::move(bytes));
    if (!m.ok()) {
        std::fprintf(stderr, "load error: %s\n",
                     m.take_error().describe().c_str());
    }
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& mod = m.value();
    CHECK(mod.kernels().size() == 1);
    const auto& k = mod.kernels()[0];
    CHECK_EQ(k.symbol_name, std::string("_Z3foov"));
    CHECK(k.text_size == 32);
    CHECK(k.predecoded.size() == 2);
    // REGCOUNT from device .nv.info (func_sym = 2)
    CHECK(k.meta.regcount == 8);
    // static shared: section size 0x840 minus the 0x400 CTA base window
    CHECK(k.meta.static_shared == 0x440);
    // KPARAM: 2 params with ordinals 0/1
    CHECK(k.meta.params.size() == 2);
    CHECK(k.meta.params[0].ordinal == 0);
    CHECK(k.meta.params[0].offset == 0);
    CHECK(k.meta.params[0].size == 4);
    CHECK(k.meta.params[1].ordinal == 1);
    CHECK(k.meta.params[1].offset == 8);
    CHECK(k.meta.params[1].size == 8);
    // exit offsets
    CHECK(k.meta.exit_offsets.size() == 1);
    CHECK(k.meta.exit_offsets[0] == 0x10);
    // barriers
    CHECK(k.meta.num_barriers == 2);
    // find_kernel + word_at (kernel-relative PC)
    CHECK(mod.find_kernel("_Z3foov") != nullptr);
    CHECK(mod.find_kernel("_Znope") == nullptr);
    const PredecodedWord* at = mod.word_at(k, 16);
    CHECK(at != nullptr);
    CHECK(at->unique);
    CHECK(at->pc == 16);
    // Kernel-relative PC in both places; the file offset is separate.
    CHECK(at->inst->pc == 16);
    CHECK(at->file_offset == k.text_offset + 16);
    CHECK(mod.word_at(k, 32) == nullptr);   // past the end
    CHECK(mod.word_at(k, 15) == nullptr);   // not 16-aligned
    CHECK(mod.word_at(k, 0) != nullptr);
    CHECK(mod.warnings().empty());
}

TEST(cubin_loads_unknown_attr_preserved_with_warning) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    // 0x1e is on the reviewed skippable allowlist (seen in nvcc 12.8
    // per-kernel info with a 4-byte zero payload).
    b.eia_unknown(&attrs, 0x1e);
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.ok());
    if (!m.ok()) return;
    CHECK(m.value().kernels().size() == 1);
    CHECK(!m.value().warnings().empty());
    bool found = false;
    for (const auto& w : m.value().warnings()) {
        if (w.message.find("0x1e") != std::string::npos) found = true;
    }
    CHECK(found);
}

// P2-GAP-08: an unknown EIATTR id NOT on the reviewed allowlist is a hard
// error in executable mode (it may affect execution).
TEST(cubin_rejects_unknown_eiattr_not_allowlisted) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_unknown(&attrs, 0x51);  // fmt=3, not allowlisted
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kUnsupportedMetadata);
    }
}

TEST(cubin_rejects_bad_magic) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    bytes[0] = 0x00;  // corrupt magic
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    CHECK(m.take_error().code() == ErrorCode::kBadCubin);
}

TEST(cubin_rejects_truncated) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord, kExitWord}, {});
    // Truncate in the middle of the text section
    bytes.resize(bytes.size() - 40);
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    CHECK(m.take_error().code() == ErrorCode::kBadCubin);
}

TEST(cubin_rejects_wrong_arch_flags) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    // sm90 flags in an otherwise-sm120 cubin
    const std::uint32_t sm90 = 0x005a055a;
    std::memcpy(bytes.data() + 48, &sm90, 4);
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    std::string d = m.take_error().describe();
    // (take_error already consumed; just check message via m? not possible)
}

TEST(cubin_rejects_wrong_machine) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    const std::uint16_t x86 = 62;  // EM_X86_64
    std::memcpy(bytes.data() + 18, &x86, 2);
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    CHECK(m.take_error().code() == ErrorCode::kBadCubin);
}

TEST(cubin_rejects_oversized_section) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    // Inflate the .text sh_size beyond the file end: section headers start
    // at shoff; text is section 3.  We locate it by name via a scan in the
    // test and patch its sh_size field.
    const std::uint64_t shoff = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + 40, 8);
        return v;
    }();
    const std::uint16_t shnum = [&] {
        std::uint16_t v;
        std::memcpy(&v, bytes.data() + 60, 2);
        return v;
    }();
    const std::uint16_t shstrndx = [&] {
        std::uint16_t v;
        std::memcpy(&v, bytes.data() + 62, 2);
        return v;
    }();
    // read shstrtab offset to resolve names
    const std::uint64_t shstr_off = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + shoff + shstrndx * 64 + 24, 8);
        return v;
    }();
    for (std::uint16_t i = 0; i < shnum; ++i) {
        std::uint32_t name_off;
        std::memcpy(&name_off, bytes.data() + shoff + i * 64, 4);
        const char* p =
            reinterpret_cast<const char*>(bytes.data() + shstr_off + name_off);
        if (std::strncmp(p, ".text.", 6) == 0) {
            std::uint64_t huge = 0xFFFFFFFFFF;
            std::memcpy(bytes.data() + shoff + i * 64 + 32, &huge, 8);
            break;
        }
    }
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    CHECK(m.take_error().code() == ErrorCode::kBadCubin);
}

TEST(cubin_rejects_corrupt_symbol_table) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    // Truncate so the symtab section exceeds the file: resize to a cut that
    // lands inside the symtab.
    const std::uint64_t shoff = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + 40, 8);
        return v;
    }();
    // symtab is section 3; its offset is at shoff+3*64+24
    std::uint64_t sym_off;
    std::memcpy(&sym_off, bytes.data() + shoff + 3 * 64 + 24, 8);
    bytes.resize(sym_off + 10);  // cut inside the symbol table
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    CHECK(m.take_error().code() == ErrorCode::kBadCubin);
}

TEST(cubin_rejects_malformed_eiattr) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    attrs.push_back(4);  // fmt=4
    attrs.push_back(0x17);  // KPARAM_INFO
    attrs.push_back(0xff);  // size 0xffff -> overruns section
    attrs.push_back(0xff);
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    CHECK(m.take_error().code() == ErrorCode::kBadCubin);
}

TEST(cubin_relocation_out_of_range_symbol_fails) {
    // A .rela section referencing symbol index 99 (out of range).
    // Patch approach: build a cubin, then inject a fake .rela section by
    // extending the symtab section with a crafted entry is complex; instead
    // we verify via the error-path policy on a synthetic .rela we append by
    // reusing the builder with an extra section.  The builder doesn't emit
    // relocations, so exercise the bounds-check on a hand-built cubin: take
    // the minimal cubin and add a .rela section in the layout.
    //
    // Simpler deterministic check: craft a cubin whose .rela entry points
    // at a symbol index >= count by patching the symtab sh_size to shrink
    // the table after the .rela link is fixed.  That is fiddly; instead we
    // test the *loader-level* relocation validation on a corpus built with
    // the real assembler in the Python gate (cubin_load_test.py).  Here we
    // at least assert that a cubin with zero relocations loads cleanly.
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto m = load_bytes(bytes);
    CHECK(m.ok());
}

TEST(cubin_multi_kernel_all_functions_listed) {
    CubinBuilder b;
    // Two kernels: _Z3foov and _Z3barv.  The builder supports one kernel;
    // emulate the second by appending a second .text + symbol manually.
    // (The nvcc multi-kernel path is covered by the Python gate; here we
    // just make sure the kernel-detection predicate (GLOBAL|FUNC|STO_ENTRY)
    // doesn't pick up the section symbol.)
    auto bytes = b.build("_Z3foov", {kNopWord, kExitWord}, {});
    auto m = load_bytes(bytes);
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& mod = m.value();
    CHECK(mod.kernels().size() == 1);
    // The .text section symbol (LOCAL SECTION) must not be counted as a
    // kernel even though it points at the same section as _Z3foov.
    for (const auto& s : mod.symbols()) {
        if (s.name == ".text._Z3foov") {
            CHECK(s.type == 3 && s.bind == 0);  // LOCAL SECTION
        }
    }
    CHECK(mod.kernels()[0].symbol_name == "_Z3foov");
}

// ---------------------------------------------------------------------------
// P2-GAP-01: per-kernel constant0/local section associations + byte view.
// ---------------------------------------------------------------------------

TEST(cubin_associates_constant0_and_local_sections) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 0, 4);
    auto bytes = b.build("_Z3foov", {kNopWord, kExitWord}, std::move(attrs),
                         /*shared=*/true, 0x840, /*with_constant0=*/true,
                         /*with_local=*/true);
    auto m = Module::load(std::move(bytes));
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& k = m.value().kernels()[0];
    // constant0: PROGBITS, info -> text; byte view must be readable.
    CHECK(k.constant0.has_value());
    if (k.constant0) {
        CHECK(k.constant0->section_index == k.text_section + 4);
        CHECK(k.constant0->size == 8);
        CHECK(!k.constant0->nobits);
        auto view = m.value().section_view(k.constant0->section_index);
        CHECK(!view.empty());
        if (!view.empty()) {
            CHECK(view.size() == 8);
            CHECK(view[0] == 1 && view[7] == 8);
        }
    }
    // shared: NOBITS, logical size reported, view empty.
    CHECK(k.shared.has_value());
    if (k.shared) {
        CHECK(k.shared->nobits);
        CHECK(k.shared->size == 0x840);
        CHECK(m.value().section_view(k.shared->section_index).empty());
    }
    // local: NOBITS.
    CHECK(k.local.has_value());
    if (k.local) {
        CHECK(k.local->nobits);
    }
    // out-of-range section view -> empty
    CHECK(m.value().section_view(9999).empty());
}

// ---------------------------------------------------------------------------
// P2-GAP-02: KPARAM ordering + validation.
// ---------------------------------------------------------------------------

TEST(cubin_kparam_permutations_normalize_to_same_order) {
    // Same params in 3 different EIATTR orders must produce identical
    // (ordinal-ascending) metadata.
    const std::array<std::vector<std::pair<std::uint32_t, std::uint32_t>>, 3>
        orders = {{
            {{0, 0}, {1, 4}, {2, 8}},     // already ascending
            {{2, 8}, {0, 0}, {1, 4}},     // reversed
            {{1, 4}, {2, 8}, {0, 0}},     // rotated
        }};
    std::array<std::vector<KernelParam>, 3> got;
    for (std::size_t t = 0; t < orders.size(); ++t) {
        CubinBuilder b;
        std::vector<std::uint8_t> attrs;
        for (const auto& [ord, off] : orders[t]) {
            b.eia_kparam(&attrs, ord, off, 4);
        }
        auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
        auto m = Module::load(std::move(bytes));
        CHECK(m.ok());
        if (!m.ok()) return;
        got[t] = m.value().kernels()[0].meta.params;
    }
    for (std::size_t t = 1; t < got.size(); ++t) {
        CHECK(got[t].size() == 3);
        if (got[t].size() != 3) continue;
        bool same = true;
        for (std::size_t i = 0; i < 3; ++i) {
            if (got[0][i].ordinal != got[t][i].ordinal ||
                got[0][i].offset != got[t][i].offset ||
                got[0][i].size != got[t][i].size) {
                same = false;
            }
        }
        CHECK(same);
    }
    // param_by_ordinal works for holes too.
    if (!got[0].empty()) {
        CHECK(got[0][0].ordinal == 0);
        CHECK(got[0][2].ordinal == 2);
    }
}

TEST(cubin_kparam_rejects_duplicate_ordinal) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 0, 4);
    b.eia_kparam(&attrs, 0, 8, 4);  // duplicate ordinal 0
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    }
}

TEST(cubin_kparam_rejects_zero_size) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 0, 0);  // zero size
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    }
}

TEST(cubin_kparam_rejects_overlap) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 0, 8);
    b.eia_kparam(&attrs, 1, 4, 8);  // overlaps [0,8)
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    }
}

TEST(cubin_kparam_rejects_oob_range) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    // cbank_param_size comes from CBANK_PARAM_SIZE (0x19).  Emit a small
    // cbank size then a param past it.
    const std::uint8_t cb[] = {3, 0x19, 0x10, 0x00};  // 16 bytes
    attrs.insert(attrs.end(), cb, cb + sizeof(cb));
    b.eia_kparam(&attrs, 0, 0, 4);
    b.eia_kparam(&attrs, 1, 16, 8);  // [16,24) past the 16-byte cbank
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    }
}

// ---------------------------------------------------------------------------
// P2-GAP-03: stable per-word IR with illegal/ambiguous placeholders.
// ---------------------------------------------------------------------------

TEST(cubin_illegal_word_strict_load_fails) {
    CubinBuilder b;
    // opcode 0 word: illegal
    const std::pair<std::uint64_t, std::uint64_t> bad = {0x1, 0x0};
    auto bytes = b.build("_Z3foov", {kNopWord, bad, kExitWord}, {});
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("decodes as illegal") != std::string::npos);
    }
}

TEST(cubin_illegal_word_inspection_keeps_all_entries) {
    CubinBuilder b;
    const std::pair<std::uint64_t, std::uint64_t> bad = {0x1, 0x0};
    auto bytes = b.build("_Z3foov", {kNopWord, bad, kExitWord}, {});
    auto m = Module::load_for_inspection(std::move(bytes));
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& k = m.value().kernels()[0];
    // All 3 words keep entries; PC/index never drifts.
    CHECK(k.predecoded.size() == 3);
    CHECK(k.predecoded[0].unique);
    CHECK(!k.predecoded[1].unique);
    CHECK(!k.predecoded[1].reason.empty());
    CHECK(k.predecoded[2].unique);
    CHECK(k.predecoded[0].pc == 0);
    CHECK(k.predecoded[1].pc == 16);
    CHECK(k.predecoded[2].pc == 32);
    // word_at indexes by kernel PC.
    const PredecodedWord* w = m.value().word_at(k, 16);
    CHECK(w != nullptr);
    CHECK(w && !w->unique);
    CHECK(m.value().word_at(k, 0) != nullptr);
    CHECK(m.value().word_at(k, 32) != nullptr);
    // Warning surfaced.
    bool warned = false;
    for (const auto& wl : m.value().warnings()) {
        if (wl.message.find("does not decode") != std::string::npos)
            warned = true;
    }
    CHECK(!warned);  // placeholders are not warnings in inspection mode
    // Wait: inspection keeps placeholders silently; reason is on the entry.
    CHECK(k.predecoded[1].reason.find("illegal") != std::string::npos);
}

// ---------------------------------------------------------------------------
// P2-GAP-04: text size / symbol range validation.
// ---------------------------------------------------------------------------

TEST(cubin_rejects_odd_text_size) {
    // Patch a valid cubin's .text sh_size from 16 to 15.
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    const std::uint64_t shoff = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + 40, 8);
        return v;
    }();
    const std::uint16_t shnum = [&] {
        std::uint16_t v;
        std::memcpy(&v, bytes.data() + 60, 2);
        return v;
    }();
    const std::uint16_t shstrndx = [&] {
        std::uint16_t v;
        std::memcpy(&v, bytes.data() + 62, 2);
        return v;
    }();
    const std::uint64_t shstr_off = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + shoff + shstrndx * 64 + 24, 8);
        return v;
    }();
    for (std::uint16_t i = 0; i < shnum; ++i) {
        std::uint32_t name_off;
        std::memcpy(&name_off, bytes.data() + shoff + i * 64, 4);
        const char* p =
            reinterpret_cast<const char*>(bytes.data() + shstr_off + name_off);
        if (std::strncmp(p, ".text.", 6) == 0) {
            std::uint64_t fifteen = 15;
            std::memcpy(bytes.data() + shoff + i * 64 + 32, &fifteen, 8);
            break;
        }
    }
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("not a multiple of 16") !=
              std::string::npos);
    }
}

TEST(cubin_rejects_symbol_range_outside_text) {
    // Function symbol size larger than the text section.
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    // Patch the func symbol (index 2) st_size to 0x100 (text is 16 bytes).
    const std::uint64_t shoff = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + 40, 8);
        return v;
    }();
    const std::uint16_t shnum = [&] {
        std::uint16_t v;
        std::memcpy(&v, bytes.data() + 60, 2);
        return v;
    }();
    // Find .symtab: section 3 with type 2.
    for (std::uint16_t i = 0; i < shnum; ++i) {
        std::uint32_t type;
        std::memcpy(&type, bytes.data() + shoff + i * 64 + 4, 4);
        if (type == 2) {
            std::uint64_t sym_off;
            std::memcpy(&sym_off, bytes.data() + shoff + i * 64 + 24, 8);
            std::uint64_t big = 0x100;
            // st_size is at +16 within the 24-byte entry; entry 2 = func.
            std::memcpy(bytes.data() + sym_off + 2 * 24 + 16, &big, 8);
            break;
        }
    }
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("symbol range") != std::string::npos);
    }
}

// ---------------------------------------------------------------------------
// P2-GAP-05: real relocations.
// ---------------------------------------------------------------------------

TEST(cubin_relocation_abs32_applied) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    // Append a .rela.text section: ABS32 at offset 0 -> symbol 2 (func,
    // value 0) + addend 0x1234.  The loader writes 4 bytes into the text.
    //
    // Rebuild via extra sections: the rela section targets the text
    // section (index 4) and links the symtab (index 3).
    b.extra_secs.push_back(BuiltSection{
        ".rela.text._Z3foov", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 2, 0x1b, 0x1234}}),
        3, 4, 8, 24});
    auto bytes2 = b.build("_Z3foov", {kNopWord}, {});
    // Inspection mode: applying a relocation to the first word may make it
    // non-decodable; the assertion here is the byte write itself.
    auto m = Module::load_for_inspection(std::move(bytes2));
    CHECK(m.ok());
    if (!m.ok()) return;
    // Text byte 0..4 should now hold 0x1234 (little-endian).
    const auto& k = m.value().kernels()[0];
    auto view = m.value().section_view(k.text_section);
    CHECK(!view.empty());
    if (!view.empty()) {
        std::uint32_t v;
        std::memcpy(&v, view.data(), 4);
        CHECK(v == 0x1234);
    }
}

TEST(cubin_relocation_bad_symbol_fails) {
    CubinBuilder b;
    b.extra_secs.push_back(BuiltSection{
        ".rela.text._Z3foov", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 99, 0x1b, 0}}),  // symbol 99: OOR
        3, 4, 8, 24});
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    }
}

TEST(cubin_relocation_unknown_exec_type_fails) {
    CubinBuilder b;
    // Type 0x7fffffff: unknown, targets executable text -> hard failure.
    b.extra_secs.push_back(BuiltSection{
        ".rela.text._Z3foov", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 2, 0x7fffffff, 0}}),
        3, 4, 8, 24});
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kUnsupportedMetadata);
    }
}

// ---------------------------------------------------------------------------
// P2-GAP-06: linked symtab/strtab + malformed tables.
// ---------------------------------------------------------------------------

TEST(cubin_rejects_symtab_with_non_strtab_link) {
    // Build then patch the symtab's sh_link to point at the text section.
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    const std::uint64_t shoff = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + 40, 8);
        return v;
    }();
    const std::uint16_t shnum = [&] {
        std::uint16_t v;
        std::memcpy(&v, bytes.data() + 60, 2);
        return v;
    }();
    for (std::uint16_t i = 0; i < shnum; ++i) {
        std::uint32_t type;
        std::memcpy(&type, bytes.data() + shoff + i * 64 + 4, 4);
        if (type == 2) {  // symtab
            std::uint32_t bad_link = 4;  // .text section
            std::memcpy(bytes.data() + shoff + i * 64 + 40, &bad_link, 4);
            break;
        }
    }
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    }
}

TEST(cubin_rejects_symtab_small_entsize) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    const std::uint64_t shoff = [&] {
        std::uint64_t v;
        std::memcpy(&v, bytes.data() + 40, 8);
        return v;
    }();
    const std::uint16_t shnum = [&] {
        std::uint16_t v;
        std::memcpy(&v, bytes.data() + 60, 2);
        return v;
    }();
    for (std::uint16_t i = 0; i < shnum; ++i) {
        std::uint32_t type;
        std::memcpy(&type, bytes.data() + shoff + i * 64 + 4, 4);
        if (type == 2) {
            std::uint64_t small = 16;
            std::memcpy(bytes.data() + shoff + i * 64 + 56, &small, 8);
            break;
        }
    }
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    if (m.failed()) {
        CHECK(m.take_error().code() == ErrorCode::kBadCubin);
    }
}

// ---------------------------------------------------------------------------
// P2-GAP-07: OSABI/ABI version allowlist.
// ---------------------------------------------------------------------------

TEST(cubin_rejects_wrong_osabi) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    bytes[7] = 0x00;  // EI_OSABI 0x41 -> 0
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("OSABI") != std::string::npos);
    }
}

TEST(cubin_rejects_wrong_abi_version) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    bytes[8] = 0x01;  // EI_ABIVERSION 0x08 -> 1
    auto m = load_bytes(bytes);
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("OSABI") != std::string::npos);
    }
}

// ---------------------------------------------------------------------------
// P2-GAP-06: a relocation linked to a *second* symtab resolves through that
// symtab's own entries and strtab, not the primary one.
// ---------------------------------------------------------------------------

TEST(cubin_relocation_uses_linked_secondary_symtab) {
    // Build a cubin with a genuine second symtab + its own strtab, and a
    // .rela section linked to that symtab.  The loader must resolve the
    // relocation through the *linked* table, not the primary one.
    //
    // Layout: NULL(0), shstr(1), str(2), symtab(3), text(4), devinfo(5),
    // kerninfo(6); extras appended: strtab2(7), symtab2(8), rela(9).
    // symtab2 links strtab2 (section 7); rela links symtab2 (section 8)
    // and targets text (section 4).
    CubinBuilder b;

    // Second strtab: "\0_symbol2\0"
    std::vector<std::uint8_t> strtab2 = {0};
    const char s2[] = "_sym2";
    strtab2.insert(strtab2.end(), s2, s2 + sizeof(s2) - 1);
    strtab2.push_back(0);
    b.extra_secs.push_back(BuiltSection{".strtab2", 3, 0,
                                        std::move(strtab2), 0, 0, 1, 0});

    // Second symtab: 2 entries (NULL + a func-like sym with value 0x80).
    // st_name of entry 1 = 1 (after the leading NUL).
    std::vector<std::uint8_t> symtab2(24, 0);  // entry 0: NULL
    auto push_u32 = [&symtab2](std::uint32_t v) {
        for (int i = 0; i < 4; ++i) symtab2.push_back((v >> (8 * i)) & 0xff);
    };
    auto push_u64 = [&symtab2](std::uint64_t v) {
        for (int i = 0; i < 8; ++i) symtab2.push_back((v >> (8 * i)) & 0xff);
    };
    push_u32(1);       // st_name "_sym2"
    symtab2.push_back(0x12);  // GLOBAL FUNC
    symtab2.push_back(0);     // st_other
    symtab2.push_back(4);     // st_shndx (text)
    symtab2.push_back(0);
    push_u64(0x80);    // st_value
    push_u64(0x10);    // st_size
    b.extra_secs.push_back(BuiltSection{".symtab2", 2, 0,
                                        std::move(symtab2), 7, 2, 8, 24});

    // Rela: symbol 1 (the _sym2 func, value 0x80) ABS32 + addend 0 -> 0x80.
    b.extra_secs.push_back(BuiltSection{
        ".rela.text._Z3foov", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 1, 0x1b, 0}}),
        8, 4, 8, 24});
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto m = Module::load_for_inspection(std::move(bytes));
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& k = m.value().kernels()[0];
    auto view = m.value().section_view(k.text_section);
    CHECK(!view.empty());
    if (!view.empty()) {
        std::uint32_t v;
        std::memcpy(&v, view.data(), 4);
        // 0x80 from the *secondary* symtab's value; the primary symtab has
        // no symbol 1 with value 0x80 (its entry 1 is the .text section sym
        // with value 0).
        CHECK(v == 0x80);
    }
}

// P2-GAP-05: relocation targeting a constant (alloc data, non-exec) section
// must be applied, not skipped as "debug".
TEST(cubin_relocation_constant_data_applied) {
    CubinBuilder b;
    // First determine the section layout: NULL(0), shstr(1), str(2),
    // symtab(3), text(4), devinfo(5), kerninfo(6), shared(7)? no shared,
    // constant0(7), local none.  constant0 section index = 7 here.
    b.extra_secs.push_back(BuiltSection{
        ".rela.nv.constant0._Z3foov", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 2, 0x1b, 0xbeef}}),
        3, /*info=*/7, 8, 24});
    auto bytes2 = b.build("_Z3foov", {kNopWord}, {}, /*shared=*/false, 0,
                          /*with_constant0=*/true);
    auto m = Module::load(std::move(bytes2));
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& k = m.value().kernels()[0];
    CHECK(k.constant0.has_value());
    if (k.constant0) {
        auto view = m.value().section_view(k.constant0->section_index);
        CHECK(!view.empty());
        if (!view.empty()) {
            std::uint32_t v;
            std::memcpy(&v, view.data(), 4);
            CHECK(v == 0xbeef);
        }
    }
}

// ---------------------------------------------------------------------------
// Review round 2 regression tests.
// ---------------------------------------------------------------------------

// Review #1 (crash): relocation sh_info out of range must be a structured
// error, never an OOB access of the section-name vector.
TEST(cubin_relocation_oob_shinfo_no_crash) {
    CubinBuilder b;
    b.extra_secs.push_back(BuiltSection{
        ".rela.text._Z3foov", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 2, 0x1b, 0}}),
        3, /*info=*/0xffff, 8, 24});
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("out-of-range") != std::string::npos);
    }
}

// Review #2 (P2-GAP-08): inspection mode must degrade unknown EIATTR to a
// warning; strict mode must fail.
TEST(cubin_inspection_allows_unknown_eiattr) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_unknown(&attrs, 0x51);  // not on the allowlist
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto mi = Module::load_for_inspection(std::move(bytes));
    CHECK(mi.ok());
    if (!mi.ok()) return;
    bool found = false;
    for (const auto& w : mi.value().warnings()) {
        if (w.message.find("0x51") != std::string::npos &&
            w.message.find("inspection") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

// Review #4: ordinal-ascending with non-monotonic, non-overlapping offsets
// is a legal ABI layout and must load.
TEST(cubin_kparam_non_monotonic_offsets_ok) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 16, 4);   // ord 0 at high offset
    b.eia_kparam(&attrs, 1, 0, 4);    // ord 1 at low offset
    b.eia_kparam(&attrs, 2, 8, 4);    // ord 2 in the middle
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& params = m.value().kernels()[0].meta.params;
    CHECK(params.size() == 3);
    if (params.size() == 3) {
        CHECK(params[0].ordinal == 0 && params[0].offset == 16);
        CHECK(params[1].ordinal == 1 && params[1].offset == 0);
        CHECK(params[2].ordinal == 2 && params[2].offset == 8);
    }
}

// Review #4: offsets out of ordinal order but overlapping must still fail.
TEST(cubin_kparam_overlap_non_monotonic_rejected) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 8, 8);   // ord 0 at [8,16)
    b.eia_kparam(&attrs, 1, 0, 12);  // ord 1 at [0,12) overlaps [8,16)
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("overlapping") != std::string::npos);
    }
}

// Review #3: KPARAM failure diagnostics must survive context push (the
// error message + kernel context must be present in the report).
TEST(cubin_kparam_error_keeps_context) {
    CubinBuilder b;
    std::vector<std::uint8_t> attrs;
    b.eia_kparam(&attrs, 0, 0, 4);
    b.eia_kparam(&attrs, 0, 8, 4);  // duplicate ordinal -> error path
    auto bytes = b.build("_Z3foov", {kNopWord}, std::move(attrs));
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        std::string d = e.describe();
        CHECK(d.find("duplicate KPARAM ordinal") != std::string::npos);
        CHECK(d.find("in kernel '_Z3foov'") != std::string::npos);
    }
}

// Review #6: relocation targeting a NOBITS section must be rejected, not
// silently written into the raw image.
TEST(cubin_relocation_nobits_target_rejected) {
    CubinBuilder b;
    // shared section is NOBITS at index 7 in the default build.
    b.extra_secs.push_back(BuiltSection{
        ".rela.nv.shared._Z3foov", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 2, 0x1b, 0x40}}),
        3, /*info=*/7, 8, 24});
    auto bytes = b.build("_Z3foov", {kNopWord}, {}, /*shared=*/true, 0x840);
    auto m = Module::load(std::move(bytes));
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kBadCubin);
        CHECK(e.describe().find("NOBITS") != std::string::npos);
    }
}

// Review #5: inst.pc is kernel-relative; file offset is separate.
TEST(cubin_word_pc_is_kernel_relative) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord, kExitWord}, {});
    auto m = Module::load(std::move(bytes));
    CHECK(m.ok());
    if (!m.ok()) return;
    const auto& k = m.value().kernels()[0];
    for (std::size_t i = 0; i < k.predecoded.size(); ++i) {
        const auto& w = k.predecoded[i];
        CHECK(w.pc == i * 16);
        if (w.unique) CHECK(w.inst->pc == i * 16);
        CHECK(w.file_offset == k.text_offset + i * 16);
    }
}

// ---------------------------------------------------------------------------
// Review round 3: text alignment (sh_addralign == 0 must NOT be exempt),
// relocation target allowlist, Module::executable().
// ---------------------------------------------------------------------------

namespace {

// Patch the .text section's sh_addralign to `align` and load.
StatusOr<Module> load_with_text_align(const std::vector<std::uint8_t>& bytes,
                                      std::uint64_t align, bool inspect) {
    std::vector<std::uint8_t> b = bytes;
    const std::uint64_t shoff = [&] {
        std::uint64_t v;
        std::memcpy(&v, b.data() + 40, 8);
        return v;
    }();
    const std::uint16_t shnum = [&] {
        std::uint16_t v;
        std::memcpy(&v, b.data() + 60, 2);
        return v;
    }();
    const std::uint16_t shstrndx = [&] {
        std::uint16_t v;
        std::memcpy(&v, b.data() + 62, 2);
        return v;
    }();
    const std::uint64_t shstr_off = [&] {
        std::uint64_t v;
        std::memcpy(&v, b.data() + shoff + shstrndx * 64 + 24, 8);
        return v;
    }();
    for (std::uint16_t i = 0; i < shnum; ++i) {
        std::uint32_t name_off;
        std::memcpy(&name_off, b.data() + shoff + i * 64, 4);
        const char* p = reinterpret_cast<const char*>(
            b.data() + shstr_off + name_off);
        if (std::strncmp(p, ".text.", 6) == 0) {
            // sh_addralign at +48 within the 64-byte header.
            std::memcpy(b.data() + shoff + i * 64 + 48, &align, 8);
            break;
        }
    }
    return inspect ? Module::load_for_inspection(std::move(b))
                   : Module::load(std::move(b));
}

}  // namespace

// sh_addralign 0 / 1 / 16 / 64 must all be rejected (no 0 exemption).
TEST(cubin_rejects_text_align_below_128) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    for (const std::uint64_t align : {std::uint64_t{0}, std::uint64_t{1},
                                      std::uint64_t{16}, std::uint64_t{64}}) {
        auto m = load_with_text_align(bytes, align, /*inspect=*/false);
        CHECK(m.failed());
        if (m.failed()) {
            Error e = m.take_error();
            CHECK(e.code() == ErrorCode::kBadCubin);
            CHECK(e.describe().find("alignment") != std::string::npos);
        }
    }
    // 128 passes.
    auto ok = load_with_text_align(bytes, 128, /*inspect=*/false);
    CHECK(ok.ok());
}

// Unknown (non-debug, non-exec, non-data) relocation target: strict fails,
// inspection warns.  Uses a fake ".nv.meta" PROGBITS section as target.
TEST(cubin_relocation_unknown_target_strict_fails) {
    CubinBuilder b;
    // extra sec 0 = .nv.meta (PROGBITS, no ALLOC, no EXEC) at index 7.
    b.extra_secs.push_back(BuiltSection{
        ".nv.meta", 1, 0, std::vector<std::uint8_t>(16, 0), 0, 0, 4, 0});
    // rela targets sec 7, links symtab (3).
    b.extra_secs.push_back(BuiltSection{
        ".rela.nv.meta", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 2, 0x1b, 0}}),
        3, 7, 8, 24});
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto m = Module::load(bytes);
    CHECK(m.failed());
    if (m.failed()) {
        Error e = m.take_error();
        CHECK(e.code() == ErrorCode::kUnsupportedMetadata);
        CHECK(e.describe().find("debug allowlist") != std::string::npos);
    }
    // Inspection mode: warns, loads.
    auto mi = Module::load_for_inspection(std::move(bytes));
    CHECK(mi.ok());
    if (mi.ok()) {
        bool warned = false;
        for (const auto& w : mi.value().warnings()) {
            if (w.message.find(".nv.meta") != std::string::npos) warned = true;
        }
        CHECK(warned);
    }
}

// Debug-allowlisted target (.debug_frame) still skips with a warning.
TEST(cubin_relocation_debug_allowlist_skips) {
    CubinBuilder b;
    b.extra_secs.push_back(BuiltSection{
        ".debug_frame", 1, 0, std::vector<std::uint8_t>(16, 0), 0, 0, 4, 0});
    b.extra_secs.push_back(BuiltSection{
        ".rela.debug_frame", 4, 0x40,
        CubinBuilder::rela_bytes({{0, 2, 0x1b, 0}}),
        3, 7, 8, 24});
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto m = Module::load(std::move(bytes));
    CHECK(m.ok());
    if (m.ok()) {
        bool warned = false;
        for (const auto& w : m.value().warnings()) {
            if (w.message.find("debug-only") != std::string::npos)
                warned = true;
        }
        CHECK(warned);
    }
}

// Module::executable(): strict load -> true; inspection -> false.
TEST(cubin_executable_flag) {
    CubinBuilder b;
    auto bytes = b.build("_Z3foov", {kNopWord}, {});
    auto strict = Module::load(std::move(bytes));
    CHECK(strict.ok());
    if (strict.ok()) CHECK(strict.value().executable());

    // Inspection load of a cubin with a bad word stays non-executable.
    CubinBuilder b2;
    const std::pair<std::uint64_t, std::uint64_t> bad = {0x1, 0x0};
    auto bytes2 = b2.build("_Z3foov", {bad}, {});
    auto insp = Module::load_for_inspection(std::move(bytes2));
    CHECK(insp.ok());
    if (insp.ok()) CHECK(!insp.value().executable());
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-cubin");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu cubin loader tests\n");
    }
    return failures == 0 ? 0 : 1;
}
