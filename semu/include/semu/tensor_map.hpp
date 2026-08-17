#pragma once

// CUtensorMap descriptor parser (SIM_PLAN Phase 9 subset).
//
// The 128-byte tensor-map object consumed by the TMA instructions
// (UTMALDG / UTMASTG / UTMAREDG / UBLKCP) has a private bit layout (the
// driver API documents only the encode calls).  This module reconstructs the
// layout empirically (see notes/sm90/arch/cutensormap.md and
// tools/tma_helper.py) and exposes a pure-CPU parser + tile-address
// expansion.  It is a plain data reader: no CUDA runtime dependency, and the
// parser never feeds back into execution.
//
// Address-expansion model (tiled mode, swizzle NONE): the tile at coordinates
// c[0..rank-1] covers boxDim[i] elements along dim i starting at element
// c[i].  The global byte address of box element (j0..j_{rank-1}) is
//
//     base + sum_i (c[i] + j_i * elementStrides[i]) * byte_stride_i
//
// where byte_stride_i = reconstructed globalStrides[i] for i < rank-1 and
// elementSize for the innermost dimension (the innermost dim is contiguous).
// The shared side is written row-major with the box dims:
//
//     shared_off = sum_i j_i * (prod_{k>i} boxDim[k]) * elementSize
//
// Swizzle modes != 0 permute bytes within 128-byte lines; the exact pattern
// is not fully reverse-engineered (cutensormap.md only documents the w18
// value table), so swizzle != 0 is parsed but its expansion is marked
// approximate (never claimed exact).

#include <array>
#include <cstdint>
#include <optional>
#include <string>

#include <semu/status.hpp>

namespace semu {

enum class TensorMapMode : std::uint8_t {
    kTiled = 0,
    kIm2col = 1,
};

// Parsed descriptor fields (documented in cutensormap.md).  All arrays are
// rank-sized (padding unused).
struct TensorMap {
    TensorMapMode mode = TensorMapMode::kTiled;
    std::uint32_t rank = 0;
    // Hardware element-type code (NOT the CUtensorMapDataType enum).
    std::uint32_t dtype_code = 0;
    std::uint32_t element_bytes = 0;
    std::uint32_t interleave = 0;   // 0 / 1 (16B) / 2 (32B)
    std::uint32_t swizzle = 0;      // 0..6
    std::uint32_t oob_fill = 0;     // float OOB-fill flag
    bool tf32 = false;              // TFLOAT32 flag
    std::uint32_t l2_promotion = 0;
    bool wide = false;              // >= 2^16 total elements / interleaved tile

    std::uint64_t base_addr = 0;    // w0..w1 (64-bit global address)
    std::array<std::uint64_t, 5> global_dims{};   // w8..w12 (element counts)
    std::array<std::uint64_t, 5> strides{};       // reconstructed byte strides
    std::array<std::uint32_t, 5> box_dims{};      // w13/w14 (boxDim[i])
    std::array<std::uint32_t, 5> element_strides{};  // w13 3-bit packed
    std::uint32_t tile_bytes = 0;   // w16 (transfer size)
    std::uint32_t swizzle_info = 0; // w18 raw
    std::uint32_t l2c_atomicity = 0;  // swizzle atomicity (w2 bits[22])
    std::uint32_t cga_swizzle_override = 0;  // w2 bit[23]

    // im2col fields (mode == kIm2col).
    std::uint32_t channels_per_pixel = 0;
    std::uint32_t pixels_per_column = 0;

    bool valid() const { return rank >= 1 && rank <= 5; }
    std::string describe() const;
};

// Parse a 128-byte CUtensorMap blob.  `blob` must point at exactly 128
// bytes.  Returns a structured error on a malformed descriptor (rank 0 or
// >5, bad dtype, reserved flags) — never guesses.
StatusOr<TensorMap> parse_tensor_map(const std::uint8_t* blob);

// The complete per-element access set of one tile.  `global` and `shared`
// lists are parallel: entry k is one element's global byte address and its
// shared byte offset (relative to the tile destination base).  Both are
// needed for the functional copy AND for the profiler's address-expansion
// consistency check (they must agree byte-for-byte).
struct TileAccessSet {
    std::vector<std::uint64_t> global;   // global byte addresses (relative to
                                         // the descriptor base_addr)
    std::vector<std::uint32_t> shared;   // shared byte offsets within the tile
    std::uint32_t element_bytes = 0;
    std::uint64_t total_global_bytes = 0;  // unique global byte span
    bool approximate = false;  // true when a swizzle != 0 pattern was folded
                               // to the linear layout (documented limitation)
};

// Expand a tile at coordinates `coords` (rank entries, innermost last —
// the SASS coordinate block order is {coord[rank-1] .. coord[0]}).  For
// swizzle != 0 the expansion is linear (approximate) unless the tile is
// single-row / fits one 128-byte line.  `coords` must have rank entries.
StatusOr<TileAccessSet> expand_tile(const TensorMap& tm,
                                    const std::uint32_t* coords);

}  // namespace semu
