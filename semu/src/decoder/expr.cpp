#include "expr.hpp"

#include <algorithm>
#include <cctype>
#include <cstdlib>

#include "isa_data.hpp"

namespace semu::decoder {

std::vector<std::string> split_row_args(std::string_view in) {
    std::vector<std::string> out;
    std::size_t start = 0;
    for (std::size_t i = 0; i <= in.size(); ++i) {
        if (i == in.size() || in[i] == ',') {
            out.emplace_back(in.substr(start, i - start));
            start = i + 1;
        }
    }
    return out;
}

// ---------------------------------------------------------------------------
// IsaData lookups
// ---------------------------------------------------------------------------

std::optional<std::int64_t> IsaData::enum_value(std::string_view type,
                                                std::string_view name) const {
    auto it = enums.find(std::string(type));
    if (it == enums.end()) return std::nullopt;
    const isa::EnumDef* e = it->second;
    for (std::uint32_t i = 0; i < e->n; ++i) {
        std::string_view nm = e->entries[i].name;
        if (nm == name || (nm.size() > 1 && nm[0] == '_' &&
                           nm.substr(1) == name)) {
            return e->entries[i].value;
        }
        if (name.size() > 1 && name[0] == '_' &&
            nm == name.substr(1)) {
            return e->entries[i].value;
        }
    }
    return std::nullopt;
}

static bool is_fp8_name(std::string_view name) {
    // E8M7/E8M10/E6M9 etc. share values with BF16/TF32/F16 names.
    if (name.size() >= 4 && name[0] == 'E' &&
        std::isdigit(static_cast<unsigned char>(name[1])) &&
        name[2] == 'M' && std::isdigit(static_cast<unsigned char>(name[3]))) {
        return true;
    }
    return false;
}

std::optional<std::string> IsaData::enum_name(std::string_view type,
                                              std::int64_t value) const {
    auto it = enums.find(std::string(type));
    if (it == enums.end()) return std::nullopt;
    const isa::EnumDef* e = it->second;
    // Pass 1: skip INVALID* and no-prefixed and fp8-format names.
    for (std::uint32_t i = 0; i < e->n; ++i) {
        std::string_view nm = e->entries[i].name;
        if (e->entries[i].value != value) continue;
        std::string n(nm);
        if (n.rfind("INVALID", 0) == 0) continue;
        if (n.rfind("no", 0) == 0) continue;
        if (is_fp8_name(nm)) continue;
        return n;
    }
    // Pass 2: any value match.
    for (std::uint32_t i = 0; i < e->n; ++i) {
        if (e->entries[i].value == value) {
            return std::string(e->entries[i].name);
        }
    }
    return std::nullopt;
}

std::optional<std::string> IsaData::enum_first(std::string_view type) const {
    auto it = enums.find(std::string(type));
    if (it == enums.end()) return std::nullopt;
    const isa::EnumDef* e = it->second;
    for (std::uint32_t i = 0; i < e->n; ++i) {
        std::string n(e->entries[i].name);
        if (n.rfind("INVALID", 0) == 0) continue;
        if (n.rfind("no", 0) == 0) continue;
        if (is_fp8_name(n)) continue;
        return n;
    }
    for (std::uint32_t i = 0; i < e->n; ++i) {
        std::string n(e->entries[i].name);
        if (n.rfind("INVALID", 0) == 0) continue;
        if (n.rfind("no", 0) == 0) continue;
        return n;
    }
    return std::nullopt;
}

bool IsaData::enum_has_value(std::string_view type, std::int64_t value) const {
    auto it = enums.find(std::string(type));
    if (it == enums.end()) return false;
    const isa::EnumDef* e = it->second;
    for (std::uint32_t i = 0; i < e->n; ++i) {
        if (e->entries[i].value == value) return true;
    }
    return false;
}

std::optional<std::int64_t> IsaData::parameter(std::string_view name) const {
    auto it = parameters.find(std::string(name));
    if (it == parameters.end()) return std::nullopt;
    return it->second;
}

std::optional<std::int64_t> IsaData::constant(std::string_view name) const {
    auto it = constants.find(std::string(name));
    if (it == constants.end()) return std::nullopt;
    return it->second;
}

const isa::TableDef* IsaData::table(std::string_view name) const {
    auto it = tables.find(std::string(name));
    return it == tables.end() ? nullptr : it->second;
}

// ---------------------------------------------------------------------------
// Tokenizer (mirrors sass_cond.tokenize)
// ---------------------------------------------------------------------------

static bool is_ident_start(char c) {
    return std::isalpha(static_cast<unsigned char>(c)) || c == '_';
}
static bool is_ident_char(char c) {
    return std::isalnum(static_cast<unsigned char>(c)) || c == '_';
}

void ExprEvaluator::tokenize(std::string_view pred) {
    toks_.clear();
    had_unknown_char_ = false;
    const std::size_t n = pred.size();
    std::size_t i = 0;
    while (i < n) {
        char c = pred[i];
        if (std::isspace(static_cast<unsigned char>(c))) {
            ++i;
            continue;
        }
        if (c == '`') {  // enum literal
            std::size_t j = i + 1;
            while (j < n && is_ident_char(pred[j])) ++j;
            std::string typ(pred.substr(i + 1, j - i - 1));
            if (j < n && pred[j] == '@') ++j;
            std::string val;
            if (j < n && pred[j] == '"') {
                ++j;
                std::size_t start = j;
                while (j < n && pred[j] != '"') ++j;
                val = std::string(pred.substr(start, j - start));
                if (j < n) ++j;
            } else {
                std::size_t start = j;
                while (j < n && (is_ident_char(pred[j]) || pred[j] == '.')) ++j;
                val = std::string(pred.substr(start, j - start));
            }
            toks_.emplace_back(0, typ + "@" + val);
            i = j;
            continue;
        }
        if (i + 1 < n) {
            std::string two = std::string(pred.substr(i, 2));
            if (two == "==" || two == "!=" || two == "<=" || two == ">=" ||
                two == "&&" || two == "||" || two == "->" || two == "<<" ||
                two == ">>") {
                toks_.emplace_back(1, two);
                i += 2;
                continue;
            }
        }
        if (c == '%' && i + 1 < n &&
            (is_ident_char(pred[i + 1]))) {
            std::size_t j = i + 1;
            while (j < n && is_ident_char(pred[j])) ++j;
            toks_.emplace_back(2, std::string(pred.substr(i + 1, j - i - 1)));
            i = j;
            continue;
        }
        if (c == '$' && i + 1 < n && is_ident_char(pred[i + 1])) {
            std::size_t j = i + 1;
            while (j < n && is_ident_char(pred[j])) ++j;
            toks_.emplace_back(3, std::string(pred.substr(i + 1, j - i - 1)));
            i = j;
            continue;
        }
        if (std::string("()+-*%<>!@,&?:;").find(c) != std::string::npos) {
            toks_.emplace_back(1, std::string(1, c));
            ++i;
            continue;
        }
        if (std::isdigit(static_cast<unsigned char>(c)) ||
            (c == '-' && i + 1 < n &&
             std::isdigit(static_cast<unsigned char>(pred[i + 1])))) {
            std::size_t j = i;
            if (pred[i] == '-') ++j;
            if (j + 1 < n && pred[j] == '0' &&
                (pred[j + 1] == 'x' || pred[j + 1] == 'X')) {
                j += 2;
                while (j < n && std::isxdigit(static_cast<unsigned char>(pred[j]))) ++j;
            } else {
                while (j < n && std::isdigit(static_cast<unsigned char>(pred[j]))) ++j;
            }
            toks_.emplace_back(4, std::string(pred.substr(i, j - i)));
            i = j;
            continue;
        }
        if (is_ident_start(c)) {
            std::size_t j = i + 1;
            while (j < n && is_ident_char(pred[j])) ++j;
            toks_.emplace_back(5, std::string(pred.substr(i, j - i)));
            i = j;
            continue;
        }
        // unknown character: mark the expression as not fully parseable
        // (GAP-04) instead of silently skipping it.
        had_unknown_char_ = true;
        ++i;  // skip unknown char
    }
}

// token kinds: 0=ENUM, 1=OP, 2=PARAM, 3=CONST, 4=NUM, 5=IDENT
#define TK_ENUM 0
#define TK_OP 1
#define TK_PARAM 2
#define TK_CONST 3
#define TK_NUM 4
#define TK_IDENT 5

static bool op_is(const std::pair<int, std::string>& t, const char* op) {
    return t.first == TK_OP && t.second == op;
}

bool ExprEvaluator::eval_bool(std::string_view predicate) {
    tokenize(predicate);
    pos_ = 0;
    try {
        auto v = eval();
        return v && *v != 0;
    } catch (...) {
        return true;  // conservative: parse failures never reject
    }
}

std::optional<bool> ExprEvaluator::eval_bool_tristate(
    std::string_view predicate) {
    tokenize(predicate);
    pos_ = 0;
    if (had_unknown_char_) {
        return std::nullopt;  // tokenizer saw an unclassifiable character
    }
    try {
        auto v = eval();
        if (!v) {
            return std::nullopt;  // unresolvable reference / grammar gap
        }
        if (pos_ != toks_.size()) {
            return std::nullopt;  // tokens left unconsumed: grammar gap
        }
        return *v != 0;
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<std::int64_t> ExprEvaluator::eval_int(std::string_view predicate) {
    tokenize(predicate);
    pos_ = 0;
    try {
        return eval();
    } catch (...) {
        return std::nullopt;
    }
}

std::int64_t ExprEvaluator::slot(std::string_view name) const {
    if (!slots_) return 0;
    auto it = slots_->find(std::string(name));
    return it == slots_->end() ? 0 : it->second;
}

std::int64_t ExprEvaluator::slot_attr(std::string_view slot_name,
                                      std::string_view attr) const {
    std::string suffix;
    if (attr == "not") suffix = "_not";
    else if (attr == "invert") suffix = "_invert";
    else if (attr == "negate") suffix = "_negated";
    else if (attr == "absolute") suffix = "_abs";
    else suffix = std::string(attr);
    return slot(std::string(slot_name) + suffix) ? 1 : 0;
}

std::optional<std::int64_t> ExprEvaluator::eval() {
    auto left = or_expr();
    if (!left) return std::nullopt;
    if (pos_ < toks_.size() && op_is(toks_[pos_], "?")) {
        ++pos_;
        auto then = eval();
        if (!then) return std::nullopt;
        if (pos_ >= toks_.size() || !op_is(toks_[pos_], ":")) return std::nullopt;
        ++pos_;
        auto els = eval();
        if (!els) return std::nullopt;
        return *left ? *then : *els;
    }
    if (pos_ < toks_.size() && op_is(toks_[pos_], "->")) {
        ++pos_;
        auto right = or_expr();
        if (!right) return std::nullopt;
        return (!*left || *right) ? 1 : 0;
    }
    return left;
}

std::optional<std::int64_t> ExprEvaluator::or_expr() {
    auto v = and_expr();
    if (!v) return std::nullopt;
    while (pos_ < toks_.size() && op_is(toks_[pos_], "||")) {
        ++pos_;
        auto r = and_expr();
        if (!r) return std::nullopt;
        v = (*v || *r) ? 1 : 0;
    }
    return v;
}

std::optional<std::int64_t> ExprEvaluator::and_expr() {
    auto v = bitand_expr();
    if (!v) return std::nullopt;
    while (pos_ < toks_.size() && op_is(toks_[pos_], "&&")) {
        ++pos_;
        auto r = bitand_expr();
        if (!r) return std::nullopt;
        v = (*v && *r) ? 1 : 0;
    }
    return v;
}

std::optional<std::int64_t> ExprEvaluator::bitand_expr() {
    auto v = cmp();
    if (!v) return std::nullopt;
    while (pos_ < toks_.size() && op_is(toks_[pos_], "&")) {
        ++pos_;
        auto r = cmp();
        if (!r) return std::nullopt;
        v = *v & *r;
    }
    return v;
}

std::optional<std::int64_t> ExprEvaluator::cmp() {
    auto left = shift();
    if (!left) return std::nullopt;
    if (pos_ < toks_.size() && toks_[pos_].first == TK_OP) {
        const std::string& op = toks_[pos_].second;
        if (op == "==" || op == "!=" || op == "<=" || op == ">=" || op == "<" ||
            op == ">") {
            ++pos_;
            auto right = shift();
            if (!right) return std::nullopt;
            if (op == "==") return *left == *right ? 1 : 0;
            if (op == "!=") return *left != *right ? 1 : 0;
            if (op == "<=") return *left <= *right ? 1 : 0;
            if (op == ">=") return *left >= *right ? 1 : 0;
            if (op == "<") return *left < *right ? 1 : 0;
            return *left > *right ? 1 : 0;
        }
    }
    return left;
}

std::optional<std::int64_t> ExprEvaluator::shift() {
    auto v = add();
    if (!v) return std::nullopt;
    while (pos_ < toks_.size() && toks_[pos_].first == TK_OP &&
           (toks_[pos_].second == "<<" || toks_[pos_].second == ">>")) {
        std::string op = toks_[pos_].second;
        ++pos_;
        auto r = add();
        if (!r) return std::nullopt;
        v = op == "<<" ? (*v << *r) : (*v >> *r);
    }
    return v;
}

std::optional<std::int64_t> ExprEvaluator::add() {
    auto v = mul();
    if (!v) return std::nullopt;
    while (pos_ < toks_.size() && toks_[pos_].first == TK_OP &&
           (toks_[pos_].second == "+" || toks_[pos_].second == "-")) {
        std::string op = toks_[pos_].second;
        ++pos_;
        auto r = mul();
        if (!r) return std::nullopt;
        v = op == "+" ? *v + *r : *v - *r;
    }
    return v;
}

std::optional<std::int64_t> ExprEvaluator::mul() {
    auto v = unary();
    if (!v) return std::nullopt;
    while (pos_ < toks_.size() && toks_[pos_].first == TK_OP &&
           (toks_[pos_].second == "%" || toks_[pos_].second == "*" ||
            toks_[pos_].second == "/")) {
        std::string op = toks_[pos_].second;
        ++pos_;
        auto r = unary();
        if (!r) return std::nullopt;
        if (op == "*") {
            v = *v * *r;
        } else if (*r == 0) {
            v = 0;
        } else {
            v = op == "%" ? *v % *r : *v / *r;
        }
    }
    return v;
}

std::optional<std::int64_t> ExprEvaluator::unary() {
    if (pos_ >= toks_.size()) return std::nullopt;
    if (op_is(toks_[pos_], "!")) {
        ++pos_;
        auto v = unary();
        if (!v) return std::nullopt;
        return *v ? 0 : 1;
    }
    if (op_is(toks_[pos_], "-")) {
        ++pos_;
        auto v = unary();
        if (!v) return std::nullopt;
        return -*v;
    }
    if (op_is(toks_[pos_], "(")) {
        ++pos_;
        auto v = eval();
        if (!v) return std::nullopt;
        if (pos_ < toks_.size() && op_is(toks_[pos_], ")")) ++pos_;
        return v;
    }
    return atom();
}

std::optional<std::int64_t> ExprEvaluator::atom() {
    if (pos_ >= toks_.size()) return 0;
    auto [kind, text] = toks_[pos_];
    if (kind == TK_IDENT && text == "DEFINED") {
        return defined();
    }
    if (kind == TK_IDENT && pos_ + 1 < toks_.size() &&
        op_is(toks_[pos_ + 1], "@")) {
        std::string slot_name = text;
        pos_ += 2;
        std::string attr;
        if (pos_ < toks_.size() && toks_[pos_].first == TK_OP) {
            attr = toks_[pos_].second;
            ++pos_;
        } else if (pos_ < toks_.size()) {
            attr = toks_[pos_].second;
            ++pos_;
        }
        return slot_attr(slot_name, attr);
    }
    ++pos_;
    if (kind == TK_IDENT) {
        // Bare table name used as a value: `TABLES_x(arg,...)` evaluates the
        // table function and yields the matching row's `out` (GAP-04 grammar
        // gap found in ATOMG SAFEADD conditions).
        if (pos_ < toks_.size() && op_is(toks_[pos_], "(") &&
            data_.table(text)) {
            std::string table_name = text;
            ++pos_;  // consume (
            std::vector<std::string> args;
            while (true) {
                args.push_back(resolve_arg());
                if (pos_ < toks_.size() && op_is(toks_[pos_], ",")) {
                    ++pos_;
                    continue;
                }
                break;
            }
            if (pos_ < toks_.size() && op_is(toks_[pos_], ")")) ++pos_;
            const isa::TableDef* t = data_.table(table_name);
            for (std::uint32_t i = 0; i < t->n; ++i) {
                if (split_row_args(t->in[i]) == args) {
                    char* endp = nullptr;
                    std::int64_t ov = std::strtoll(t->out[i], &endp, 0);
                    if (endp && *endp == '\0') return ov;
                    break;
                }
            }
            return 0;  // no row: table function value is 0
        }
        return slot(text);
    }
    if (kind == TK_PARAM) return data_.parameter(text).value_or(0);
    if (kind == TK_CONST) return data_.constant(text).value_or(0);
    if (kind == TK_ENUM) {
        std::size_t at = text.find('@');
        if (at == std::string::npos) return 0;
        std::string type = text.substr(0, at);
        std::string value = text.substr(at + 1);
        if (!value.empty() && value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.size() - 2);
        }
        if (auto v = data_.enum_value(type, value)) return *v;
        // AInteger aliases: '_64' vs '64'
        if (value.size() > 1 && value[0] == '_' &&
            data_.enum_value(type, value.substr(1))) {
            return *data_.enum_value(type, value.substr(1));
        }
        if (!value.empty() && value[0] != '_' &&
            data_.enum_value(type, "_" + value)) {
            return *data_.enum_value(type, "_" + value);
        }
        char* end = nullptr;
        std::int64_t parsed = std::strtoll(value.c_str(), &end, 0);
        if (end && *end == '\0') return parsed;
        return 0;
    }
    if (kind == TK_NUM) {
        return static_cast<std::int64_t>(std::strtoll(text.c_str(), nullptr, 0));
    }
    return 0;
}

std::optional<std::int64_t> ExprEvaluator::defined() {
    ++pos_;  // consume DEFINED
    if (pos_ >= toks_.size() || toks_[pos_].first != TK_IDENT) return 0;
    std::string table_name = toks_[pos_].second;
    ++pos_;
    if (pos_ < toks_.size() && op_is(toks_[pos_], "(")) ++pos_;
    std::vector<std::string> args;
    while (true) {
        args.push_back(resolve_arg());
        if (pos_ < toks_.size() && op_is(toks_[pos_], ",")) {
            ++pos_;
            continue;
        }
        break;
    }
    if (pos_ < toks_.size() && op_is(toks_[pos_], ")")) ++pos_;
    const isa::TableDef* t = data_.table(table_name);
    if (!t) return 0;
    for (std::uint32_t i = 0; i < t->n; ++i) {
        if (split_row_args(t->in[i]) == args) return 1;
    }
    return 0;
}

std::string ExprEvaluator::resolve_arg() {
    if (pos_ >= toks_.size()) return "0";
    auto [kind, text] = toks_[pos_];
    if (kind == TK_PARAM) {
        ++pos_;
        return std::to_string(data_.parameter(text).value_or(0));
    }
    if (kind == TK_CONST) {
        ++pos_;
        return std::to_string(data_.constant(text).value_or(0));
    }
    if (kind == TK_ENUM) {
        ++pos_;
        std::size_t at = text.find('@');
        if (at == std::string::npos) return "0";
        std::string type = text.substr(0, at);
        std::string value = text.substr(at + 1);
        if (!value.empty() && value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.size() - 2);
        }
        if (auto v = data_.enum_value(type, value)) return std::to_string(*v);
        return "0";
    }
    if (kind == TK_NUM) {
        ++pos_;
        return std::to_string(std::strtoll(text.c_str(), nullptr, 0));
    }
    if (kind == TK_IDENT) {
        ++pos_;
        if (pos_ < toks_.size() && op_is(toks_[pos_], "@")) {
            ++pos_;
            std::string attr;
            if (pos_ < toks_.size()) attr = toks_[pos_].second;
            ++pos_;
            return std::to_string(slot_attr(text, attr));
        }
        return std::to_string(slot(text));
    }
    ++pos_;
    return "0";
}

}  // namespace semu::decoder
