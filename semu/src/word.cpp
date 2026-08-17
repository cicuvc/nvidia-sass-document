#include <semu/word.hpp>

namespace semu {

std::uint64_t extract_bits(uint64_t lo, uint64_t hi,
                           std::initializer_list<BitRange> ranges) {
    std::uint64_t val = 0;
    for (const auto& [h, l] : ranges) {
        const int w = h - l + 1;
        const std::uint64_t mask = (w == 64) ? ~std::uint64_t{0}
                                             : ((std::uint64_t{1} << w) - 1);
        std::uint64_t part;
        if (l >= 64) {
            part = (hi >> (l - 64)) & mask;
        } else if (h < 64) {
            part = (lo >> l) & mask;
        } else {
            const int lo_w = 64 - l;
            const std::uint64_t lo_mask =
                (lo_w == 64) ? ~std::uint64_t{0} : ((std::uint64_t{1} << lo_w) - 1);
            std::uint64_t hi_part = 0;
            if (w - lo_w > 0 && w - lo_w < 64) {
                hi_part = hi & ((std::uint64_t{1} << (w - lo_w)) - 1);
            } else if (w - lo_w >= 64) {
                hi_part = hi;
            }
            part = (lo >> l) & lo_mask;
            if (lo_w < 64) {
                part |= hi_part << lo_w;
            }
        }
        // w == 64: this range is the whole field (val must be 0); shifting 0
        // by 64 is UB, so assign instead.
        if (w >= 64) {
            val = part;
        } else {
            val = (val << w) | part;
        }
    }
    return val;
}

std::uint64_t extract_bits(uint64_t lo, uint64_t hi, int hi_bit, int lo_bit) {
    return extract_bits(lo, hi, {BitRange{hi_bit, lo_bit}});
}

std::uint16_t opcode_of(uint64_t lo, uint64_t hi) {
    return static_cast<std::uint16_t>(
        extract_bits(lo, hi, {BitRange{91, 91}, BitRange{11, 0}}));
}

std::int64_t sign_extend(std::uint64_t val, int width) {
    if (width >= 64) {
        return static_cast<std::int64_t>(val);
    }
    const std::uint64_t sign = std::uint64_t{1} << (width - 1);
    if (val & sign) {
        val |= (~std::uint64_t{0}) << width;
    }
    return static_cast<std::int64_t>(val);
}

}  // namespace semu
