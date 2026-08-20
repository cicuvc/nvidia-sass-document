#include "internal.hpp"

#include <cctype>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>
#include <string>
#include <vector>

#include "isa_data.hpp"
#include "isa_shapes_fill.hpp"

// const char* slot-type comparison helper.
static bool styp(const char* t, const char* want) {
    return std::strcmp(t, want) == 0;
}

// Disassembly rendering for a decoded variant -- a C++ port of
// tools/sass_disasm.py (which round-trips through the reference assembler).
// The output text is in the assembler source dialect so encode->decode->encode
// round-trips are bit-exact.

namespace semu {

using decoder::IsaData;
using decoder::ExprEvaluator;

namespace {

// Schedule/control slots never rendered as operands.
bool is_sched_slot(const std::string& name) {
    return name == "req" || name == "req_bit_set" || name == "usched_info" ||
           name == "batch_t" || name == "pm_pred" || name == "reuse_src_a" ||
           name == "reuse_src_b" || name == "reuse_src_c" ||
           name == "reuse_src_d" || name == "rd" || name == "wr" ||
           name == "src_rel_sb" || name == "dst_wr_sb";
}

bool is_addr_size_slot(const std::string& name) {
    return name.rfind("input_reg_sz", 0) == 0;
}

const char* size_key_for(const std::string& name) {
    if (name == "Rd") return "IDEST_SIZE";
    if (name == "Rd2") return "IDEST2_SIZE";
    if (name == "Re") return "ISRC_E_SIZE";
    if (name == "Ra") return "ISRC_A_SIZE";
    if (name == "Rb") return "ISRC_B_SIZE";
    if (name == "Rc") return "ISRC_C_SIZE";
    if (name == "Rh") return "ISRC_H_SIZE";
    if (name == "Ri") return "ISRC_I_SIZE";
    if (name == "URa") return "ILABEL_URa_SIZE";
    if (name == "URb") return "ILABEL_URb_SIZE";
    if (name == "URc") return "ILABEL_URc_SIZE";
    if (name == "URd") return "ILABEL_URd_SIZE";
    if (name == "URe") return "ILABEL_URe_SIZE";
    if (name == "Ra_URb") return "ILABEL_Ra_URb_SIZE";
    if (name == "Ra_URc") return "ILABEL_Ra_URc_SIZE";
    if (name == "Ra_URd") return "ILABEL_Ra_URd_SIZE";
    return nullptr;
}

bool has_pred(const isa::Variant* v, const std::string& key) {
    for (std::uint16_t i = 0; i < v->npreds; ++i) {
        if (std::strcmp(v->preds[i].key, key.c_str()) == 0) return true;
    }
    return false;
}

bool is_ureg_slot(const isa::Variant* v, const std::string& name) {
    std::string base = name;
    if (base.rfind("UR", 0) == 0) base = base.substr(2);
    if (base.size() < 2 || base == "URb") return false;
    if (base[0] != 'R') return false;
    std::string key = std::string("ILABEL_UR") +
                      static_cast<char>(std::tolower(base[1])) + "_SIZE";
    return has_pred(v, key);
}

std::string reg_text(std::int64_t base, int width, bool ureg) {
    const char* prefix = ureg ? "UR" : "R";
    if (base == 255) return ureg ? "URZ" : "RZ";
    if (width <= 32) return std::string(prefix) + std::to_string(base);
    std::string out = "{";
    const int n = width / 32;
    for (int k = 0; k < n; ++k) {
        if (k) out += ",";
        out += std::string(prefix) + std::to_string(base + k);
    }
    out += "}";
    return out;
}

std::uint32_t fp16_to_f32(std::uint32_t h) {
    const std::uint32_t sign = (h >> 15) & 1;
    const std::uint32_t exp = (h >> 10) & 0x1F;
    const std::uint32_t man = h & 0x3FF;
    if (exp == 0) {
        if (man == 0) return sign << 31;
        int e = -14;
        std::uint32_t m = man;
        while ((m & 0x400) == 0) {
            m <<= 1;
            --e;
        }
        m &= 0x3FF;
        return (sign << 31) | ((std::uint32_t)(e + 127) << 23) | (m << 13);
    }
    if (exp == 31) {
        return (sign << 31) | 0x7F800000u | (man << 13);
    }
    return (sign << 31) | ((exp - 15 + 127) << 23) | (man << 13);
}

std::string hex_str(std::int64_t v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "0x%llX",
                  static_cast<unsigned long long>(v));
    return buf;
}

std::string hex_f64(std::uint64_t v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "0x%016llX",
                  static_cast<unsigned long long>(v));
    return buf;
}

std::string hex_f32(std::uint32_t v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "0f%08X", v);
    return buf;
}

std::int64_t sign_ext(std::int64_t val, int width) {
    if (width == 64) return val;
    const std::int64_t sign = std::int64_t{1} << (width - 1);
    if (val & sign) val |= (~std::int64_t{0}) << width;
    return val;
}

// (default_value, always_print); port of sass_disasm.default_of.
std::pair<std::optional<std::int64_t>, bool> default_of(
    const isa::Slot& s) {
    if (!s.dflt) return {std::nullopt, false};
    std::string raw(s.dflt);
    bool pprint = raw.find("/PRINT") != std::string::npos;
    std::size_t slash = raw.find('/');
    std::string nm = raw.substr(0, slash);
    if (nm.size() >= 2 && nm.front() == '"' && nm.back() == '"') {
        nm = nm.substr(1, nm.size() - 2);
    }
    if (nm.empty()) return {std::nullopt, pprint};
    // numeric default
    char* end = nullptr;
    long iv = std::strtol(nm.c_str(), &end, 0);
    if (end != nm.c_str() && *end == '\0') return {iv, pprint};
    // enum-name default
    if (auto v = isa_data().enum_value(s.type, nm)) return {v, pprint};
    return {std::nullopt, pprint};
}

// slot value for a format slot; handles table_fn reverse (port of
// sass_disasm.slot_value).
std::optional<std::int64_t> do_slot_value(const DecodeCtx& ctx,
                                          const std::string& name) {
    // rhs-token / star_slot scan first (reference `field_for`): the value of a
    // FORMAT slot may live in a differently-named field whose RHS is the slot
    // name (`*clear` → nottid0 field for NANOSLEEP.CLEAR), while a field that
    // merely *shares* the name (`clear = *0` star_num) is a pinned literal and
    // must not shadow it.
    for (const auto& [f, val] : ctx.fields) {
        std::string rhs(f->rhs);
        std::string tok = rhs.substr(0, rhs.find(' '));
        if (rhs == name || tok == name) {
            return static_cast<std::int64_t>(val);
        }
        if (f->rhs_kind == 5 && tok.size() > 1 && tok[0] == '*' &&
            tok.substr(1) == name) {
            return static_cast<std::int64_t>(val);
        }
    }
    // direct field-name match (skip table_fn fields: their raw bits are
    // re-encoded through a table, so the reverse lookup below is authoritative)
    for (const auto& [f, val] : ctx.fields) {
        if (f->rhs_kind == 6) continue;
        if (std::string(f->name) == name) {
            return static_cast<std::int64_t>(val);
        }
    }
    // table_fn reverse: TABLES_x(...,name,...) -> arg value for the row
    for (const auto& [f, val] : ctx.fields) {
        if (f->rhs_kind != 6) continue;
        std::string rhs(f->rhs);
        std::size_t open = rhs.find('(');
        if (open == std::string::npos) continue;
        std::string tname = rhs.substr(0, open);
        std::string args = rhs.substr(open + 1);
        if (!args.empty() && args.back() == ')') args.pop_back();
        auto argnames = decoder::split_row_args(args);
        int idx = -1;
        for (std::size_t i = 0; i < argnames.size(); ++i) {
            if (argnames[i] == name) {
                idx = static_cast<int>(i);
                break;
            }
        }
        if (idx < 0) continue;
        const isa::TableDef* tbl = isa_data().table(tname);
        if (!tbl) continue;
        for (std::uint32_t i = 0; i < tbl->n; ++i) {
            std::int64_t outv;
            if (!parse_int_full(tbl->out[i], &outv)) continue;
            if (static_cast<std::uint64_t>(outv) != val) continue;
            auto inargs = decoder::split_row_args(tbl->in[i]);
            if (idx < static_cast<int>(inargs.size())) {
                std::int64_t av;
                if (parse_int_full(inargs[idx], &av)) return av;
            }
            return 0;
        }
        return std::nullopt;
    }
    // composite fields (ConstBankAddress...) carry the slot name
    for (const auto& [f, val] : ctx.fields) {
        if (std::string(f->name) == name) {
            return static_cast<std::int64_t>(val);
        }
    }
    return std::nullopt;
}

// operand size in bits for a register slot (default 32 / 64 for address regs).
int size_of(const isa::Variant* v, const DecodeCtx& ctx,
            const std::string& name, int dflt = 32) {
    const char* key = size_key_for(name);
    if (key) {
        for (std::uint16_t i = 0; i < v->npreds; ++i) {
            if (std::strcmp(v->preds[i].key, key) == 0) {
                ExprEvaluator ev(isa_data());
                ev.set_slots(ctx.sm);
                auto w = ev.eval_int(v->preds[i].value);
                if (w) return static_cast<int>(*w);
                return dflt;
            }
        }
        // size_key_for's key is absent (e.g. URd without ILABEL_URd_SIZE):
        // fall back to the destination/source size predicates like the
        // reference disassembler.
        key = nullptr;
    }
    if (!key) {
        if (name.rfind("Rd", 0) == 0 || name.rfind("URd", 0) == 0 ||
            name.rfind("Re", 0) == 0) {
            key = "IDEST_SIZE";
        } else if (name.rfind("Ra", 0) == 0 || name.rfind("Rb", 0) == 0 ||
                   name.rfind("Rc", 0) == 0) {
            if (name.rfind("Ra", 0) == 0) key = "ISRC_A_SIZE";
            else if (name.rfind("Rb", 0) == 0) key = "ISRC_B_SIZE";
            else key = "ISRC_C_SIZE";
        } else if (name.rfind("UR", 0) == 0) {
            key = "IDEST_SIZE";
        }
    }
    if (key) {
        for (std::uint16_t i = 0; i < v->npreds; ++i) {
            if (std::strcmp(v->preds[i].key, key) != 0) continue;
            ExprEvaluator ev(isa_data());
            ev.set_slots(ctx.sm);
            auto w = ev.eval_int(v->preds[i].value);
            if (w) return static_cast<int>(*w);
            break;
        }
    }
    return dflt;
}

// locate the encoding field for a slot (width in bits + decode scale).
const isa::Field* field_for_slot(const DecodeCtx& ctx, const std::string& name) {
    for (const auto& [f, val] : ctx.fields) {
        if (std::string(f->name) == name) return f;
        std::string rhs(f->rhs);
        std::string tok = rhs.substr(0, rhs.find(' '));
        if (tok == name) return f;
    }
    // composite / renamed slot: name appears inside the RHS (e.g. the C-bank
    // slot `Sa_offset` whose field is `Ra_offset = ConstBankAddress0(...Sa_offset)`).
    for (const auto& [f, val] : ctx.fields) {
        std::string rhs(f->rhs);
        std::string tok = rhs.substr(0, rhs.find('('));
        if (rhs.find(name) != std::string::npos) return f;
        if (f->rhs_kind == 5 && tok.size() > 1 && tok[0] == '*' &&
            std::string(tok.substr(1)).find(name) != std::string::npos) {
            return f;
        }
    }
    return nullptr;
}

int field_width(const isa::Field* f) {
    int w = 0;
    for (std::uint8_t i = 0; f && i < f->nranges; ++i) {
        w += f->ranges[2 * i] - f->ranges[2 * i + 1] + 1;
    }
    return w;
}

std::string render_imm(const isa::Slot& s, std::int64_t val,
                       const isa::Variant* v, const DecodeCtx& ctx) {
    (void)v;
    std::string t = s.type;
    const char* r = t.c_str();
    const isa::Field* f = field_for_slot(ctx, s.name);
    if (std::strcmp(r, "SImm") == 0 || std::strcmp(r, "RSImm") == 0) {
        int width = field_width(f);
        if (width == 0) width = 32;
        std::int64_t scale = f ? (f->scale ? f->scale : 1) : 1;
        std::int64_t off = sign_ext(val, width) * scale;
        if (off < 0) return std::string("-0x") + hex_str(-off).substr(2);
        return hex_str(off);
    }
    if (std::strcmp(r, "F16Imm") == 0) {
        return hex_f32(fp16_to_f32(static_cast<std::uint32_t>(val) & 0xFFFF));
    }
    if (std::strcmp(r, "F32Imm") == 0 || std::strcmp(r, "F64Imm") == 0) {
        int width = std::strcmp(r, "F64Imm") == 0 ? 64 : 32;
        int w = field_width(f);
        if (w != 0) width = w;
        if (width == 16) {
            return hex_f32(fp16_to_f32(static_cast<std::uint32_t>(val) & 0xFFFF));
        }
        if (width == 32) {
            return hex_f32(static_cast<std::uint32_t>(val));
        }
        return "0f" + hex_f64(static_cast<std::uint64_t>(val));
    }
    return hex_str(val);
}

// render a single non-composite operand slot (port of sass_disasm.render_single).
std::optional<std::string> render_single(const isa::Variant* v,
                                         const DecodeCtx& ctx,
                                         const isa::Slot& s,
                                         std::set<std::string>& used) {
    const std::string name = s.name;
    if (used.count(name) || is_sched_slot(name)) return std::nullopt;
    std::string t = s.type;
    auto val = do_slot_value(ctx, name);
    auto [dflt, pprint] = default_of(s);
    std::int64_t not_ = slot_attr_val(ctx, name, "not");

    if (!pprint && dflt && !not_ && (!val || *val == *dflt)) {
        if (t == "SImm" || t == "UImm" || t == "RSImm") {
            if (!val) return std::nullopt;
        } else {
            return std::nullopt;
        }
    }

    std::int64_t neg = slot_attr_val(ctx, name, "negate");
    std::int64_t abs_ = slot_attr_val(ctx, name, "absolute");
    std::string txt;

    const char* r = t.c_str();
    if (std::strcmp(r, "C") == 0) {
        std::int64_t bank = 0, off = 0;
        for (std::uint16_t si = 0; si < v->nslots; ++si) {
            const isa::Slot& s2 = v->slots[si];
            if (s2.modifier || is_sched_slot(std::string(s2.name))) continue;
            const std::string s2n(s2.name);
            const char* t2 = s2.type;
            bool is_imm = std::strcmp(t2, "UImm") == 0 ||
                          std::strcmp(t2, "SImm") == 0;
            if (!is_imm) continue;
            if (s2n.size() > 5 &&
                s2n.compare(s2n.size() - 5, 5, "_bank") == 0) {
                auto bv = do_slot_value(ctx, s2n);
                if (bv) bank = *bv;
            } else if (s2n.size() > 7 &&
                       s2n.compare(s2n.size() - 7, 7, "_offset") == 0) {
                const isa::Field* f = nullptr;
                for (const auto& [ff, fv] : ctx.fields) {
                    std::string frhs(ff->rhs);
                    if (frhs.find(s2n) == std::string::npos) continue;
                    // prefer a field whose own name is the offset (LDCU's
                    // Sa_offset lives in field `Ra_offset`); skip the _bank
                    // field that also names Sa_offset in its RHS.
                    std::string fname(ff->name);
                    if (fname.size() > 7 &&
                        fname.compare(fname.size() - 7, 7, "_offset") == 0) {
                        f = ff;
                        break;
                    }
                    if (!f) f = ff;
                }
                int w = field_width(f);
                if (w == 0) w = 32;
                std::int64_t scale = f ? (f->scale ? f->scale : 1) : 1;
                auto o = do_slot_value(ctx, s2n);
                if (!o && f) {
                    for (const auto& [ff, fv] : ctx.fields) {
                        if (ff == f) { o = static_cast<std::int64_t>(fv); break; }
                    }
                }
                if (o) off = sign_ext(*o, w) * scale;
            }
        }
        char cbuf[48];
        std::snprintf(cbuf, sizeof(cbuf), "c[0x%llx][0x%llx]",
                      static_cast<unsigned long long>(bank),
                      static_cast<unsigned long long>(off));
        txt = cbuf;
        used.insert(name);
        for (std::uint16_t si = 0; si < v->nslots; ++si) {
            const std::string s2n(v->slots[si].name);
            if ((s2n.size() >= 5 &&
                 s2n.compare(s2n.size() - 5, 5, "_bank") == 0) ||
                (s2n.size() >= 7 &&
                 s2n.compare(s2n.size() - 7, 7, "_offset") == 0) ||
                s2n == "Ra" || s2n == "Ra_URb" || s2n == "URa" ||
                s2n == "URb" || s2n == "URc") {
                used.insert(s2n);
            }
        }
    } else if (std::strcmp(r, "Register") == 0 ||
               std::strcmp(r, "NonZeroRegister") == 0) {
        int width = size_of(v, ctx, name);
        bool ureg = is_ureg_slot(v, name);
        txt = reg_text(val.value_or(0), width, ureg);
    } else if (std::strcmp(r, "UniformRegister") == 0 ||
               std::strcmp(r, "NonZeroUniformRegister") == 0) {
        int width = size_of(v, ctx, name);
        txt = reg_text(val.value_or(0), width, true);
    } else if (std::strcmp(r, "ZeroRegister") == 0) {
        txt = "RZ";
    } else if (std::strcmp(r, "ZeroUniformRegister") == 0) {
        txt = "URZ";
    } else if (std::strcmp(r, "Predicate") == 0) {
        txt = (val && *val == 7) ? "PT" : "P" + std::to_string(val.value_or(0));
    } else if (std::strcmp(r, "PR") == 0) {
        // Raw predicate-register-file operand (R2P destination / P2R source).
        // Rendered as the literal token `PR`; there is no per-operand value
        // (no encoding field carries it).  Generic type handling so any
        // variant with a `PR`-typed slot renders it.
        txt = "PR";
    } else if (std::strcmp(r, "UniformPredicate") == 0) {
        txt = (val && *val == 7) ? "UPT" : "UP" + std::to_string(val.value_or(0));
    } else if (std::strcmp(r, "BITSET") == 0) {
        std::string bits;
        std::uint64_t m = static_cast<std::uint64_t>(val.value_or(0));
        for (int i = 0; i < 8; ++i) {
            if (m & (1u << i)) {
                if (!bits.empty()) bits += ",";
                bits += std::to_string(i);
            }
        }
        txt = "{" + bits + "}";
    } else if (std::strcmp(r, "SpecialRegister") == 0) {
        if (auto nm = isa_data().enum_name(t, val.value_or(0))) {
            txt = *nm;
        } else {
            txt = "SR" + std::to_string(val.value_or(0));
        }
    } else if (std::strcmp(r, "BD") == 0) {
        txt = "B" + std::to_string(val.value_or(0));
    } else if (std::strcmp(r, "GSB0ONLY") == 0 ||
               std::strcmp(r, "OPTIONAL_GSB") == 0) {
        if (auto nm = isa_data().enum_name(t, val.value_or(0))) {
            txt = *nm;
        } else {
            txt = "gsb" + std::to_string(val.value_or(0));
        }
    } else if (std::strcmp(r, "Scoreboard") == 0) {
        txt = "gsb" + std::to_string(val.value_or(0));
    } else if (std::strcmp(r, "UImm") == 0 || std::strcmp(r, "SImm") == 0 ||
               std::strcmp(r, "RSImm") == 0 || std::strcmp(r, "F16Imm") == 0 ||
               std::strcmp(r, "F32Imm") == 0 || std::strcmp(r, "F64Imm") == 0) {
        txt = render_imm(s, val.value_or(0), v, ctx);
    } else {
        return std::nullopt;  // unhandled operand type
    }

    if (neg) txt = "-" + txt;
    if (abs_) txt = "|" + txt + "|";
    if (not_) txt = "!" + txt;
    used.insert(name);
    return txt;
}

}  // namespace

// --- slot lookup (used by decoder.cpp) ---
std::optional<std::int64_t> slot_value(const DecodeCtx& ctx,
                                       const std::string& name) {
    return do_slot_value(ctx, name);
}

std::int64_t slot_attr_val(const DecodeCtx& ctx, const std::string& name,
                           const std::string& attr) {
    std::string suffix;
    if (attr == "not") suffix = "_not";
    else if (attr == "negate") suffix = "_negated";
    else if (attr == "absolute") suffix = "_abs";
    else if (attr == "invert") suffix = "_invert";
    else return 0;
    auto it = ctx.sm.find(name + suffix);
    return it == ctx.sm.end() ? 0 : it->second;
}

namespace {

// --- composite operand rendering (port of sass_disasm) ---

bool is_register_type(const std::string& t) {
    return t == "Register" || t == "NonZeroRegister" ||
           t == "ZeroRegister" || t == "UniformRegister" ||
           t == "NonZeroUniformRegister" || t == "ZeroUniformRegister";
}

// sass_disasm._is_memaddr: a register slot followed by a *_offset slot.
bool is_memaddr(const isa::Variant* v, std::size_t i) {
    const isa::Slot& s = v->slots[i];
    if (styp(s.type, "DESC") || styp(s.type, "GMMA")) return false;
    std::size_t j = i + 1;
    while (j < v->nslots && j <= i + 3) {
        const isa::Slot& sj = v->slots[j];
        const std::string sjn(sj.name);
        if (sj.modifier || is_sched_slot(sjn) || sjn == "Pu" ||
            sjn == "Pv" || sjn == "Pp" || sjn == "Pq" ||
            sjn == "Pnz") {
            ++j;
            continue;
        }
        if (styp(sj.type, "SImm")) {
            std::string nm = sj.name;
            return nm.size() > 7 &&
                   nm.compare(nm.size() - 7, 7, "_offset") == 0;
        }
        if (styp(sj.type, "UImm")) {
            std::string nm = sj.name;
            return nm.size() > 7 &&
                   nm.compare(nm.size() - 7, 7, "_offset") == 0;
        }
        if (styp(sj.type, "UniformRegister")) {
            ++j;
            continue;
        }
        if (is_register_type(sj.type) || styp(sj.type, "Predicate")) {
            return false;
        }
        ++j;
    }
    return false;
}

std::string offset_text(std::int64_t off) {
    if (off > 0) return std::string("+0x") + hex_str(off).substr(2);
    if (off < 0) return std::string("-0x") + hex_str(-off).substr(2);
    return "";
}

std::optional<std::int64_t> slot_offset(const DecodeCtx& ctx,
                                        const isa::Slot& off_s) {
    const isa::Field* f = field_for_slot(ctx, off_s.name);
    auto o = do_slot_value(ctx, off_s.name);
    if (!o) return std::nullopt;
    int w = field_width(f);
    if (w == 0) w = 32;
    std::int64_t scale = f ? (f->scale ? f->scale : 1) : 1;
    return sign_ext(*o, w) * scale;
}

// desc[UR][R.64+off] composite.
std::optional<std::string> render_desc(const isa::Variant* v,
                                       const DecodeCtx& ctx, std::size_t i,
                                       std::set<std::string>& used) {
    std::string ureg_txt, rtxt;
    std::int64_t off = 0;
    bool have_off = false;
    const isa::Slot* reg_s = nullptr;
    const isa::Slot* ureg_s = nullptr;
    const isa::Slot* off_s = nullptr;
    for (std::size_t j = i + 1; j < v->nslots; ++j) {
        const isa::Slot& sj = v->slots[j];
        if (sj.modifier || is_sched_slot(sj.name)) continue;
        if ((styp(sj.type, "UniformRegister") ||
             styp(sj.type, "NonZeroUniformRegister")) &&
            ureg_txt.empty()) {
            ureg_s = &sj;
            auto uval = do_slot_value(ctx, sj.name);
            int w = size_of(v, ctx, sj.name, 32);
            ureg_txt = reg_text(uval.value_or(0), w, true);
        } else if (is_register_type(sj.type) && !reg_s) {
            reg_s = &sj;
        } else if (styp(sj.type, "SImm") || styp(sj.type, "UImm")) {
            off_s = &sj;
            if (auto o = slot_offset(ctx, sj)) {
                off = *o;
                have_off = true;
            }
            break;
        }
    }
    if (!reg_s) return std::nullopt;
    int rw = size_of(v, ctx, reg_s->name, 64);
    auto rval = do_slot_value(ctx, reg_s->name);
    rtxt = reg_text(rval.value_or(0), rw, false);
    std::string ur = ureg_txt.empty() ? "" : ureg_txt;
    std::string out = "desc[" + ur + "][" + rtxt;
    if (have_off) out += offset_text(off);
    out += "]";
    used.insert(v->slots[i].name);
    if (ureg_s) used.insert(ureg_s->name);
    if (reg_s) used.insert(reg_s->name);
    if (off_s) used.insert(off_s->name);
    return out;
}

// gdesc[UR] composite (HGMMA/QMMA descriptor).
std::optional<std::string> render_gdesc(const isa::Variant* v,
                                        const DecodeCtx& ctx, std::size_t i,
                                        std::set<std::string>& used) {
    for (std::size_t j = i + 1; j < v->nslots; ++j) {
        const isa::Slot& sj = v->slots[j];
        if (sj.modifier || is_sched_slot(sj.name)) continue;
        if (styp(sj.type, "UniformRegister") || styp(sj.type, "NonZeroUniformRegister")) {
            auto uval = do_slot_value(ctx, sj.name);
            std::string utxt = reg_text(uval.value_or(0), 32, true);
            used.insert(v->slots[i].name);
            used.insert(sj.name);
            return "gdesc[" + utxt + "]";
        }
    }
    return std::nullopt;
}

// [R.64+off] or [R.64+UR+off] memory-address composite.
std::optional<std::string> render_memaddr(const isa::Variant* v,
                                          const DecodeCtx& ctx,
                                          std::size_t i,
                                          std::set<std::string>& used) {
    const isa::Slot& reg_s = v->slots[i];
    const isa::Slot* off_s = nullptr;
    const isa::Slot* ureg_s = nullptr;
    for (std::size_t j = i + 1; j < v->nslots; ++j) {
        const isa::Slot& sj = v->slots[j];
        if (sj.modifier || is_sched_slot(sj.name)) continue;
        if ((styp(sj.type, "UniformRegister") ||
             styp(sj.type, "NonZeroUniformRegister")) && !ureg_s) {
            ureg_s = &sj;
        } else if (styp(sj.type, "SImm") || styp(sj.type, "UImm")) {
            off_s = &sj;
            break;
        }
    }
    auto rval = do_slot_value(ctx, reg_s.name);
    int rw = size_of(v, ctx, reg_s.name, 64);
    bool ureg = styp(reg_s.type, "UniformRegister") ||
                styp(reg_s.type, "NonZeroUniformRegister") ||
                styp(reg_s.type, "ZeroUniformRegister");
    std::string rtxt;
    if (rval && *rval == 255 && rw <= 32) {
        rtxt = ureg ? "URZ" : "RZ";
    } else {
        rtxt = reg_text(rval.value_or(0), rw, ureg);
    }
    std::int64_t off = 0;
    bool have_off = false;
    if (off_s) {
        if (auto o = slot_offset(ctx, *off_s)) {
            off = *o;
            have_off = true;
        }
    }
    used.insert(reg_s.name);
    if (ureg_s) used.insert(ureg_s->name);
    if (off_s) used.insert(off_s->name);
    std::string base = rtxt;
    if (ureg_s) {
        auto uval = do_slot_value(ctx, ureg_s->name);
        int uw = size_of(v, ctx, ureg_s->name, 32);
        std::string utxt = reg_text(uval.value_or(0), uw, true);
        base = rtxt + "+" + utxt;
    }
    std::string out = "[" + base;
    if (have_off) out += offset_text(off);
    out += "]";
    return out;
}

std::vector<std::string> render_ops(const isa::Variant* v,
                                    const DecodeCtx& ctx) {
    std::vector<std::string> ops;
    std::set<std::string> used;
    for (std::size_t i = 0; i < v->nslots; ++i) {
        const isa::Slot& s = v->slots[i];
        const std::string& name = s.name;
        if (s.modifier || name == "Pg" || is_sched_slot(name) ||
            used.count(name)) {
            continue;
        }
        if (styp(s.type, "DESC") || name == "memoryDescriptor") {
            if (auto t = render_desc(v, ctx, i, used)) {
                ops.push_back(*t);
            }
            continue;
        }
        if (styp(s.type, "GMMA") || name == "gdesc") {
            if (auto t = render_gdesc(v, ctx, i, used)) {
                ops.push_back(*t);
            }
            continue;
        }
        if (name == "Ra_URb" || name == "URa" || name == "Ra") {
            if (is_memaddr(v, i)) {
                if (auto t = render_memaddr(v, ctx, i, used)) {
                    ops.push_back(*t);
                }
            } else if (auto t = render_single(v, ctx, s, used)) {
                ops.push_back(*t);
            }
            continue;
        }
        if (auto t = render_single(v, ctx, s, used)) {
            ops.push_back(*t);
        }
    }
    return ops;
}

// 2b-3: the generic operand / slot-value vectors were removed with the typed
// migration; render_instruction no longer collects them.

}  // namespace

namespace {

class ContextFillIn final : public shape::FillIn {
public:
    ContextFillIn(const isa::Variant* v, const DecodeCtx& ctx) : v_(v), ctx_(ctx) {}

    std::int64_t value(const char* slot) const override {
        auto val = do_slot_value(ctx_, slot);
        if (!val) return 0;
        for (std::uint16_t i = 0; i < v_->nslots; ++i) {
            const isa::Slot& s = v_->slots[i];
            if (std::strcmp(s.name, slot) != 0) continue;
            if (std::strcmp(s.type, "SImm") == 0 ||
                std::strcmp(s.type, "RSImm") == 0) {
                const isa::Field* f = field_for_slot(ctx_, slot);
                int width = field_width(f);
                if (width == 0) width = 32;
                return sign_ext(*val, width);
            }
            break;
        }
        return *val;
    }

    std::uint8_t flags(const char* slot) const override {
        return static_cast<std::uint8_t>(
            slot_attr_val(ctx_, slot, "negate") |
            (slot_attr_val(ctx_, slot, "absolute") << 1) |
            (slot_attr_val(ctx_, slot, "not") << 2));
    }

private:
    const isa::Variant* v_;
    const DecodeCtx& ctx_;
};

}  // namespace

std::unique_ptr<DecodedInstruction> render_instruction(
    const isa::Variant* v, Word128 word, const DecodeCtx& ctx) {
    const std::uint32_t vi = static_cast<std::uint32_t>(v - isa::kVariants);
    auto inst = shape::make_by_variant(vi);
    if (!inst) return nullptr;
    inst->word = word;
    inst->mnemonic = v->mnemonic;
    inst->variant_class = v->variant_class;
    inst->pipe = v->pipe;
    inst->shape_variant = vi;

    // 2b-3: no generic vectors are built anymore — the derived Decoded* is
    // the only storage; raw fields are extracted from the word on demand
    // (interpreter field_value).
    auto fv = [&ctx](const char* name, std::int64_t dflt) -> std::int64_t {
        for (const auto& [f, val] : ctx.fields) {
            if (std::strcmp(f->name, name) == 0) {
                return static_cast<std::int64_t>(val);
            }
        }
        return dflt;
    };
    inst->schedule.dst_wr_sb = static_cast<int>(fv("dst_wr_sb", 7));
    inst->schedule.src_rel_sb = static_cast<int>(fv("src_rel_sb", 7));
    inst->schedule.req_bit_set = static_cast<int>(fv("req_bit_set", 0));
    inst->schedule.opex = static_cast<int>(fv("opex", 0));
    inst->schedule.usched = inst->schedule.opex & 0x1F;
    inst->schedule.stall = inst->schedule.usched & 0xF;
    inst->schedule.yield_off = inst->schedule.usched >= 16 ? 1 : 0;
    inst->schedule.batch_t = inst->schedule.opex >> 5;

    // guard predicate
    if (auto pg = do_slot_value(ctx, "Pg")) {
        inst->guard_pred = static_cast<int>(*pg);
    }
    inst->guard_not = slot_attr_val(ctx, "Pg", "not") != 0;

    ContextFillIn in(v, ctx);
    shape::fill_by_variant(vi, in, inst.get());

    // (Disassembly text is NOT rendered here -- it is produced on demand by
    // render_disasm_text so the per-instruction decode path never builds
    // strings only an infrequent consumer (debugger/CLI/trace) reads.)
    return inst;
}

// 2b-3: modifiers are rendered from the decode context on demand, not stored
// on the instruction (the generic `modifiers` vector was removed).
std::string render_modifiers(const isa::Variant* v, const DecodeCtx& ctx) {
    std::string mods;
    for (std::uint16_t si = 0; si < v->nslots; ++si) {
        const isa::Slot& s = v->slots[si];
        if (!s.modifier || is_sched_slot(s.name)) continue;
        auto val = do_slot_value(ctx, s.name);
        auto [dflt, pprint] = default_of(s);
        std::optional<std::string> nm;
        if (val) {
            if (!pprint && dflt && *dflt == *val) continue;
            if (is_addr_size_slot(s.name)) continue;
            nm = isa_data().enum_name(s.type, *val);
        } else {
            // variant-implied modifier: show a real name unless the default
            // already fixes it
            if (dflt && !pprint) continue;
            if (is_addr_size_slot(s.name)) continue;
            nm = isa_data().enum_first(s.type);
        }
        if (nm && !nm->empty()) {
            mods += ".";
            mods += *nm;
        }
    }
    return mods;
}

std::string render_disasm_text(const isa::Variant* v, const DecodeCtx& ctx,
                               const DecodedInstruction& inst, bool full) {
    auto ops = render_ops(v, ctx);
    std::string opstr;
    for (std::size_t i = 0; i < ops.size(); ++i) {
        if (i) opstr += ", ";
        opstr += ops[i];
    }

    std::string mods = render_modifiers(v, ctx);

    std::string out =
        std::string(isa::mnemonic_name(inst.mnemonic)) + mods + " " + opstr;
    if (!full) return out;

    std::string pred;
    if (inst.guard_pred != 7 || inst.guard_not) {
        pred = "@";
        if (inst.guard_not) pred += "!";
        if (inst.guard_pred == 7) pred += "PT";
        else pred += "P" + std::to_string(inst.guard_pred);
        pred += " ";
    }

    // schedule bracket
    char br[64];
    std::string reqs;
    for (int b = 0; b < 6; ++b) {
        if (inst.schedule.req_bit_set & (1 << b)) {
            if (!reqs.empty()) reqs += ",";
            reqs += std::to_string(b);
        }
    }
    int x6 = inst.schedule.opex >> 5;
    // 5th bracket field is the SASS yield flag: 0 = yield (usched >= 16),
    // 1 = no-yield.  yield_off = usched >= 16, so the printed flag is inverted.
    const int yield_flag = inst.schedule.yield_off ? 0 : 1;
    if (x6) {
        std::snprintf(br, sizeof(br), "[%d:%d:{%s}:%d:%d:%d]",
                      inst.schedule.dst_wr_sb, inst.schedule.src_rel_sb,
                      reqs.c_str(), inst.schedule.stall, yield_flag, x6);
    } else {
        std::snprintf(br, sizeof(br), "[%d:%d:{%s}:%d:%d]",
                      inst.schedule.dst_wr_sb, inst.schedule.src_rel_sb,
                      reqs.c_str(), inst.schedule.stall, yield_flag);
    }

    return pred + out + " ; " + br;
}

}  // namespace semu
