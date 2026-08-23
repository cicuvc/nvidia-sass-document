#include <semu/decoder/decoder.hpp>

#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#include "internal.hpp"
#include "isa_data.hpp"

namespace semu {

using decoder::IsaData;

// ---------------------------------------------------------------------------
// Compiled-in ISA lookup tables (built once from the generated data).
// ---------------------------------------------------------------------------
const IsaData& isa_data() {
    static const IsaData data = [] {
        IsaData d;
        for (std::uint32_t i = 0; i < isa::kNumEnums; ++i) {
            d.enums[isa::kEnums[i].name] = &isa::kEnums[i];
        }
        for (std::uint32_t i = 0; i < isa::kNumTables; ++i) {
            d.tables[isa::kTables[i].name] = &isa::kTables[i];
        }
        return d;
    }();
    return data;
}

std::uint64_t extract_field(const isa::Field& f, Word128 w) {
    std::uint64_t val = 0;
    for (std::uint8_t i = 0; i < f.nranges; ++i) {
        const int hi = f.ranges[2 * i];
        const int lo = f.ranges[2 * i + 1];
        const int width = hi - lo + 1;
        const std::uint64_t mask = (width == 64)
                                       ? ~std::uint64_t{0}
                                       : ((std::uint64_t{1} << width) - 1);
        std::uint64_t part;
        if (lo >= 64) {
            part = (w.hi >> (lo - 64)) & mask;
        } else if (hi < 64) {
            part = (w.lo >> lo) & mask;
        } else {
            const int lo_w = 64 - lo;
            const std::uint64_t lo_mask = (lo_w == 64)
                                              ? ~std::uint64_t{0}
                                              : ((std::uint64_t{1} << lo_w) - 1);
            // hi_part << lo_w is UB when lo_w == 64 (lo == 0); in that case
            // width - lo_w <= 0 so the hi contribution is empty.
            std::uint64_t hi_part = 0;
            if (width - lo_w > 0 && width - lo_w < 64) {
                hi_part = w.hi & ((std::uint64_t{1} << (width - lo_w)) - 1);
            } else if (width - lo_w >= 64) {
                hi_part = w.hi;
            }
            part = ((w.lo >> lo) & lo_mask);
            if (lo_w < 64) {
                part |= hi_part << lo_w;
            }
        }
        // width == 64: the range is the whole field, so val must be 0;
        // shifting 0 by 64 is still UB, so assign instead.
        if (width >= 64) {
            val = part;
        } else {
            val = (val << width) | part;
        }
    }
    return val;
}

std::int64_t parse_int(std::string_view s) {
    if (s.empty()) return 0;
    char* end = nullptr;
    long v = std::strtol(std::string(s).c_str(), &end, 0);
    if (end == s.data()) return 0;
    return v;
}

bool parse_int_full(std::string_view s, std::int64_t* out) {
    if (s.empty()) return false;
    std::string tmp(s);
    char* end = nullptr;
    long v = std::strtol(tmp.c_str(), &end, 0);
    if (end == tmp.c_str() || *end != '\0') return false;
    *out = v;
    return true;
}

// Attribute suffix for slot@attr names (mirrors the encoder).
const char* attr_suffix(std::string_view attr) {
    if (attr == "not") return "_not";
    if (attr == "negate") return "_negated";
    if (attr == "absolute") return "_abs";
    if (attr == "invert") return "_invert";
    return "";
}

// Reverse-lookup a table_fn field: set each arg slot from the matching row.
// Returns true when a row matched.
bool reverse_table_fn(DecodeCtx& ctx, const isa::Field& f,
                      std::uint64_t value) {
    std::string rhs(f.rhs);
    std::size_t open = rhs.find('(');
    if (open == std::string::npos) return true;
    std::string tname = rhs.substr(0, open);
    std::string args = rhs.substr(open + 1);
    if (!args.empty() && args.back() == ')') args.pop_back();
    auto argnames = decoder::split_row_args(args);
    const isa::TableDef* tbl = isa_data().table(tname);
    if (!tbl) return true;
    for (std::uint32_t i = 0; i < tbl->n; ++i) {
        std::int64_t outv;
        if (!parse_int_full(tbl->out[i], &outv)) continue;
        if (static_cast<std::uint64_t>(outv) != value) continue;
        auto inargs = decoder::split_row_args(tbl->in[i]);
        for (std::size_t a = 0; a < argnames.size() && a < inargs.size(); ++a) {
            std::int64_t av;
            if (parse_int_full(inargs[a], &av)) {
                ctx.sm[argnames[a]] = av;
            }
        }
        return true;
    }
    return false;
}

// Reverse-lookup a star_slot *TABLES_x(arg,...) field.  RHS args that are
// integer literals must match the row's `in` values; slot args are set from
// the row.  Returns true when a row matched.
bool reverse_star_table_fn(DecodeCtx& ctx, const std::string& rhs,
                           std::uint64_t value, std::string* reject) {
    std::string body = rhs.size() > 1 ? rhs.substr(1) : rhs;
    std::size_t open = body.find('(');
    if (open == std::string::npos || body.empty() ||
        body.back() != ')') {
        if (reject) *reject = "malformed star table fn " + body;
        return false;
    }
    std::string tname = body.substr(0, open);
    std::string args = body.substr(open + 1);
    if (!args.empty() && args.back() == ')') args.pop_back();
    auto argnames = decoder::split_row_args(args);
    const isa::TableDef* tbl = isa_data().table(tname);
    if (!tbl) {
        if (reject) *reject = "no table " + tname;
        return false;
    }
    for (std::uint32_t i = 0; i < tbl->n; ++i) {
        std::int64_t outv;
        if (!parse_int_full(tbl->out[i], &outv)) continue;
        if (static_cast<std::uint64_t>(outv) != value) continue;
        auto inargs = decoder::split_row_args(tbl->in[i]);
        if (inargs.size() != argnames.size()) continue;
        bool args_ok = true;
        for (std::size_t a = 0; a < argnames.size(); ++a) {
            std::int64_t litv;
            if (parse_int_full(argnames[a], &litv)) {
                std::int64_t inrow;
                if (!parse_int_full(inargs[a], &inrow) || inrow != litv) {
                    args_ok = false;
                    break;
                }
            }
        }
        if (!args_ok) continue;
        for (std::size_t a = 0; a < argnames.size(); ++a) {
            std::int64_t av;
            if (parse_int_full(argnames[a], &av)) continue;  // literal arg
            if (parse_int_full(inargs[a], &av)) {
                ctx.sm[argnames[a]] = av;
            }
        }
        return true;
    }
    if (reject) {
        char buf[128];
        std::snprintf(buf, sizeof(buf), "no %s row for value 0x%" PRIx64,
                      tname.c_str(), value);
        *reject = buf;
    }
    return false;
}

namespace {

// ---------------------------------------------------------------------------
// build_decode_ctx: fixed-bit checks + slot map + legality conditions for a
// candidate variant (no rendering).  try_decode_variant adds rendering;
// Decoder::disassemble uses this directly to re-render disassembly text on
// demand without storing it on the instruction.
// ---------------------------------------------------------------------------
bool build_decode_ctx(const isa::Variant* v, Word128 word, DecodeCtx& ctx,
                      std::string* reject) {
    ctx.variant = v;
    ctx.word = word;

    for (std::uint16_t fi = 0; fi < v->nfields; ++fi) {
        const isa::Field& f = v->fields[fi];
        const std::uint64_t val = extract_field(f, word);
        ctx.fields.emplace_back(&f, val);
        std::string rhs(f.rhs);
        char buf[160];
        switch (f.rhs_kind) {
            case 3: {  // num: fixed literal
                const std::int64_t want = parse_int(rhs);
                if (static_cast<std::int64_t>(val) != want) {
                    std::snprintf(buf, sizeof(buf),
                                  "fixed bit field %s = 0x%" PRIx64
                                  " (expected 0x%" PRIx64 ")",
                                  f.name, val, want);
                    *reject = buf;
                    return false;
                }
                break;
            }
            case 4: {  // star_num: reserved literal
                const std::int64_t want =
                    rhs.size() > 1 ? parse_int(rhs.substr(1)) : 0;
                if (static_cast<std::int64_t>(val) != want) {
                    std::snprintf(buf, sizeof(buf),
                                  "reserved scoreboard field %s = 0x%" PRIx64
                                  " (expected 0x%" PRIx64 ")",
                                  f.name, val, want);
                    *reject = buf;
                    return false;
                }
                break;
            }
            case 5: {  // star_slot: encodes the named slot's value
                std::string slot_name = rhs.size() > 1 ? rhs.substr(1) : rhs;
                if (!slot_name.empty() && slot_name[0] == '*') {
                    slot_name = slot_name.substr(1);
                }
                // *TABLES_x(arg,...): reverse table lookup with literal-arg
                // matching (LDGMC/UBLKCP's mem discriminator field).
                if (!slot_name.empty() && slot_name.find('(') != std::string::npos) {
                    if (!reverse_star_table_fn(ctx, rhs, val, reject)) {
                        return false;
                    }
                    break;
                }
                std::int64_t lit;
                if (parse_int_full(slot_name, &lit)) {
                    if (static_cast<std::int64_t>(val) != lit) {
                        std::snprintf(buf, sizeof(buf),
                                      "pinned field %s = 0x%" PRIx64
                                      " (expected 0x%" PRIx64 ")",
                                      f.name, val, lit);
                        *reject = buf;
                        return false;
                    }
                } else {
                    ctx.sm[slot_name] = static_cast<std::int64_t>(val);
                    // Discriminator check: the value must be a member of the
                    // referenced format slot's enum type.  Variants that pin
                    // dstfmt/srcfmt/merge/... to disjoint value sets are
                    // therefore only matched by the word that carries a valid
                    // member (e.g. F2I's cop/srcfmt, F2FP's dstfmt/srcfmt).
                    const isa::Slot* slot = nullptr;
                    for (std::uint16_t si = 0; si < v->nslots; ++si) {
                        if (std::strcmp(v->slots[si].name, slot_name.c_str()) == 0) {
                            slot = &v->slots[si];
                            break;
                        }
                    }
                    if (slot) {
                        // Only a registered enum type constrains the value.
                        // Free/absence-typed slots (INCONLY has no enum) accept
                        // any value; the discriminator then falls to siblings
                        // that do carry a registered enum (ARRIVE=10).
                        if (isa_data().enums.count(slot->type) &&
                            !isa_data().enum_has_value(
                                slot->type, static_cast<std::int64_t>(val))) {
                            std::snprintf(buf, sizeof(buf),
                                          "discriminator %s = 0x%" PRIx64
                                          " not a valid %s value",
                                          slot_name.c_str(), val, slot->type);
                            *reject = buf;
                            return false;
                        }
                    }
                }
                break;
            }
            case 0: {  // slot: value (scaled up on decode)
                const std::int64_t scale = f.scale ? f.scale : 1;
                ctx.sm[rhs] = static_cast<std::int64_t>(val) * scale;
                break;
            }
            case 1: {  // slot_attr: X@attr
                std::size_t at = rhs.find('@');
                if (at != std::string::npos) {
                    const char* suffix =
                        attr_suffix(rhs.substr(at + 1));
                    ctx.sm[rhs.substr(0, at) + suffix] =
                        static_cast<std::int64_t>(val);
                }
                break;
            }
            case 6: {  // table_fn: reverse lookup
                if (!reverse_table_fn(ctx, f, val)) {
                    std::string tname = rhs.substr(0, rhs.find('('));
                    std::snprintf(buf, sizeof(buf),
                                  "no %s row for value 0x%" PRIx64,
                                  tname.c_str(), val);
                    *reject = buf;
                    return false;
                }
                break;
            }
            case 7: {  // other_fn
                std::size_t open = rhs.find('(');
                if (open != std::string::npos) {
                    std::string fn = rhs.substr(0, open);
                    std::string args = rhs.substr(open + 1);
                    if (!args.empty() && args.back() == ')') args.pop_back();
                    auto argnames = decoder::split_row_args(args);
                    if (fn == "VarLatOperandEnc") {
                        if (!argnames.empty()) {
                            ctx.sm[argnames[0]] =
                                static_cast<std::int64_t>(val);
                        }
                    } else if (fn == "IDENTICAL") {
                        for (const auto& a : argnames) {
                            ctx.sm[a] = static_cast<std::int64_t>(val);
                        }
                    } else if (fn == "ConstBankAddress0" ||
                               fn == "ConstBankAddress2") {
                        // each bank/offset field carries its own value.
                        ctx.sm[f.name] = static_cast<std::int64_t>(val);
                    }
                }
                break;
            }
            case 2:  // opcode
            default:
                break;
        }
    }

    // legality conditions -- evaluated by the per-variant merged thunk
    // (compile-time hardened by the generator), never by runtime string
    // parsing.  This variant's packed condition-slot array is filled once from
    // the decoded slot map; absent slots stay 0 (lenient reference semantics).
    if (v->check) {
        static thread_local std::int64_t g_slots[isa::kMaxCondSlots];
        for (std::uint16_t k = 0; k < v->ncondslots; ++k) {
            auto it = ctx.sm.find(v->condslots[k]);
            g_slots[k] = it == ctx.sm.end() ? 0 : it->second;
        }
        if (auto err = v->check(word, g_slots)) {
            std::string reason(err->error_type);
            if (err->message && *err->message) {
                reason += ": ";
                reason += err->message;
            }
            *reject = std::move(reason);
            return false;
        }
    }

    return true;
}

bool try_decode_variant(const isa::Variant* v, Word128 word,
                        std::unique_ptr<DecodedInstruction>* inst,
                        std::string* reject) {
    DecodeCtx ctx;
    if (!build_decode_ctx(v, word, ctx, reject)) return false;
    *inst = render_instruction(v, word, ctx);
    return *inst != nullptr;
}

}

std::string Decoder::disassemble(Word128 word, bool full) const {
    const std::uint16_t opc = opcode_of(word.lo, word.hi);
    const std::uint32_t start = isa::kOpcodeStart[opc];
    const std::uint32_t end = isa::kOpcodeStart[opc + 1];
    if (start == end) return "";
    for (std::uint32_t i = start; i < end; ++i) {
        const isa::Variant* v = &isa::kVariants[i];
        if (v->alternate) continue;
        DecodeCtx ctx;
        std::string reject;
        if (!build_decode_ctx(v, word, ctx, &reject)) continue;
        auto inst = render_instruction(v, word, ctx);
        if (!inst) continue;
        return render_disasm_text(v, ctx, *inst, full);
    }
    return "";
}


DecodeResult::DecodeResult(const DecodeResult& o)
    : outcome_(o.outcome_),
      instruction_(o.instruction_ ? o.instruction_->clone() : nullptr),
      candidates_(o.candidates_) {}

DecodeResult& DecodeResult::operator=(const DecodeResult& o) {
    if (this == &o) return *this;
    outcome_ = o.outcome_;
    instruction_ = o.instruction_ ? o.instruction_->clone() : nullptr;
    candidates_ = o.candidates_;
    return *this;
}

DecodeResult Decoder::decode(Word128 word) const {
    DecodeResult res;
    const std::uint16_t opc = opcode_of(word.lo, word.hi);
    const std::uint32_t start = isa::kOpcodeStart[opc];
    const std::uint32_t end = isa::kOpcodeStart[opc + 1];
    if (start == end) {
        res.outcome_ = DecodeOutcome::kIllegal;
        char buf[96];
        std::snprintf(buf, sizeof(buf),
                      "no variant for opcode 0x%X (bits [91]|[11:0])", opc);
        res.candidates_.push_back({"", buf});
        return res;
    }

    std::vector<std::unique_ptr<DecodedInstruction>> matched;
    std::vector<CandidateRejection> rejected;
    for (std::uint32_t i = start; i < end; ++i) {
        const isa::Variant* v = &isa::kVariants[i];
        // ALTERNATE CLASSes are alternative encodings, not decode candidates
        // (matches the reference disassembler).
        if (v->alternate) {
            rejected.push_back({isa::variant_class_name(v->variant_class),
                                "alternate class (not a decode candidate)"});
            continue;
        }
        std::unique_ptr<DecodedInstruction> inst;
        std::string reason;
        if (try_decode_variant(v, word, &inst, &reason)) {
            matched.push_back(std::move(inst));
        } else {
            rejected.push_back({isa::variant_class_name(v->variant_class),
                                reason});
        }
    }

    if (matched.size() == 1) {
        res.outcome_ = DecodeOutcome::kUnique;
        res.instruction_ = std::move(matched[0]);
        res.candidates_ = std::move(rejected);
        return res;
    }
    if (matched.size() > 1) {
        res.outcome_ = DecodeOutcome::kAmbiguous;
        for (auto& m : matched) {
            res.candidates_.push_back(
                {isa::variant_class_name(m->variant_class), ""});
        }
        for (auto& r : rejected) {
            res.candidates_.push_back(std::move(r));
        }
        return res;
    }
    res.outcome_ = DecodeOutcome::kIllegal;
    res.candidates_ = std::move(rejected);
    return res;
}

DecodeResult Decoder::decode(std::uint64_t lo, std::uint64_t hi) const {
    return decode(Word128{lo, hi});
}

std::vector<const isa::Variant*> Decoder::candidates(
    std::uint16_t opcode) const {
    std::vector<const isa::Variant*> out;
    const std::uint32_t start = isa::kOpcodeStart[opcode];
    const std::uint32_t end = isa::kOpcodeStart[opcode + 1];
    for (std::uint32_t i = start; i < end; ++i) {
        out.push_back(&isa::kVariants[i]);
    }
    return out;
}

Decoder::Decoder() {}

const Decoder& Decoder::instance() {
    static const Decoder dec;
    return dec;
}

}  // namespace semu
