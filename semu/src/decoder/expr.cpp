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

const isa::TableDef* IsaData::table(std::string_view name) const {
    auto it = tables.find(std::string(name));
    return it == tables.end() ? nullptr : it->second;
}

}  // namespace semu::decoder