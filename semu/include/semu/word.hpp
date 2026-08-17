#pragma once

#include <cstdint>
#include <utility>
#include <vector>

// Raw 128-bit instruction words and bit-level helpers shared by the decoder,
// debugger, profiler and fault reporting.  CPU-interpreter facing: the 128-bit
// word is split into lo64 (bits [63:0]) and hi64 (bits [127:64]).

namespace semu {

struct Word128 {
    uint64_t lo = 0;   // bits [63:0]
    uint64_t hi = 0;   // bits [127:64]
};

// A field is a (hi, lo) contiguous bit range, hi >= lo.  Targets are listed
// MSB-first; for a field spanning several disjoint ranges each range holds
// *width* bits ending at bit hi (i.e. [hi-w+1, hi]).
using BitRange = std::pair<int, int>;

// Extract a value from a 128-bit word.  `ranges` are MSB-first bit ranges;
// the extracted value is the concatenation (top range = most significant
// bits).  Handles ranges crossing the lo/hi boundary.
std::uint64_t extract_bits(uint64_t lo, uint64_t hi,
                           std::initializer_list<BitRange> ranges);

// Convenience for a single contiguous range.
std::uint64_t extract_bits(uint64_t lo, uint64_t hi, int hi_bit, int lo_bit);

// Extract the 13-bit sm120 opcode = {bit[91], bits[11:0]}.
std::uint16_t opcode_of(uint64_t lo, uint64_t hi);

// Sign-extend `val` (interpreted as `width` bits) to int64.
std::int64_t sign_extend(uint64_t val, int width);

}  // namespace semu
