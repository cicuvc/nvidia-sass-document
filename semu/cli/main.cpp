#include <semu/api.hpp>
#include <semu/capability.hpp>
#include <semu/cubin.hpp>
#include <semu/debugger.hpp>
#include <semu/decoder.hpp>
#include <semu/decoded_access.hpp>
#include <semu/interpreter.hpp>
#include <semu/profiler.hpp>
#include <semu/status.hpp>
#include <semu/version.hpp>

#include <cstdio>
#include <cstring>
#include <fstream>
#include <istream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

int print_usage(FILE* out) {
    std::fprintf(out,
                 "usage: semu <command> [options]\n"
                 "\n"
                 "commands:\n"
                 "  --version            print version and build info\n"
                 "  capability [--full]  print the sm120 capability manifest\n"
                 "  disasm <lo> <hi>     decode a 128-bit instruction word\n"
                 "  scan-conds           scan all legality conditions for\n"
                 "                       parser gaps (GAP-04 gate)\n"
                 "  cond-eval <cls> <lo> <hi>\n"
                 "                       per-condition verdicts for a variant\n"
                 "                       class against a word (GAP-09)\n"
                 "  decode-json <lo> <hi>  structured decode (GAP-10)\n"
                  "  eval-cond             stdin predicate+slot map ->\n"
                  "                       1|0|2 tri-state (GAP-09)\n"
                  "  load <cubin>         load a cubin module (Phase 2)\n"
                  "  inspect <cubin>      dump ELF sections/symbols/kernels\n"
                  "  list-kernels <cubin> one line per kernel (machine-\n"
                  "                       readable)\n"
                  "  disasm <cubin> [kernel]\n"
                  "                       pre-decoded kernel text\n"
"  run <cubin> <kernel> <grid.x> <block.x> [grid.y"
                  " block.y grid.z block.z]\n"
                  "       [--precise|--fast] [--fast-fallback=...]"
                  " [--instruction-limit=N]\n"
                  "       execute a kernel and dump final\n"
                  "       per-lane GPRs as JSON (Phase 5\n"
                  "       differential harness)\n"
                  "  debug <cubin> <kernel> <grid.x> <block.x> [grid.y"
                  " block.y grid.z block.z]\n"
                  "       [--precise|--fast] [--instruction-limit=N]\n"
                  "       [--global=<hex>] [--param-hex=<hex>]"
                  " [--shared-size=N]\n"
                  "       single-step debug REPL (Phase 7; breakpoints,\n"
                  "       watchpoints, GPR/UR/pred/PC/memory view+modify)\n"
                  "  --help               show this help\n"
                 "\n"
                 "exit codes: 0 ok, 1 runtime error, 2 usage error\n");
    return 0;
}

int run_version() {
    std::printf("semu %s\n", semu::semu_version_string().c_str());
    std::printf("  sim: sm120 SASS behavior simulator (SIM_PLAN)\n");
    std::printf("  arch: %s\n", semu::kTargetArch);
    std::printf("  build: %s\n", semu::build_mode().c_str());
    std::printf("  cxx: %s\n", semu::build_cxx_compiler().c_str());
    std::printf("  sanitizers: %s\n",
                semu::sanitizers_enabled() ? "on" : "off");
    std::printf("  gpu differential: %s\n",
                semu::gpu_differential_enabled() ? "on" : "off");
    std::printf("  error model: %s\n", semu::kErrorModelVersion);
    std::printf("  capability manifest: %d\n", semu::kCapabilityManifestVersion);
    std::printf("  frozen API (Phase 10): backend=%d decoded_ir=%d "
                "runtime_services=%d event_stream=%d fault=%d\n",
                semu::kBackendApiVersion, semu::kDecodedIrVersion,
                semu::kRuntimeServicesVersion, semu::kEventStreamVersion,
                semu::kFaultAbiVersion);
    return 0;
}

int run_capability(bool full) {
    const auto& m = semu::CapabilityManifest::current();
    std::fputs(m.to_text(full).c_str(), stdout);
    return 0;
}

int run_disasm(int argc, char** argv) {
    const auto& dec = semu::Decoder::instance();
    if (argc >= 4) {
        const std::uint64_t lo = std::strtoull(argv[2], nullptr, 0);
        const std::uint64_t hi = std::strtoull(argv[3], nullptr, 0);
        semu::DecodeResult r = dec.decode(lo, hi);
        if (r.is_unique()) {
            const auto& inst = r.instruction();
            std::printf("OK   %s | %s | %s\n", semu::isa::variant_class_name(inst.variant_class),
                        semu::isa::mnemonic_name(inst.mnemonic),
                        dec.disassemble(inst.word, /*full=*/true).c_str());
            return 0;
        }
        if (r.outcome() == semu::DecodeOutcome::kAmbiguous) {
            std::printf("AMBIGUOUS (%zu candidates):\n", r.candidates().size());
        } else {
            std::printf("ILLEGAL (%zu candidates rejected):\n",
                        r.candidates().size());
        }
        for (const auto& c : r.candidates()) {
            std::printf("  %s  %s\n", c.variant_class.c_str(),
                        c.reason.c_str());
        }
        return 1;
    }
    // Batch mode: read "lo hi" pairs from stdin, one per line.
    char line[160];
    std::uint64_t ok = 0, ambig = 0, illegal = 0;
    while (std::fgets(line, sizeof(line), stdin)) {
        char* lp = line;
        std::uint64_t lo = std::strtoull(lp, &lp, 0);
        std::uint64_t hi = std::strtoull(lp, &lp, 0);
        if (lo == 0 && hi == 0) {
            // tolerate all-zero words (valid encodings of opcode 0)
        }
        semu::DecodeResult r = dec.decode(lo, hi);
        if (r.is_unique()) {
            ++ok;
            const auto& inst = r.instruction();
            std::printf("OK\t%s\t%s\n", semu::isa::variant_class_name(inst.variant_class),
                        dec.disassemble(inst.word, /*full=*/true).c_str());
        } else if (r.outcome() == semu::DecodeOutcome::kAmbiguous) {
            ++ambig;
            std::printf("AMBIG\t%zu\n", r.candidates().size());
        } else {
            ++illegal;
            std::printf("ILLEGAL\n");
        }
    }
    std::fprintf(stderr, "# decode: %llu ok, %llu ambiguous, %llu illegal\n",
                 static_cast<unsigned long long>(ok),
                 static_cast<unsigned long long>(ambig),
                 static_cast<unsigned long long>(illegal));
    return 0;
}

// GAP-10: machine-readable decode for structured comparison against
// cuobjdump.  `semu decode-json <lo> <hi>` prints one JSON object per line
// (or a single object for the one-word form).  2b-3: the generic
// operands/modifiers vectors were removed; the operands array is now built
// from the typed named operand fields via the per-variant ShapeManifest, and the normalized
// text comes from Decoder::disassemble (the cuobjdump-format contract).
int run_decode_json(int argc, char** argv) {
    const auto& dec = semu::Decoder::instance();
    auto print_inst = [&dec](const semu::DecodedInstruction& inst) {
        std::printf("{\"mnemonic\":\"%s\",\"variant_class\":\"%s\","
                    "\"guard\":%d,\"guard_not\":%d,\"modifiers\":[",
                    semu::isa::mnemonic_name(inst.mnemonic),
                    semu::isa::variant_class_name(inst.variant_class),
                    inst.guard_pred, inst.guard_not ? 1 : 0);
        // Typed modifiers: report the variant's format modifiers with values
        // resolved through the generated per-variant reader.
        bool first = true;
        for (std::uint16_t si = 0;
             si < semu::isa::kVariants[inst.shape_variant].nslots; ++si) {
            const auto& s = semu::isa::kVariants[inst.shape_variant].slots[si];
            if (!s.modifier) continue;
            auto v = semu::shape::slot_value(inst, s.name);
            if (!v) continue;
            if (!first) std::printf(",");
            first = false;
            std::printf("{\"slot\":\"%s\",\"type\":\"%s\","
                        "\"value\":%llu}",
                        s.name, s.type, static_cast<unsigned long long>(*v));
        }
        std::printf("],\"operands\":[");
        // Typed operands: per-variant ShapeManifest roles -> named fields.
        if (inst.shape_variant < semu::isa::kNumVariants) {
            const auto& mf = semu::shape::kShapeManifests[inst.shape_variant];
            for (std::uint16_t p = 0; p < mf.n_ops; ++p) {
                if (p) std::printf(",");
                const auto& role = mf.ops[p];
                const auto* op = semu::shape::operand_field(
                    inst.shape_variant, &inst, p);
                std::printf("{\"slot\":\"%s\",\"kind\":%d,"
                            "\"value\":%lld,\"flags\":%u}",
                            role.slot, static_cast<int>(role.kind),
                            static_cast<long long>(op
                                ? semu::shape::operand_value_as_i64(*op) : 0),
                            op ? static_cast<unsigned>(op->flags) : 0u);
            }
        }
        std::printf("],\"disasm\":\"%s\"}\n",
                    dec.disassemble(inst.word).c_str());
    };
    if (argc >= 4) {
        const std::uint64_t lo = std::strtoull(argv[2], nullptr, 0);
        const std::uint64_t hi = std::strtoull(argv[3], nullptr, 0);
        semu::DecodeResult r = dec.decode(lo, hi);
        if (r.is_unique()) {
            print_inst(r.instruction());
            return 0;
        }
        std::printf("{}\n");
        return 1;
    }
    // batch mode: "lo hi" per line
    char line[160];
    while (std::fgets(line, sizeof(line), stdin)) {
        char* lp = line;
        const std::uint64_t lo = std::strtoull(lp, &lp, 0);
        const std::uint64_t hi = std::strtoull(lp, &lp, 0);
        semu::DecodeResult r = dec.decode(lo, hi);
        if (r.is_unique()) {
            print_inst(r.instruction());
        } else {
            std::printf("{}\n");
        }
    }
    return 0;
}

int run_scan_conds() {
    std::size_t total = 0, resolved = 0;
    const std::size_t gaps =
        semu::scan_condition_parse_gaps(true, &total, &resolved);
    std::printf("# conditions: %zu total, %zu resolvable, %zu parser gaps\n",
                total, resolved, gaps);
    return gaps == 0 ? 0 : 1;
}

// GAP-09: per-condition verdict for a variant against a word's decoded slot
// map: `semu cond-eval <variant_class> <lo> <hi>` prints one line per
// condition: "<error>\t<1|0|2>\t<predicate>" (1 true, 0 false, 2 unresolved).
int run_cond_eval(int argc, char** argv) {
    if (argc < 5) {
        std::fputs("semu: 'cond-eval' requires <variant_class> <lo> <hi>\n",
                   stderr);
        return 2;
    }
    const std::string cls = argv[2];
    const std::uint64_t lo = std::strtoull(argv[3], nullptr, 0);
    const std::uint64_t hi = std::strtoull(argv[4], nullptr, 0);
    auto verdicts = semu::condition_verdicts(
        cls, semu::Word128{lo, hi});
    if (verdicts.empty()) {
        std::fprintf(stderr, "semu: no variant class '%s'\n", cls.c_str());
        return 1;
    }
    for (const auto& cv : verdicts) {
        std::printf("%s\t%d\t%s\n", cv.error.c_str(), cv.verdict,
                    cv.predicate.c_str());
    }
    return 0;
}

// GAP-09: direct three-state evaluation of a predicate against an explicit
// slot map: `semu eval-cond` reads lines "<predicate>\t<slot=value,...>" from
// stdin and prints "1|0|2" per line (1 true, 0 false, 2 unresolved).  This is
// the counterpart of Python's ConditionEvaluator.evaluate_tristate used by
// cond_differential_test to verify unknown-token samples on the C++ side too.
int run_eval_cond() {
    char line[4096];
    while (std::fgets(line, sizeof(line), stdin)) {
        char* tab = std::strchr(line, '\t');
        if (!tab) {
            std::printf("2\n");
            continue;
        }
        *tab = '\0';
        std::string pred(line);
        std::vector<std::pair<std::string, std::int64_t>> slots;
        char* sp = tab + 1;
        while (sp && *sp) {
            char* comma = std::strchr(sp, ',');
            if (comma) *comma = '\0';
            char* eq = std::strchr(sp, '=');
            if (eq) {
                *eq = '\0';
                slots.emplace_back(std::string(sp),
                                   std::strtoll(eq + 1, nullptr, 0));
            }
            sp = comma ? comma + 1 : nullptr;
        }
        std::printf("%d\n", semu::eval_predicate(pred, slots));
    }
    return 0;
}

// Read a whole cubin file into a byte vector.  Returns nullptr-style
// nullopt on open/read failure with the error printed to stderr.
std::optional<std::vector<std::uint8_t>> read_cubin_file(const char* path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        semu::Error err = semu::Error::not_found(
            std::string("cannot open module '") + path + "'");
        std::fprintf(stderr, "semu: %s\n", err.describe().c_str());
        return std::nullopt;
    }
    f.seekg(0, std::ios::end);
    const std::streamoff size = f.tellg();
    if (size == 0) {
        semu::Error err(
            semu::ErrorCode::kBadCubin, "empty module",
            semu::Error(semu::ErrorCode::kInvalidArgument,
                        "file has zero bytes"));
        std::fprintf(stderr, "semu: %s\n", err.describe().c_str());
        return std::nullopt;
    }
    f.seekg(0, std::ios::beg);
    std::vector<std::uint8_t> buf(static_cast<std::size_t>(size));
    f.read(reinterpret_cast<char*>(buf.data()),
           static_cast<std::streamsize>(size));
    if (!f) {
        semu::Error err(semu::ErrorCode::kIoError,
                        std::string("short read on module '") + path + "'");
        std::fprintf(stderr, "semu: %s\n", err.describe().c_str());
        return std::nullopt;
    }
    return buf;
}

// `semu load <cubin>`: load + validate, then report the kernel inventory.
int run_load(int argc, char** argv) {
    if (argc < 3) {
        std::fputs("semu: 'load' requires a cubin path\n", stderr);
        return 2;
    }
    auto buf = read_cubin_file(argv[2]);
    if (!buf) return 1;
    auto mod = semu::Module::load(std::move(*buf));
    if (mod.failed()) {
        std::fprintf(stderr, "semu: %s\n", mod.take_error().describe().c_str());
        return 1;
    }
    const auto& m = mod.value();
    std::printf("loaded %zu kernel(s) from %s (e_flags=0x%08x)\n",
                m.kernels().size(), argv[2], m.e_flags());
    for (const auto& k : m.kernels()) {
        std::printf("  %s: text=%lluB regs=%u shared=%u params=%zu\n",
                    k.symbol_name.c_str(),
                    static_cast<unsigned long long>(k.text_size),
                    k.meta.regcount, k.meta.static_shared,
                    k.meta.params.size());
    }
    for (const auto& w : m.warnings()) {
        std::fprintf(stderr, "semu: warning: %s\n", w.message.c_str());
    }
    return 0;
}

// `semu inspect <cubin>`: full ELF dump (header, sections, symbols, kernels).
int run_inspect(int argc, char** argv) {
    if (argc < 3) {
        std::fputs("semu: 'inspect' requires a cubin path\n", stderr);
        return 2;
    }
    auto buf = read_cubin_file(argv[2]);
    if (!buf) return 1;
    auto mod = semu::Module::load_for_inspection(std::move(*buf));
    if (mod.failed()) {
        std::fprintf(stderr, "semu: %s\n", mod.take_error().describe().c_str());
        return 1;
    }
    const auto& m = mod.value();
    std::printf("== ELF header\n");
    std::printf("  e_flags=0x%08x osabi=0x%02x abi_version=%u\n",
                m.e_flags(), m.osabi(), m.abi_version());
    std::printf("== sections (%zu)\n", m.sections().size());
    for (const auto& s : m.sections()) {
        std::printf("  %-40s type=0x%08x flags=0x%llx off=0x%llx size=%llu "
                    "link=%u info=%u\n",
                    s.name.c_str(), s.type,
                    static_cast<unsigned long long>(s.flags),
                    static_cast<unsigned long long>(s.offset),
                    static_cast<unsigned long long>(s.size), s.link, s.info);
    }
    std::printf("== symbols (%zu)\n", m.symbols().size());
    for (std::size_t i = 0; i < m.symbols().size(); ++i) {
        const auto& s = m.symbols()[i];
        std::printf("  [%2zu] %-44s bind=%u type=%u other=0x%02x shndx=%u "
                    "value=0x%llx size=%llu\n",
                    i, s.name.c_str(), s.bind, s.type, s.other, s.shndx,
                    static_cast<unsigned long long>(s.value),
                    static_cast<unsigned long long>(s.size));
    }
    std::printf("== kernels (%zu)\n", m.kernels().size());
    for (const auto& k : m.kernels()) {
        std::printf("  %s: text_sec=%u text=%lluB regs=%u shared=%u "
                    "barriers=%u mbarriers=%u maxreg=%u params=%zu\n",
                    k.symbol_name.c_str(), k.text_section,
                    static_cast<unsigned long long>(k.text_size),
                    k.meta.regcount, k.meta.static_shared,
                    k.meta.num_barriers, k.meta.num_mbarriers, k.meta.maxreg,
                    k.meta.params.size());
        for (const auto& p : k.meta.params) {
            std::printf("    param[%u] off=0x%x size=%u\n", p.ordinal,
                        p.offset, p.size);
        }
        if (!k.meta.exit_offsets.empty()) {
            std::printf("    exit:");
            for (const auto e : k.meta.exit_offsets)
                std::printf(" 0x%x", e);
            std::printf("\n");
        }
        if (k.meta.cluster_dims) {
            std::printf("    cluster_dims=%u,%u,%u%s\n",
                        (*k.meta.cluster_dims)[0], (*k.meta.cluster_dims)[1],
                        (*k.meta.cluster_dims)[2],
                        k.meta.explicit_cluster ? " (explicit)" : "");
        }
        if (k.meta.has_stack_metadata) {
            std::printf("    frame=%u min_stack=%u max_stack=%u\n",
                        k.meta.frame_size, k.meta.min_stack_size,
                        k.meta.max_stack_size);
        }
        auto ref_str = [](const std::optional<semu::KernelSectionRef>& ref) {
            if (!ref) return std::string("-");
            return std::string(ref->nobits ? "NOBITS" : "PROGBITS") +
                   " sec=" + std::to_string(ref->section_index) + " size=" +
                   std::to_string(ref->size) + " align=" +
                   std::to_string(ref->align);
        };
        std::printf("    constant0: %s\n", ref_str(k.constant0).c_str());
        std::printf("    shared:    %s\n", ref_str(k.shared).c_str());
        std::printf("    local:     %s\n", ref_str(k.local).c_str());
        std::printf("    predecoded=%zu instructions\n", k.predecoded.size());
    }
    if (!m.warnings().empty()) {
        std::printf("== warnings (%zu)\n", m.warnings().size());
        for (const auto& w : m.warnings())
            std::printf("  %s\n", w.message.c_str());
    }
    return 0;
}

// `semu list-kernels <cubin>`: one tab-separated line per kernel:
// mangled_name  text_bytes  regcount  static_shared  params
int run_list_kernels(int argc, char** argv) {
    if (argc < 3) {
        std::fputs("semu: 'list-kernels' requires a cubin path\n", stderr);
        return 2;
    }
    auto buf = read_cubin_file(argv[2]);
    if (!buf) return 1;
    auto mod = semu::Module::load_for_inspection(std::move(*buf));
    if (mod.failed()) {
        std::fprintf(stderr, "semu: %s\n", mod.take_error().describe().c_str());
        return 1;
    }
    const auto& m = mod.value();
    for (const auto& k : m.kernels()) {
        std::printf("%s\t%llu\t%u\t%u\t%zu\n", k.symbol_name.c_str(),
                    static_cast<unsigned long long>(k.text_size),
                    k.meta.regcount, k.meta.static_shared,
                    k.meta.params.size());
    }
    for (const auto& w : m.warnings()) {
        std::fprintf(stderr, "semu: warning: %s\n", w.message.c_str());
    }
    return 0;
}

// `semu disasm <cubin> [kernel]`: cuobjdump-style pre-decoded text.
int run_disasm_module(int argc, char** argv) {
    if (argc < 3) {
        std::fputs("semu: 'disasm' requires a cubin path\n", stderr);
        return 2;
    }
    auto buf = read_cubin_file(argv[2]);
    if (!buf) return 1;
    auto mod = semu::Module::load_for_inspection(std::move(*buf));
    if (mod.failed()) {
        std::fprintf(stderr, "semu: %s\n", mod.take_error().describe().c_str());
        return 1;
    }
    const auto& m = mod.value();
    const std::string only = argc >= 4 ? argv[3] : std::string();
    bool found = false;
    for (const auto& k : m.kernels()) {
        if (!only.empty() && k.symbol_name != only) continue;
        found = true;
        std::printf("\t\tFunction : %s\n", k.symbol_name.c_str());
        for (const auto& w : k.predecoded) {
            if (w.unique) {
                std::printf("        /*%04llx*/  %s\n",
                            static_cast<unsigned long long>(w.pc),
                            semu::Decoder::instance()
                                .disassemble(semu::Word128{w.lo, w.hi}, /*full=*/true)
                                .c_str());
            } else {
                std::printf("        /*%04llx*/  <unresolved: %s>\n",
                            static_cast<unsigned long long>(w.pc),
                            w.reason.c_str());
            }
        }
    }
    if (!found) {
        std::fprintf(stderr, "semu: kernel '%s' not found\n", only.c_str());
        return 1;
    }
    for (const auto& w : m.warnings()) {
        std::fprintf(stderr, "semu: warning: %s\n", w.message.c_str());
    }
    return 0;
}

}  // namespace

// Shared option parsing for `run` / `debug`.
//   [--precise|--fast] [--fast-fallback=none|exceptional|modifiers]
//   [--instruction-limit=N] [--workers=N] [--l1tex] [--race] [--l2]
//   [--shared-size=N] [--param-hex=<hex>] [--global=<hex>]
// Sets `pos` to the first positional argument (the cubin path).  Returns 0
// and prints the error when the command line is invalid.
namespace {
struct RunCliOptions {
    semu::RunOptions opts;
    std::vector<std::uint8_t> global_buffer;
    std::vector<std::uint8_t> param_buffer;
    int pos = 2;   // first positional (cubin path)
    bool valid = false;
    bool profile = false;  // Phase 8: emit the profiler report JSON
    int error = 0;  // exit code when !valid
};

RunCliOptions parse_run_options(int argc, char** argv) {
    RunCliOptions o;
    bool mode_given = false;
    bool fallback_given = false;
    for (int i = 2; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--precise" || a == "--fast") {
            if (mode_given) {
                std::fprintf(stderr,
                             "semu: only one of --precise/--fast allowed\n");
                o.error = 2;
                return o;
            }
            mode_given = true;
            o.opts.mode = (a == "--fast") ? semu::ExecutionMode::kFast
                                          : semu::ExecutionMode::kPrecise;
            if (o.opts.mode == semu::ExecutionMode::kFast) {
                // --fast defaults to fallback none (performance-first).
                o.opts.fast_fp_fallback = semu::FastFpFallback::kNone;
            }
            ++o.pos;
            continue;
        }
        if (a.rfind("--fast-fallback=", 0) == 0) {
            fallback_given = true;
            const std::string v = a.substr(16);
            if (v == "none") o.opts.fast_fp_fallback = semu::FastFpFallback::kNone;
            else if (v == "exceptional")
                o.opts.fast_fp_fallback = semu::FastFpFallback::kExceptional;
            else if (v == "modifiers")
                o.opts.fast_fp_fallback = semu::FastFpFallback::kStrictModifiers;
            else {
                std::fprintf(stderr,
                             "semu: bad --fast-fallback '%s' (none|exceptional|modifiers)\n",
                             v.c_str());
                o.error = 2;
                return o;
            }
            ++o.pos;
            continue;
        }
        if (a.rfind("--instruction-limit=", 0) == 0) {
            char* end = nullptr;
            const unsigned long v = std::strtoul(a.c_str() + 20, &end, 10);
            if (!end || *end != '\0') {
                std::fprintf(stderr, "semu: bad --instruction-limit\n");
                o.error = 2;
                return o;
            }
            o.opts.instruction_limit = v;
            ++o.pos;
            continue;
        }
        if (a == "--l1tex") {
            o.opts.model.l1tex = semu::L1TexMode::kTraceOnly;
            ++o.pos;
            continue;
        }
        if (a == "--race") {
            o.opts.model.race = semu::RaceMode::kReport;
            ++o.pos;
            continue;
        }
        if (a == "--l2") {
            o.opts.model.l2 = semu::L2Mode::kFunctionalEvents;
            ++o.pos;
            continue;
        }
        if (a == "--profile") {
            o.profile = true;
            ++o.pos;
            continue;
        }
        if (a.rfind("--workers=", 0) == 0) {
            char* end = nullptr;
            const long v = std::strtol(a.c_str() + 10, &end, 10);
            if (!end || *end != '\0' || v < 1 || v > 256) {
                std::fprintf(stderr, "semu: bad --workers (1..256)\n");
                o.error = 2;
                return o;
            }
            o.opts.worker_count = static_cast<int>(v);
            ++o.pos;
            continue;
        }
        if (a.rfind("--shared-size=", 0) == 0) {
            char* end = nullptr;
            const unsigned long v = std::strtoul(a.c_str() + 14, &end, 10);
            if (!end || *end != '\0') {
                std::fprintf(stderr, "semu: bad --shared-size\n");
                o.error = 2;
                return o;
            }
            o.opts.memory.shared_size = v;
            ++o.pos;
            continue;
        }
        if (a.rfind("--local-size=", 0) == 0) {
            char* end = nullptr;
            const unsigned long v = std::strtoul(a.c_str() + 13, &end, 10);
            if (!end || *end != '\0') {
                std::fprintf(stderr, "semu: bad --local-size\n");
                o.error = 2;
                return o;
            }
            o.opts.memory.local_size = v;
            ++o.pos;
            continue;
        }
        if (a.rfind("--param-hex=", 0) == 0) {
            const std::string hex = a.substr(12);
            if (hex.size() % 2 != 0) {
                std::fprintf(stderr, "semu: --param-hex must have even length\n");
                o.error = 2;
                return o;
            }
            auto nib = [](char c) -> int {
                if (c >= '0' && c <= '9') return c - '0';
                if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                return -1;
            };
            for (std::size_t i = 0; i < hex.size(); i += 2) {
                const int hi = nib(hex[i]);
                const int lo = nib(hex[i + 1]);
                if (hi < 0 || lo < 0) {
                    std::fprintf(stderr, "semu: bad hex in --param-hex\n");
                    o.error = 2;
                    return o;
                }
                o.param_buffer.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
            }
            o.opts.memory.params = &o.param_buffer;
            ++o.pos;
            continue;
        }
        if (a.rfind("--global=", 0) == 0) {
            const std::string hex = a.substr(9);
            if (hex.size() % 2 != 0) {
                std::fprintf(stderr, "semu: --global hex must have even length\n");
                o.error = 2;
                return o;
            }
            for (std::size_t i = 0; i < hex.size(); i += 2) {
                int hi = 0, lo = 0;
                const char c1 = hex[i], c2 = hex[i + 1];
                auto nib = [](char c) -> int {
                    if (c >= '0' && c <= '9') return c - '0';
                    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                    return -1;
                };
                hi = nib(c1);
                lo = nib(c2);
                if (hi < 0 || lo < 0) {
                    std::fprintf(stderr, "semu: bad hex in --global\n");
                    o.error = 2;
                    return o;
                }
                o.global_buffer.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
            }
            o.opts.memory.global = &o.global_buffer;
            ++o.pos;
            continue;
        }
        if (a.rfind("--", 0) == 0) {
            std::fprintf(stderr, "semu: unknown option '%s'\n", a.c_str());
            o.error = 2;
            return o;
        }
        break;  // first positional
    }
    if (o.opts.mode == semu::ExecutionMode::kPrecise && fallback_given) {
        std::fputs("semu: --fast-fallback is fast-only; remove it for "
                   "precise mode\n",
                   stderr);
        o.error = 2;
        return o;
    }
    o.valid = true;
    return o;
}
}  // namespace

// `semu run <cubin> <kernel> <grid.x> <block.x> [grid.y block.y grid.z
// block.z]`: execute the named kernel in the interpreter and dump the final
// per-lane GPR state as JSON (one object per CTA/warp/lane with
// {"pc","exited","active","gpr":[...]}).  Exit 0 on clean completion.
int run_interp(int argc, char** argv) {
    RunCliOptions o = parse_run_options(argc, argv);
    if (!o.valid) return o.error > 0 ? o.error : 2;
    if (argc - o.pos < 4) {
        std::fputs("semu: 'run' requires <cubin> <kernel> <grid.x> <block.x>\n",
                   stderr);
        return 2;
    }
    auto& opts = o.opts;
    auto buf = read_cubin_file(argv[o.pos]);
    if (!buf) return 1;
    auto mod = semu::Module::load(std::move(*buf));
    if (mod.failed()) {
        std::fprintf(stderr, "semu: %s\n", mod.take_error().describe().c_str());
        return 1;
    }
    const auto& m = mod.value();
    const std::string kname = argv[o.pos + 1];
    const semu::Kernel* k = m.find_kernel(kname);
    if (!k) {
        std::fprintf(stderr, "semu: kernel '%s' not found\n", kname.c_str());
        return 1;
    }
    auto parse_u32 = [](const char* s, std::uint32_t* out) -> bool {
        char* end = nullptr;
        const unsigned long v = std::strtoul(s, &end, 10);
        if (!end || *end != '\0') return false;
        *out = static_cast<std::uint32_t>(v);
        return true;
    };
    semu::LaunchEnv env;
    int idx = o.pos + 2;
    // grid.x block.x [grid.y block.y grid.z block.z]
    if (!parse_u32(argv[idx], &env.grid[0])) {
        std::fprintf(stderr, "semu: bad grid.x '%s'\n", argv[idx]);
        return 2;
    }
    if (!parse_u32(argv[idx + 1], &env.block[0])) {
        std::fprintf(stderr, "semu: bad block.x '%s'\n", argv[idx + 1]);
        return 2;
    }
    idx += 2;
    while (idx + 1 < argc && idx < o.pos + 2 + 4) {
        // Pairs after grid.x/block.x are (grid.y,block.y),(grid.z,block.z).
        std::uint32_t a = 0, b = 0;
        if (!parse_u32(argv[idx], &a) || !parse_u32(argv[idx + 1], &b)) break;
        env.grid[(idx - (o.pos + 2)) / 2 + 1] = a;
        env.block[(idx - (o.pos + 2)) / 2 + 1] = b;
        idx += 2;
    }
    auto r = semu::Interpreter::run_result(*k, env, opts);
    if (r.fault) {
        std::printf("{\"execution_mode\":\"%s\",\"approximate\":%s,"
                    "\"fast_stats\":{\"fast_fp_ops\":%llu,"
                    "\"precise_fallback_ops\":%llu,"
                    "\"ignored_modifier_ops\":%llu},"
                    "\"fault\":{\"kind\":%d,\"pc\":%llu,\"warp\":%llu,"
                    "\"message\":\"%s\"}}\n",
                    r.execution_mode == semu::ExecutionMode::kFast ? "fast"
                                                                   : "precise",
                    r.approximate ? "true" : "false",
                    static_cast<unsigned long long>(r.fast_stats.fast_fp_ops),
                    static_cast<unsigned long long>(
                        r.fast_stats.precise_fallback_ops),
                    static_cast<unsigned long long>(
                        r.fast_stats.ignored_modifier_ops),
                    static_cast<int>(r.fault->kind()),
                    static_cast<unsigned long long>(r.fault->pc().value_or(0)),
                    static_cast<unsigned long long>(r.fault->warp().value_or(0)),
                    r.fault->message().c_str());
        return 1;
    }
    std::printf("{\"execution_mode\":\"%s\",\"approximate\":%s,"
                "\"fast_stats\":{\"fast_fp_ops\":%llu,"
                "\"precise_fallback_ops\":%llu,"
                "\"ignored_modifier_ops\":%llu},\"ctas\":[",
                r.execution_mode == semu::ExecutionMode::kFast ? "fast"
                                                               : "precise",
                r.approximate ? "true" : "false",
                static_cast<unsigned long long>(r.fast_stats.fast_fp_ops),
                static_cast<unsigned long long>(
                    r.fast_stats.precise_fallback_ops),
                static_cast<unsigned long long>(
                    r.fast_stats.ignored_modifier_ops));
    for (std::size_t ci = 0; ci < r.ctas.size(); ++ci) {
        const auto& cta = r.ctas[ci];
        if (ci) std::printf(",");
        std::printf("{\"warps\":[");
        for (std::size_t wi = 0; wi < cta.warps.size(); ++wi) {
            const auto& ws = cta.warps[wi];
            if (wi) std::printf(",");
            std::printf("{\"lanes\":[");
            for (int lane = 0; lane < semu::kLanesPerWarp; ++lane) {
                const auto& t = ws.threads[lane];
                if (lane) std::printf(",");
                std::printf("{\"pc\":%llu,\"exited\":%d,\"active\":%d,\"gpr\":[",
                            static_cast<unsigned long long>(t.pc),
                            t.exited ? 1 : 0, t.active ? 1 : 0);
                for (int g = 0; g < semu::kNumGprs; ++g) {
                    if (g) std::printf(",");
                    std::printf("%u", t.gpr[g]);
                }
                std::printf("]}");
            }
            std::printf("]}");
        }
        std::printf("]}");
    }
    // Close the ctas array, then the root object (with the global buffer as a
    // final Phase 6 field inside the root object).
    std::printf("]");
    if (opts.memory.global) {
        std::printf(",\"global\":\"");
        for (std::uint8_t b : *opts.memory.global) {
            std::printf("%02x", b);
        }
        std::printf("\"");
    }
    // Phase 6 Step 2B: trace-only L1TEX events (only when --l1tex enabled).
    if (opts.model.l1tex == semu::L1TexMode::kTraceOnly) {
        std::printf(",\"memory_events\":[");
        for (std::size_t i = 0; i < r.memory_events.size(); ++i) {
            const auto& ev = r.memory_events[i];
            if (i) std::printf(",");
            std::printf("{\"id\":%llu,\"sm\":%u,\"subcore\":%u,\"cta\":%u,"
                        "\"warp\":%u,\"kind\":\"%s\",\"mnemonic\":\"%s\"}",
                        static_cast<unsigned long long>(ev.event_id), ev.sm,
                        ev.subcore, ev.cta, ev.warp, ev.request_kind.c_str(),
                        ev.mnemonic.c_str());
        }
        std::printf("]");
    }
    // Phase 6 Step 2D: data-race reports (only when --race).
    if (opts.model.race == semu::RaceMode::kReport) {
        std::printf(",\"races\":[");
        for (std::size_t i = 0; i < r.race_reports.size(); ++i) {
            const auto& rr = r.race_reports[i];
            if (i) std::printf(",");
            std::printf("{\"key\":\"%s\",\"count\":%llu,"
                        "\"overlap\":[%llu,%llu],\"reason\":\"%s\","
                        "\"a_pc\":%llu,\"a_insn\":\"%s\","
                        "\"b_pc\":%llu,\"b_insn\":\"%s\"}",
                        rr.key.c_str(),
                        static_cast<unsigned long long>(rr.occurrence),
                        static_cast<unsigned long long>(rr.overlap_begin),
                        static_cast<unsigned long long>(rr.overlap_end),
                        rr.reason.c_str(),
                        static_cast<unsigned long long>(rr.first.pc),
                        rr.first.mnemonic.c_str(),
                        static_cast<unsigned long long>(rr.second.pc),
                        rr.second.mnemonic.c_str());
        }
        std::printf("]");
    }
    // Phase 8: profiler report (only when --profile).  The profiler is a pure
    // subscriber of the backend-neutral event stream; it never changes the
    // functional result printed above.
    if (o.profile) {
        semu::profiler::MemoryProfiler prof(kname, opts.model.simulated_sm_count);
        prof.add_events(r.memory_events);
        auto rep = prof.report();
        std::printf(",\"profiler\":%s", rep.to_json().c_str());
    }
    std::printf("}\n");
    return 0;
}

// ---------------------------------------------------------------------------
// `semu debug` — single-step debug REPL (SIM_PLAN Phase 7).
//
//   semu debug <cubin> <kernel> <grid.x> <block.x> [grid.y block.y grid.z
//              block.z] [same run options as `run`]
//
// All REPL capabilities come from the public DebugSession API — no profiler,
// no backend bypass.  The session is pinned to a single worker so identical
// scripts replay byte-for-byte.
//
// Commands:
//   s / step [N]      step one (or N) dynamic warp instruction(s)
//   c / continue      run until breakpoint/watchpoint/fault/limit/done
//                     (steps over the just-hit breakpoint once)
//   b pc <addr> [cond]      breakpoint on a byte PC
//   b mnem <STG> [cond]     breakpoint on a mnemonic
//   wb <space> <base> <len> [r|w|a] [cond]     memory watchpoint
//   del <id> | del b <id> | del w <id>  delete (ids are shared across both)
//   info b / info w   list breakpoints / watchpoints
//   r R# [= val][@L#]         read / write GPR
//   ur UR# [= val]            read / write uniform register
//   pred P# [= 0|1] [@L#]     read / write predicate
//   pc [= addr]               read / write all lanes' PC (jump)
//   sreg L#           show special registers for a lane
//   mem <space> <addr> <len> [--cta N [--warp N]]  dump memory
//   mem w <space> <addr> <hex> [same scope]  write memory
//       (shared requires --cta; local requires --cta + --warp; local is a
//        per-warp window — no --lane dimension)
//   info state        full GPR / UR / pred / barrier / scoreboard dump
//   info last         summary of the last step
//   info sb           scoreboard / pending memory-op groups
//   trace             full reproducible step trace
//   focus <cta>.<warp> | focus off     warp step (restrict scheduling)
//   limit [N]         show / set the dynamic instruction limit
//   fault             show the terminal fault (if any)
//   q / quit
//   conditions: [--cta N] [--warp N] [--lane 0xMASK]
// ---------------------------------------------------------------------------

namespace {

struct DebugCli {
    semu::DebugSession session;
    semu::DebugStepInfo last;
    std::vector<std::string> trace;
    explicit DebugCli(semu::DebugSession s) : session(std::move(s)) {}
};

// Print a step result line for the REPL.
void print_step(const semu::DebugStepInfo& s) {
    std::printf("[%s] ", semu::to_string(s.reason));
    if (s.reason == semu::DebugStopReason::kDone) {
        std::printf("launch finished (executed=%llu)\n",
                    static_cast<unsigned long long>(s.dynamic_instructions));
        return;
    }
    std::printf("cta=%u warp=%u pc=0x%llx mask=0x%08llx dyn=%llu",
                s.cta, s.warp, static_cast<unsigned long long>(s.pc),
                static_cast<unsigned long long>(s.active_mask),
                static_cast<unsigned long long>(s.dynamic_instructions));
    if (s.instruction.mnemonic != semu::isa::Mnemonic::kUnknown) {
        std::printf("  %s",
                    semu::Decoder::instance()
                        .disassemble(s.instruction.word, /*full=*/true)
                        .c_str());
    }
    std::printf("\n");
    for (const auto& d : s.reg_diffs)
        std::printf("    !! %s\n", d.describe().c_str());
    for (const auto& a : s.accesses)
        std::printf("    > mem %s 0x%llx +%llu lane=%u%s%s\n",
                    semu::to_string(a.space),
                    static_cast<unsigned long long>(a.address),
                    static_cast<unsigned long long>(a.width),
                    a.lane, a.write ? " write" : "",
                    a.atomic ? " atomic" : "");
    for (const auto& h : s.watch_hits) {
        std::printf("    * watchpoint #%llu lanes=0x%08llx\n",
                    static_cast<unsigned long long>(h.watchpoint_id),
                    static_cast<unsigned long long>(h.lanes));
    }
    if (s.fault) {
        std::printf("    FAULT %s: %s\n",
                    semu::to_string(s.fault->kind()),
                    s.fault->message().c_str());
    }
}

bool parse_u64_arg(const char* s, std::uint64_t* out) {
    char* end = nullptr;
    const unsigned long long v = std::strtoull(s, &end, 0);
    if (!end || *end != '\0') return false;
    *out = static_cast<std::uint64_t>(v);
    return true;
}

bool parse_u32_arg(const char* s, std::uint32_t* out) {
    std::uint64_t v = 0;
    if (!parse_u64_arg(s, &v) || v > 0xFFFFFFFFull) return false;
    *out = static_cast<std::uint32_t>(v);
    return true;
}

// Breakpoint / watchpoint condition filter parsing: consumes trailing
// `--cta N --warp N --lane 0xMASK` tokens from `args` starting at *i.
void parse_conditions(const std::vector<std::string>& args, std::size_t* i,
                      std::optional<std::uint32_t>* cta,
                      std::optional<std::uint32_t>* warp,
                      std::optional<std::uint32_t>* lane) {
    while (*i < args.size()) {
        const std::string& a = args[*i];
        if (a == "--cta" && *i + 1 < args.size()) {
            std::uint32_t v = 0;
            if (parse_u32_arg(args[*i + 1].c_str(), &v)) *cta = v;
            *i += 2;
        } else if (a == "--warp" && *i + 1 < args.size()) {
            std::uint32_t v = 0;
            if (parse_u32_arg(args[*i + 1].c_str(), &v)) *warp = v;
            *i += 2;
        } else if (a == "--lane" && *i + 1 < args.size()) {
            std::uint64_t v = 0;
            if (parse_u64_arg(args[*i + 1].c_str(), &v)) *lane = static_cast<std::uint32_t>(v);
            *i += 2;
        } else {
            break;
        }
    }
}

std::vector<std::string> split_cmd(const char* line) {
    std::vector<std::string> out;
    std::istringstream is(line);
    std::string tok;
    while (is >> tok) out.push_back(tok);
    return out;
}

}  // namespace

int run_debug(int argc, char** argv) {
    RunCliOptions o = parse_run_options(argc, argv);
    if (!o.valid) return o.error > 0 ? o.error : 2;
    if (argc - o.pos < 4) {
        std::fputs("semu: 'debug' requires <cubin> <kernel> <grid.x> <block.x>\n",
                   stderr);
        return 2;
    }
    auto buf = read_cubin_file(argv[o.pos]);
    if (!buf) return 1;
    auto mod = semu::Module::load(std::move(*buf));
    if (mod.failed()) {
        std::fprintf(stderr, "semu: %s\n", mod.take_error().describe().c_str());
        return 1;
    }
    const auto& m = mod.value();
    const std::string kname = argv[o.pos + 1];
    const semu::Kernel* k = m.find_kernel(kname);
    if (!k) {
        std::fprintf(stderr, "semu: kernel '%s' not found\n", kname.c_str());
        return 1;
    }
    auto parse_u32 = [](const char* s, std::uint32_t* out) -> bool {
        char* end = nullptr;
        const unsigned long v = std::strtoul(s, &end, 10);
        if (!end || *end != '\0') return false;
        *out = static_cast<std::uint32_t>(v);
        return true;
    };
    semu::LaunchEnv env;
    int idx = o.pos + 2;
    if (!parse_u32(argv[idx], &env.grid[0])) {
        std::fprintf(stderr, "semu: bad grid.x '%s'\n", argv[idx]);
        return 2;
    }
    if (!parse_u32(argv[idx + 1], &env.block[0])) {
        std::fprintf(stderr, "semu: bad block.x '%s'\n", argv[idx + 1]);
        return 2;
    }
    idx += 2;
    while (idx + 1 < argc && idx < o.pos + 2 + 4) {
        std::uint32_t a = 0, b = 0;
        if (!parse_u32(argv[idx], &a) || !parse_u32(argv[idx + 1], &b)) break;
        env.grid[(idx - (o.pos + 2)) / 2 + 1] = a;
        env.block[(idx - (o.pos + 2)) / 2 + 1] = b;
        idx += 2;
    }

    auto begin = semu::DebugSession::begin(*k, env, o.opts,
                                           o.opts.instruction_limit);
    if (begin.failed()) {
        std::fprintf(stderr, "semu: debug: %s\n",
                     begin.take_error().describe().c_str());
        return 1;
    }
    DebugCli cli(std::move(begin.value()));

    std::printf("semu debug: kernel '%s' grid=%ux%ux%u block=%ux%ux%u "
                "limit=%llu\n",
                k->symbol_name.c_str(), env.grid[0], env.grid[1], env.grid[2],
                env.block[0], env.block[1], env.block[2],
                static_cast<unsigned long long>(cli.session.instruction_limit()));
    std::printf("  (help for command list; q to quit)\n");

    char line[4096];
    for (;;) {
        std::fputs("(dbg) ", stdout);
        std::fflush(stdout);
        if (!std::fgets(line, sizeof(line), stdin)) break;
        auto args = split_cmd(line);
        if (args.empty()) continue;
        const std::string& cmd = args[0];

        if (cmd == "q" || cmd == "quit" || cmd == "exit") break;

        if (cmd == "s" || cmd == "step") {
            std::uint64_t n = 1;
            if (args.size() > 1) {
                if (!parse_u64_arg(args[1].c_str(), &n) || n == 0) {
                    std::fputs("(dbg) step [N]: N > 0\n", stderr);
                    continue;
                }
            }
            cli.last = cli.session.step_n(n);
            cli.trace.push_back(cli.last.canonical());
            print_step(cli.last);
            continue;
        }
        if (cmd == "c" || cmd == "continue") {
            cli.last = cli.session.continue_run();
            cli.trace.push_back(cli.last.canonical());
            print_step(cli.last);
            continue;
        }
        if (cmd == "b" || cmd == "break") {
            if (args.size() < 2 ||
                (args[1] != "pc" && args[1] != "mnem" && args[1] != "mnemonic")) {
                std::fputs("usage: b pc <addr> [conds]  |  b mnem <STG> [conds]\n",
                           stderr);
                continue;
            }
            semu::Breakpoint bp;
            std::optional<std::uint32_t> cta, warp, lane;
            std::size_t i = 2;
            parse_conditions(args, &i, &cta, &warp, &lane);
            bp.cta = cta;
            bp.warp = warp;
            bp.lane_mask = lane;
            if (args[1] == "pc") {
                if (i >= args.size() || !parse_u64_arg(args[i].c_str(), &bp.pc)) {
                    std::fputs("usage: b pc <addr>\n", stderr);
                    continue;
                }
                bp.kind = semu::BreakpointKind::kPc;
                if (bp.pc % 16 != 0) {
                    std::fprintf(stderr, "(dbg) pc must be 16-byte aligned\n");
                    continue;
                }
            } else {
                if (i >= args.size()) {
                    std::fputs("usage: b mnem <STG>\n", stderr);
                    continue;
                }
                bp.kind = semu::BreakpointKind::kMnemonic;
                bp.mnemonic = args[i];
            }
            auto id = cli.session.add_breakpoint(bp);
            if (id.failed()) {
                std::fprintf(stderr, "(dbg) %s\n", id.take_error().describe().c_str());
            } else {
                std::printf("(dbg) breakpoint #%llu: %s\n",
                            static_cast<unsigned long long>(id.value()),
                            bp.describe().c_str());
            }
            continue;
        }
        if (cmd == "wb" || cmd == "watch") {
            if (args.size() < 4) {
                std::fputs(
                    "usage: wb <g|s|l|c> <base> <len> [r|w|a|rw|ra|wa|rwa] "
                    "[conds]\n",
                    stderr);
                continue;
            }
            semu::Watchpoint wp;
            if (args[1] == "g" || args[1] == "global") wp.space = semu::AddressSpace::kGlobal;
            else if (args[1] == "s" || args[1] == "shared") wp.space = semu::AddressSpace::kShared;
            else if (args[1] == "l" || args[1] == "local") wp.space = semu::AddressSpace::kLocal;
            else if (args[1] == "c" || args[1] == "const" || args[1] == "constant")
                wp.space = semu::AddressSpace::kConstant;
            else {
                std::fputs("(dbg) space must be g/s/l/c\n", stderr);
                continue;
            }
            std::uint64_t base = 0, len = 0;
            if (!parse_u64_arg(args[2].c_str(), &base) ||
                !parse_u64_arg(args[3].c_str(), &len) || len == 0) {
                std::fputs("(dbg) bad base/len\n", stderr);
                continue;
            }
            wp.base = base;
            wp.size = len;
            std::size_t i = 4;
            if (i < args.size() && args[i][0] != '-') {
                const std::string& k = args[i];
                wp.kind = 0;
                if (k.find('r') != std::string::npos) wp.kind |= semu::WK_READ;
                if (k.find('w') != std::string::npos) wp.kind |= semu::WK_WRITE;
                if (k.find('a') != std::string::npos) wp.kind |= semu::WK_ATOMIC;
                if (wp.kind == 0) wp.kind = semu::WK_READ | semu::WK_WRITE | semu::WK_ATOMIC;
                ++i;
            }
            std::optional<std::uint32_t> cta, warp, lane;
            parse_conditions(args, &i, &cta, &warp, &lane);
            wp.cta = cta;
            wp.warp = warp;
            wp.lane_mask = lane;
            auto id = cli.session.add_watchpoint(wp);
            if (id.failed()) {
                std::fprintf(stderr, "(dbg) %s\n", id.take_error().describe().c_str());
            } else {
                std::printf("(dbg) watchpoint #%llu: %s\n",
                            static_cast<unsigned long long>(id.value()),
                            wp.describe().c_str());
            }
            continue;
        }
        if (cmd == "del" || cmd == "db") {
            if (args.size() < 2) {
                std::fputs("usage: del <id> | del b <id> | del w <id>\n",
                           stderr);
                continue;
            }
            // Medium (Phase 7 re-review): breakpoint and watchpoint ids come
            // from one shared pool, so `del <id>` is unambiguous.  `del b` /
            // `del w` delete from a specific kind and reject cross-kind ids.
            std::size_t ai = 1;
            semu::Status st = semu::Status::success();
            if (args[ai] == "b" || args[ai] == "w") {
                const bool bp = args[ai] == "b";
                if (args.size() < 3) {
                    std::fputs("usage: del b <id> | del w <id>\n", stderr);
                    continue;
                }
                std::uint64_t idv = 0;
                if (!parse_u64_arg(args[ai + 1].c_str(), &idv)) {
                    std::fputs("(dbg) bad id\n", stderr);
                    continue;
                }
                st = bp ? cli.session.remove_breakpoint(idv)
                        : cli.session.remove_watchpoint(idv);
                if (st.failed()) {
                    std::fprintf(stderr, "(dbg) %s\n",
                                 st.error().message().c_str());
                } else {
                    std::printf("(dbg) deleted %s #%llu\n",
                                bp ? "breakpoint" : "watchpoint",
                                static_cast<unsigned long long>(idv));
                }
                continue;
            }
            std::uint64_t idv = 0;
            if (!parse_u64_arg(args[ai].c_str(), &idv)) {
                std::fputs("(dbg) bad id\n", stderr);
                continue;
            }
            st = cli.session.remove_breakpoint(idv);
            if (st.failed()) st = cli.session.remove_watchpoint(idv);
            if (st.failed()) {
                std::fprintf(stderr, "(dbg) %s\n", st.error().message().c_str());
            } else {
                std::printf("(dbg) deleted #%llu\n",
                            static_cast<unsigned long long>(idv));
            }
            continue;
        }
        if (cmd == "info") {
            const std::string sub = args.size() > 1 ? args[1] : "last";
            if (sub == "b" || sub == "breakpoints") {
                const auto& bps = cli.session.breakpoints();
                std::printf("(dbg) %zu breakpoint(s)\n", bps.size());
                for (const auto& b : bps) std::printf("  %s\n", b.describe().c_str());
                continue;
            }
            if (sub == "w" || sub == "watchpoints") {
                const auto& wps = cli.session.watchpoints();
                std::printf("(dbg) %zu watchpoint(s)\n", wps.size());
                for (const auto& w : wps) std::printf("  %s\n", w.describe().c_str());
                continue;
            }
            if (sub == "last") {
                print_step(cli.last);
                continue;
            }
            if (sub == "sb" || sub == "scoreboard") {
                auto pg = cli.session.pending_groups();
                std::printf("(dbg) pending_groups=%llu\n",
                            pg.ok() ? static_cast<unsigned long long>(pg.value())
                                    : 0ull);
                if (pg.ok()) {
                    for (std::uint64_t g = 0; g < pg.value(); ++g) {
                        auto ops = cli.session.pending_ops(g);
                        std::printf("  group %llu: %zu pending op(s)\n",
                                    static_cast<unsigned long long>(g),
                                    ops.ok() ? ops.value() : 0);
                    }
                }
                continue;
            }
            if (sub == "state") {
                std::fputs(cli.session.state_report().c_str(), stdout);
                continue;
            }
            std::printf("(dbg) info: b | w | last | sb | state\n");
            continue;
        }
        if (cmd == "r") {
            if (args.size() < 2) {
                std::fputs("usage: r R# [= val] [@Ln]\n", stderr);
                continue;
            }
            int reg = -1;
            if (args[1].size() >= 2 && (args[1][0] == 'R'))
                reg = static_cast<int>(std::strtoul(args[1].c_str() + 1, nullptr, 0));
            if (reg < 0 || reg > 255) {
                std::fputs("(dbg) bad register (R0..R255)\n", stderr);
                continue;
            }
            int lane = -1;
            if (args.size() > 1) {
                // optional @Ln (or @n) on the register token
                const std::string& tok = args[1];
                const std::size_t at = tok.find('@');
                if (at != std::string::npos) {
                    const char* lp = tok.c_str() + at + 1;
                    if (*lp == 'L' || *lp == 'l') ++lp;
                    lane = static_cast<int>(std::strtoul(lp, nullptr, 0));
                }
            }
            // default cta/warp from the last step
            const std::uint32_t cta_id = cli.last.cta;
            const std::uint32_t warp = cli.last.warp;
            auto idx = cli.session.cta_index(cta_id);
            if (!idx.ok()) {
                std::fprintf(stderr, "(dbg) %s\n", idx.take_error().describe().c_str());
                continue;
            }
            bool want_write = false;
            std::uint32_t value = 0;
            for (std::size_t i = 2; i < args.size(); ++i) {
                if (args[i] == "=" && i + 1 < args.size()) {
                    want_write = true;
                    std::uint64_t v = 0;
                    if (!parse_u64_arg(args[i + 1].c_str(), &v)) {
                        std::fputs("(dbg) bad value (use 0x hex)\n", stderr);
                        continue;
                    }
                    value = static_cast<std::uint32_t>(v);
                    break;
                }
            }
            if (want_write) {
                if (lane >= 0) {
                    std::printf("R%d@L%d = 0x%08x\n", reg, lane, value);
                } else {
                    for (int l = 0; l < semu::kLanesPerWarp; ++l) {
                        cli.session.write_gpr(cta_id, warp, l, reg, value);
                    }
                    std::printf("R%d = 0x%08x (all lanes of cta %u warp %u)\n",
                                reg, value, cta_id, warp);
                }
                cli.last.reg_diffs.clear();
                continue;
            }
            if (lane >= 0) {
                std::uint32_t out = 0;
                auto st = cli.session.read_gpr(cta_id, warp, lane, reg, &out);
                if (st.failed()) {
                    std::fprintf(stderr, "(dbg) %s\n", st.error().message().c_str());
                } else {
                    std::printf("R%d@L%d = 0x%08x\n", reg, lane, out);
                }
                continue;
            }
            for (int l = 0; l < semu::kLanesPerWarp; ++l) {
                std::uint32_t out = 0;
                if (cli.session.read_gpr(cta_id, warp, l, reg, &out).ok())
                    std::printf("  R%d[L%02d] = 0x%08x\n", reg, l, out);
            }
            continue;
        }
        if (cmd == "ur") {
            if (args.size() < 2) {
                std::fputs("usage: ur UR# [= val]\n", stderr);
                continue;
            }
            int ur = -1;
            if (args[1].size() >= 3 && (args[1][0] == 'U' && args[1][1] == 'R'))
                ur = static_cast<int>(std::strtoul(args[1].c_str() + 2, nullptr, 0));
            if (ur < 0 || ur > 63) {
                std::fputs("(dbg) bad uniform register (UR0..UR63)\n", stderr);
                continue;
            }
            const std::uint32_t cta_id = cli.last.cta;
            const std::uint32_t warp = cli.last.warp;
            bool want_write = false;
            std::uint32_t value = 0;
            for (std::size_t i = 2; i < args.size(); ++i) {
                if (args[i] == "=" && i + 1 < args.size()) {
                    want_write = true;
                    std::uint64_t v = 0;
                    if (!parse_u64_arg(args[i + 1].c_str(), &v)) break;
                    value = static_cast<std::uint32_t>(v);
                    break;
                }
            }
            if (want_write) {
                auto st = cli.session.write_ur(cta_id, warp, ur, value);
                if (st.failed())
                    std::fprintf(stderr, "(dbg) %s\n", st.error().message().c_str());
                else
                    std::printf("UR%d = 0x%08x\n", ur, value);
                continue;
            }
            std::uint32_t out = 0;
            auto st = cli.session.read_ur(cta_id, warp, ur, &out);
            if (st.failed())
                std::fprintf(stderr, "(dbg) %s\n", st.error().message().c_str());
            else
                std::printf("UR%d = 0x%08x\n", ur, out);
            continue;
        }
        if (cmd == "pred") {
            if (args.size() < 2) {
                std::fputs("usage: pred P# [= 0|1] [@Ln]\n", stderr);
                continue;
            }
            int pd = -1;
            if (args[1].size() >= 2 && args[1][0] == 'P')
                pd = static_cast<int>(std::strtoul(args[1].c_str() + 1, nullptr, 0));
            if (pd < 0 || pd > 6) {
                std::fputs("(dbg) bad predicate (P0..P6)\n", stderr);
                continue;
            }
            int lane = -1;
            {
                const std::string& tok = args[1];
                const std::size_t at = tok.find('@');
                if (at != std::string::npos) {
                    const char* lp = tok.c_str() + at + 1;
                    if (*lp == 'L' || *lp == 'l') ++lp;
                    lane = static_cast<int>(std::strtoul(lp, nullptr, 0));
                }
            }
            const std::uint32_t cta_id = cli.last.cta;
            const std::uint32_t warp = cli.last.warp;
            bool want_write = false;
            bool value = false;
            for (std::size_t i = 2; i < args.size(); ++i) {
                if (args[i] == "=" && i + 1 < args.size()) {
                    want_write = true;
                    value = std::strtoul(args[i + 1].c_str(), nullptr, 0) != 0;
                    break;
                }
            }
            if (want_write) {
                if (lane >= 0) {
                    cli.session.write_pred(cta_id, warp, lane, pd, value);
                    std::printf("P%d@L%d = %d\n", pd, lane, value ? 1 : 0);
                } else {
                    for (int l = 0; l < semu::kLanesPerWarp; ++l)
                        cli.session.write_pred(cta_id, warp, l, pd, value);
                    std::printf("P%d = %d (all lanes)\n", pd, value ? 1 : 0);
                }
                continue;
            }
            if (lane >= 0) {
                bool out = false;
                if (cli.session.read_pred(cta_id, warp, lane, pd, &out).ok())
                    std::printf("P%d@L%d = %d\n", pd, lane, out ? 1 : 0);
                continue;
            }
            for (int l = 0; l < semu::kLanesPerWarp; ++l) {
                bool out = false;
                if (cli.session.read_pred(cta_id, warp, l, pd, &out).ok())
                    std::printf("  P%d[L%02d] = %d\n", pd, l, out ? 1 : 0);
            }
            continue;
        }
        if (cmd == "pc") {
            const std::uint32_t cta_id = cli.last.cta;
            const std::uint32_t warp = cli.last.warp;
            bool want_write = false;
            std::uint64_t target = 0;
            for (std::size_t i = 2; i < args.size(); ++i) {
                if (args[i] == "=" && i + 1 < args.size()) {
                    want_write = true;
                    parse_u64_arg(args[i + 1].c_str(), &target);
                    break;
                }
            }
            if (want_write) {
                bool any_bad = false;
                for (int l = 0; l < semu::kLanesPerWarp; ++l) {
                    auto st = cli.session.write_pc(cta_id, warp, l, target);
                    if (st.failed()) any_bad = true;
                }
                std::printf("pc set to 0x%llx for all lanes of cta %u warp %u%s\n",
                            static_cast<unsigned long long>(target), cta_id, warp,
                            any_bad ? " (some lanes rejected; out of text)" : "");
                continue;
            }
            auto st = cli.session.cta_index(cta_id);
            if (!st.ok()) {
                std::fprintf(stderr, "(dbg) %s\n", st.take_error().describe().c_str());
                continue;
            }
            const auto& ws = cli.session.ctas()[st.value()].warps[warp];
            for (int l = 0; l < semu::kLanesPerWarp; ++l) {
                if (ws.threads[l].active || !ws.threads[l].exited)
                    std::printf("  PC[L%02d] = 0x%llx\n", l,
                                static_cast<unsigned long long>(ws.threads[l].pc));
            }
            continue;
        }
        if (cmd == "sreg") {
            int lane = 0;
            if (args.size() > 1) {
                std::uint32_t lanev = 0;
                if (parse_u32_arg(args[1].c_str(), &lanev)) lane = static_cast<int>(lanev);
            }
            const std::uint32_t cta_id = cli.last.cta;
            const std::uint32_t warp = cli.last.warp;
            for (int sr = static_cast<int>(semu::SpecialReg::kTidX);
                 sr <= static_cast<int>(semu::SpecialReg::kSmId); ++sr) {
                auto v = cli.session.read_special(
                    cta_id, warp, lane, static_cast<semu::SpecialReg>(sr));
                if (v.ok())
                    std::printf("  SR[%d] L%02d = 0x%08x\n", sr, lane, v.value());
            }
            continue;
        }
        if (cmd == "mem") {
            if (args.size() < 3) {
                std::fputs("usage: mem <g|s|l|c> <addr> [len] [--cta N] "
                           "[--warp N]\n"
                           "       mem w <g|s|l|c> <addr> <hexbytes> "
                           "[--cta N] [--warp N]\n"
                           "       mem <space> w <addr> <hexbytes> "
                           "[scope]\n"
                           "  (shared requires --cta; local requires --cta "
                           "--warp)\n",
                           stderr);
                continue;
            }
            semu::AddressSpace space = semu::AddressSpace::kGlobal;
            std::size_t i = 1;
            bool write_mode = false;
            if (args[i] == "w") {
                write_mode = true;
                ++i;
            }
            std::string sp = args[i];
            if (sp == "s" || sp == "shared") space = semu::AddressSpace::kShared;
            else if (sp == "l" || sp == "local") space = semu::AddressSpace::kLocal;
            else if (sp == "c" || sp == "constant") space = semu::AddressSpace::kConstant;
            else if (sp == "g" || sp == "global") space = semu::AddressSpace::kGlobal;
            else {
                std::fputs("(dbg) space must be g/s/l/c\n", stderr);
                continue;
            }
            ++i;
            if (!write_mode && args.size() > i && args[i] == "w") {
                write_mode = true;
                ++i;
            }
            // Blocker (Phase 7 re-review): shared/local need an explicit
            // (cta [, warp]) scope; parse trailing --cta/--warp.  Round 2
            // re-review (High-1): local memory is a per-warp window — there
            // is no --lane dimension, so it is no longer parsed.
            semu::MemoryScope scope;
            auto parse_scope = [&](std::size_t start) -> bool {
                std::size_t j = start;
                while (j < args.size()) {
                    const std::string& a = args[j];
                    if (a == "--cta" && j + 1 < args.size()) {
                        std::uint32_t v = 0;
                        if (parse_u32_arg(args[j + 1].c_str(), &v)) scope.cta = v;
                        j += 2;
                    } else if (a == "--warp" && j + 1 < args.size()) {
                        std::uint32_t v = 0;
                        if (parse_u32_arg(args[j + 1].c_str(), &v)) scope.warp = v;
                        j += 2;
                    } else if (a == "--lane") {
                        // High-1: rejected explicitly (local is per-warp).
                        std::fputs("(dbg) --lane is not a scope dimension for "
                                   "shared/local (local is a per-warp "
                                   "window)\n", stderr);
                        return false;
                    } else {
                        return false;
                    }
                }
                return true;
            };
            if (write_mode) {
                if (args.size() < i + 2) {
                    std::fputs("usage: mem w <space> <addr> <hexbytes>\n", stderr);
                    continue;
                }
                std::uint64_t addr = 0;
                if (!parse_u64_arg(args[i].c_str(), &addr)) {
                    std::fputs("(dbg) bad addr\n", stderr);
                    continue;
                }
                const std::string hex = args[i + 1];
                if (hex.size() % 2 != 0) {
                    std::fputs("(dbg) hex must have even length\n", stderr);
                    continue;
                }
                if (i + 2 < args.size() && !parse_scope(i + 2)) {
                    std::fputs("(dbg) bad scope tokens (--cta/--warp)\n",
                               stderr);
                    continue;
                }
                std::vector<std::uint8_t> bytes;
                for (std::size_t j = 0; j < hex.size(); j += 2) {
                    auto nib = [](char c) -> int {
                        if (c >= '0' && c <= '9') return c - '0';
                        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                        return -1;
                    };
                    const int hi = nib(hex[j]), lo = nib(hex[j + 1]);
                    if (hi < 0 || lo < 0) {
                        std::fputs("(dbg) bad hex\n", stderr);
                        break;
                    }
                    bytes.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
                }
                if (bytes.empty()) continue;
                auto st = cli.session.write_memory(space, addr, bytes, scope);
                if (st.failed())
                    std::fprintf(stderr, "(dbg) %s\n", st.error().message().c_str());
                else
                    std::printf("(dbg) mem %s 0x%llx wrote %zu byte(s)%s%s\n",
                                semu::to_string(space),
                                static_cast<unsigned long long>(addr),
                                bytes.size(),
                                scope.cta ? (" cta=" + std::to_string(*scope.cta)).c_str() : "",
                                scope.warp ? (" warp=" + std::to_string(*scope.warp)).c_str() : "");
                continue;
            }
            std::uint64_t addr = 0, len = 4;
            if (!parse_u64_arg(args[i].c_str(), &addr)) {
                std::fputs("(dbg) bad addr\n", stderr);
                continue;
            }
            if (args.size() > i + 1 && !parse_u64_arg(args[i + 1].c_str(), &len)) {
                // Not a plain number: try scope tokens from here.
                if (!parse_scope(i + 1)) {
                    std::fputs("(dbg) bad len or scope tokens\n", stderr);
                    continue;
                }
            } else if (args.size() > i + 2) {
                if (!parse_scope(i + 2)) {
                    std::fputs("(dbg) bad scope tokens (--cta/--warp)\n",
                               stderr);
                    continue;
                }
            }
            std::vector<std::uint8_t> bytes;
            auto st = cli.session.read_memory(space, addr, len, &bytes, scope);
            if (st.failed()) {
                std::fprintf(stderr, "(dbg) %s\n", st.error().describe().c_str());
                continue;
            }
            std::printf("(dbg) mem %s 0x%llx [%llu]%s%s:", semu::to_string(space),
                        static_cast<unsigned long long>(addr),
                        static_cast<unsigned long long>(len),
                        scope.cta ? (" cta=" + std::to_string(*scope.cta)).c_str() : "",
                        scope.warp ? (" warp=" + std::to_string(*scope.warp)).c_str() : "");
            for (std::size_t j = 0; j < bytes.size(); ++j)
                std::printf(" %02x", bytes[j]);
            std::printf("\n");
            continue;
        }
        if (cmd == "focus") {
            if (args.size() < 2) {
                auto f = cli.session.focus();
                if (f)
                    std::printf("(dbg) focus cta=%u warp=%u\n", f->first, f->second);
                else
                    std::printf("(dbg) no focus (whole launch)\n");
                continue;
            }
            if (args[1] == "off") {
                cli.session.set_focus(std::nullopt);
                std::printf("(dbg) focus cleared\n");
                continue;
            }
            const std::size_t dot = args[1].find('.');
            std::uint32_t cta = 0, w = 0;
            if (dot == std::string::npos ||
                !parse_u32_arg(args[1].substr(0, dot).c_str(), &cta) ||
                !parse_u32_arg(args[1].substr(dot + 1).c_str(), &w)) {
                std::fputs("usage: focus <cta>.<warp> | focus off\n", stderr);
                continue;
            }
            semu::Status st = cli.session.set_focus(std::make_pair(cta, w));
            if (st.failed()) {
                std::fprintf(stderr, "(dbg) %s\n", st.error().describe().c_str());
                continue;
            }
            std::printf("(dbg) focus cta=%u warp=%u\n", cta, w);
            continue;
        }
        if (cmd == "limit") {
            if (args.size() > 1) {
                std::uint64_t n = 0;
                if (!parse_u64_arg(args[1].c_str(), &n)) {
                    std::fputs("(dbg) bad limit\n", stderr);
                    continue;
                }
                cli.session.set_instruction_limit(n);
            }
            std::printf("(dbg) instruction limit = %llu (executed %llu)\n",
                        static_cast<unsigned long long>(cli.session.instruction_limit()),
                        static_cast<unsigned long long>(cli.session.executed_count()));
            continue;
        }
        if (cmd == "fault") {
            const auto& f = cli.session.fault();
            const bool have_last = cli.last.fault.has_value();
            if (!f && !have_last) {
                std::printf("(dbg) no fault\n");
            } else {
                if (f) {
                    std::printf("(dbg) terminal fault %s: %s\n",
                                semu::to_string(f->kind()), f->message().c_str());
                }
                if (have_last) {
                    std::printf("(dbg) last step stopped with %s: %s\n",
                                semu::to_string(cli.last.fault->kind()),
                                cli.last.fault->message().c_str());
                }
            }
            continue;
        }
        if (cmd == "trace") {
            std::printf("(dbg) %zu step(s) recorded\n", cli.trace.size());
            for (std::size_t j = 0; j < cli.trace.size(); ++j)
                std::printf("  %3zu %s\n", j, cli.trace[j].c_str());
            continue;
        }
        if (cmd == "help") {
            std::printf(
                "(dbg) commands:\n"
                "  s [N] | step [N]      step N dynamic warp instruction(s)\n"
                "  c | continue          run until stop condition (breaks "
                "step over once)\n"
                "  b pc <addr> [conds]   PC breakpoint\n"
                "  b mnem <STG> [conds]  mnemonic breakpoint\n"
                "  wb <g|s|l|c> <base> <len> [r|w|a] [conds]\n"
                "  del <id> | del b <id> | del w <id>\n"
                "  info b | info w\n"
                "  r R# [= val] [@Ln]   GPR view/write (default last cta/warp)\n"
                "  ur UR# [= val]       uniform register view/write\n"
                "  pred P# [= 0|1]      predicate view/write\n"
                "  pc [= addr]          lane PC view / set (jump)\n"
                "  sreg L#              special registers for a lane\n"
                "  mem <g|s|l|c> <addr> <len> [--cta N [--warp N]]\n"
                "  mem w <space> <addr> <hex> [same scope]\n"
                "    shared/local need explicit --cta (and --warp for local)\n"
                "  info last | state | sb | b | w\n"
                "  trace                reproducible step trace\n"
                "  focus <cta>.<warp> | focus off\n"
                "  limit [N]            show / set instruction limit\n"
                "  fault                show terminal fault\n"
                "  q | quit\n"
                "  conds: --cta N --warp N --lane 0xMASK\n");
            continue;
        }
        std::printf("(dbg) unknown command '%s' (help)\n", cmd.c_str());
    }
    return cli.session.faulted() || cli.session.finished() ? 0 : 0;
}

int main(int argc, char** argv) {
    if (argc < 2) {
        print_usage(stderr);
        return 2;
    }
    const std::string cmd = argv[1];

    if (cmd == "--help" || cmd == "-h" || cmd == "help") {
        print_usage(stdout);
        return 0;
    }
    if (cmd == "--version" || cmd == "-V" || cmd == "version") {
        return run_version();
    }
    if (cmd == "capability") {
        const bool full = argc >= 3 && std::strcmp(argv[2], "--full") == 0;
        if (argc >= 3 && !full) {
            std::fprintf(stderr, "semu: unknown capability option '%s'\n",
                         argv[2]);
            return 2;
        }
        return run_capability(full);
    }
    if (cmd == "disasm") {
        // disasm <lo> <hi> decodes a single word; `disasm` with no args
        // reads "lo hi" pairs from stdin (batch); disasm <cubin> [kernel]
        // disassembles a module.  Disambiguate: a first arg that parses as
        // a plain hex number is a word.
        const bool is_word =
            argc >= 4 && argv[2][0] != '\0' &&
            (std::strspn(argv[2], "0123456789abcdefABCDEFxX") ==
             std::strlen(argv[2]));
        if (is_word || argc < 3) {
            return run_disasm(argc, argv);
        }
        return run_disasm_module(argc, argv);
    }
    if (cmd == "scan-conds") {
        return run_scan_conds();
    }
    if (cmd == "cond-eval") {
        return run_cond_eval(argc, argv);
    }
    if (cmd == "decode-json") {
        return run_decode_json(argc, argv);
    }
    if (cmd == "eval-cond") {
        return run_eval_cond();
    }
    if (cmd == "load") {
        return run_load(argc, argv);
    }
    if (cmd == "inspect") {
        return run_inspect(argc, argv);
    }
    if (cmd == "list-kernels") {
        return run_list_kernels(argc, argv);
    }
    if (cmd == "run") {
        return run_interp(argc, argv);
    }
    if (cmd == "debug") {
        return run_debug(argc, argv);
    }

    std::fprintf(stderr, "semu: unknown command '%s'\n\n", cmd.c_str());
    print_usage(stderr);
    return 2;
}
