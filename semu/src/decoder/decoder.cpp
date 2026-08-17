#include <semu/decoder.hpp>

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
using decoder::ExprEvaluator;

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
        for (std::uint32_t i = 0; i < isa::kNumParameters; ++i) {
            d.parameters[isa::kParameters[i]] = isa::kParameterVals[i];
        }
        for (std::uint32_t i = 0; i < isa::kNumConstants; ++i) {
            d.constants[isa::kConstants[i]] = isa::kConstantVals[i];
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
// build_slot_map: extract every encoding field of a variant into the slot
// map (ctx.sm) exactly as the decoder does, WITHOUT the fixed-bit / reserved /
// discriminator rejection gates.  Returns false (with `reject` reason) only
// on structural failures (malformed table fn / no table row) where the slot
// map cannot be built at all.  Used both by try_decode_variant and by the
// per-condition verdict API (GAP-09).
// ---------------------------------------------------------------------------
bool build_slot_map(const isa::Variant* v, Word128 word, DecodeCtx* ctx,
                    std::string* reject) {
    for (std::uint16_t fi = 0; fi < v->nfields; ++fi) {
        const isa::Field& f = v->fields[fi];
        const std::uint64_t val = extract_field(f, word);
        ctx->fields.emplace_back(&f, val);
        std::string rhs(f.rhs);
        char buf[160];
        switch (f.rhs_kind) {
            case 3:  // num: fixed literal (checked by the caller's gate)
            case 4:  // star_num: reserved literal (checked by caller)
            case 2:  // opcode
            default:
                break;
            case 5: {  // star_slot
                std::string slot_name = rhs.size() > 1 ? rhs.substr(1) : rhs;
                if (!slot_name.empty() && slot_name[0] == '*') {
                    slot_name = slot_name.substr(1);
                }
                if (!slot_name.empty() &&
                    slot_name.find('(') != std::string::npos) {
                    if (!reverse_star_table_fn(*ctx, rhs, val, reject)) {
                        return false;
                    }
                    break;
                }
                std::int64_t lit;
                if (parse_int_full(slot_name, &lit)) {
                    break;  // pinned literal
                }
                ctx->sm[slot_name] = static_cast<std::int64_t>(val);
                break;
            }
            case 0: {  // slot: value (scaled up on decode)
                const std::int64_t scale = f.scale ? f.scale : 1;
                ctx->sm[rhs] = static_cast<std::int64_t>(val) * scale;
                break;
            }
            case 1: {  // slot_attr: X@attr
                std::size_t at = rhs.find('@');
                if (at != std::string::npos) {
                    const char* suffix =
                        attr_suffix(rhs.substr(at + 1));
                    ctx->sm[rhs.substr(0, at) + suffix] =
                        static_cast<std::int64_t>(val);
                }
                break;
            }
            case 6: {  // table_fn: reverse lookup
                if (!reverse_table_fn(*ctx, f, val)) {
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
                            ctx->sm[argnames[0]] =
                                static_cast<std::int64_t>(val);
                        }
                    } else if (fn == "IDENTICAL") {
                        for (const auto& a : argnames) {
                            ctx->sm[a] = static_cast<std::int64_t>(val);
                        }
                    } else if (fn == "ConstBankAddress0" ||
                               fn == "ConstBankAddress2") {
                        ctx->sm[f.name] = static_cast<std::int64_t>(val);
                    }
                }
                break;
            }
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// try_decode_variant: fixed-bit checks + slot map + legality conditions.
// ---------------------------------------------------------------------------
bool try_decode_variant(const isa::Variant* v, Word128 word,
                        DecodedInstruction* inst, std::string* reject) {
    DecodeCtx ctx;
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

    // legality conditions
    {
        ExprEvaluator ev(isa_data());
        ev.set_slots(ctx.sm);
        for (std::uint16_t ci = 0; ci < v->nconds; ++ci) {
            const isa::Cond& c = v->conds[ci];
            // GAP-04: a condition that cannot be fully parsed/resolved must
            // not be treated as satisfied -- reject with an explicit reason
            // so the decode never claims authoritative uniqueness on top of
            // an unevaluable legality check.
            auto r = ev.eval_bool_tristate(c.predicate);
            if (!r.has_value()) {
                std::string reason(c.error);
                reason += ": condition unresolved (parser gap)";
                if (c.message && *c.message) {
                    reason += ": ";
                    reason += c.message;
                }
                *reject = std::move(reason);
                return false;
            }
            if (!*r) {
                std::string reason(c.error);
                if (c.message && *c.message) {
                    reason += ": ";
                    reason += c.message;
                }
                *reject = std::move(reason);
                return false;
            }
        }
    }

    *inst = render_instruction(v, word, ctx);
    return true;
}

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

    std::vector<DecodedInstruction> matched;
    std::vector<CandidateRejection> rejected;
    for (std::uint32_t i = start; i < end; ++i) {
        const isa::Variant* v = &isa::kVariants[i];
        // ALTERNATE CLASSes are alternative encodings, not decode candidates
        // (matches the reference disassembler).
        if (v->alternate) {
            rejected.push_back({v->variant_class,
                                "alternate class (not a decode candidate)"});
            continue;
        }
        DecodedInstruction inst;
        std::string reason;
        if (try_decode_variant(v, word, &inst, &reason)) {
            matched.push_back(std::move(inst));
        } else {
            rejected.push_back({v->variant_class, reason});
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
            res.candidates_.push_back({m.variant_class, ""});
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

std::size_t scan_condition_parse_gaps(bool report,
                                      std::size_t* total_conds,
                                      std::size_t* resolved_conds) {
    std::size_t total = 0;
    std::size_t resolved = 0;
    std::size_t gaps = 0;
    for (std::uint32_t i = 0; i < isa::kNumVariants; ++i) {
        const isa::Variant* v = &isa::kVariants[i];
        ExprEvaluator ev(isa_data());
        // empty slot map: all slots evaluate to 0, which is sufficient to
        // detect tokenizer/grammar gaps (they return nullopt regardless of
        // slot values).
        static const std::unordered_map<std::string, std::int64_t> kEmpty;
        ev.set_slots(kEmpty);
        for (std::uint16_t ci = 0; ci < v->nconds; ++ci) {
            ++total;
            if (ev.eval_bool_tristate(v->conds[ci].predicate).has_value()) {
                ++resolved;
            } else {
                ++gaps;
                if (report) {
                    std::printf("%s\t%s\t%s\n", v->variant_class,
                                v->conds[ci].error, v->conds[ci].predicate);
                }
            }
        }
    }
    if (total_conds) *total_conds = total;
    if (resolved_conds) *resolved_conds = resolved;
    return gaps;
}

std::vector<ConditionVerdict> condition_verdicts(
    const std::string& variant_class, Word128 word) {
    std::vector<ConditionVerdict> out;
    const isa::Variant* variant = nullptr;
    for (std::uint32_t i = 0; i < isa::kNumVariants; ++i) {
        if (variant_class == isa::kVariants[i].variant_class) {
            variant = &isa::kVariants[i];
            break;
        }
    }
    if (!variant) {
        return out;
    }
    DecodeCtx ctx;
    ctx.variant = variant;
    ctx.word = word;
    std::string reject;
    if (!build_slot_map(variant, word, &ctx, &reject)) {
        // structural failure: every condition is unresolved
        for (std::uint16_t ci = 0; ci < variant->nconds; ++ci) {
            out.push_back({variant->conds[ci].error,
                           variant->conds[ci].predicate, 2});
        }
        return out;
    }
    ExprEvaluator ev(isa_data());
    ev.set_slots(ctx.sm);
    for (std::uint16_t ci = 0; ci < variant->nconds; ++ci) {
        const isa::Cond& c = variant->conds[ci];
        auto r = ev.eval_bool_tristate(c.predicate);
        int verdict = 2;  // unresolved
        if (r.has_value()) {
            verdict = *r ? 1 : 0;
        }
        out.push_back({c.error, c.predicate, verdict});
    }
    return out;
}

int eval_predicate(const std::string& predicate,
                   const std::vector<std::pair<std::string, std::int64_t>>&
                       slots) {
    ExprEvaluator ev(isa_data());
    std::unordered_map<std::string, std::int64_t> sm;
    for (const auto& [k, v] : slots) {
        sm[k] = v;
    }
    ev.set_slots(sm);
    auto r = ev.eval_bool_tristate(predicate);
    if (!r.has_value()) {
        return 2;  // unresolved
    }
    return *r ? 1 : 0;
}

}  // namespace semu
