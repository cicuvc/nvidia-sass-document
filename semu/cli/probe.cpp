// semu_probe: test/diagnostic tools kept out of the user-facing CLI.
//
// Currently hosts `decode-json` (GAP-10 structured decode used for
// cuobjdump differentials); probe commands can be added here without
// touching the `semu` binary's command surface.
//
// Splitting note (moved verbatim from cli/main.cpp -- the Interpreter- and
// loader-facing code stays in `semu`).

#include <semu/decoder/decoder.hpp>
#include <semu/decoder/decoded_access.hpp>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include <isa_manifest.hpp>  // ShapeManifest/kShapeManifests (decode bridge)

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

int print_usage(FILE* out) {
    std::fprintf(out,
                 "usage: semu_probe <command> [options]\n"
                 "commands:\n"
                 "  decode-json <lo> <hi>  structured decode (GAP-10); also\n"
                 "                       reads \"lo hi\" pairs from stdin\n"
                 "  --help                show this help\n"
                 "\n");
    return 0;
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
    if (cmd == "decode-json") {
        return run_decode_json(argc, argv);
    }
    std::fprintf(stderr, "semu_probe: unknown command '%s'\n\n", cmd.c_str());
    print_usage(stderr);
    return 2;
}
