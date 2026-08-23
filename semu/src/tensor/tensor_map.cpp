// Tensor-map descriptor parsing + tile address expansion (SIM_PLAN Phase 9
// subset).  Pure CPU; no CUDA dependency.  Layout documented in
// notes/sm90/arch/cutensormap.md, cross-checked against tools/tma_helper.py
// (the bit-accurate forward constructor verified byte-for-byte against the
// driver).

#include <semu/tensor/tensor_map.hpp>

#include <cstring>
#include <sstream>

namespace semu {

namespace {

std::uint32_t le32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) |
           (static_cast<std::uint32_t>(p[1]) << 8) |
           (static_cast<std::uint32_t>(p[2]) << 16) |
           (static_cast<std::uint32_t>(p[3]) << 24);
}
std::uint64_t le64(const std::uint8_t* p) {
    return static_cast<std::uint64_t>(le32(p)) |
           (static_cast<std::uint64_t>(le32(p + 4)) << 32);
}

// Element-type hardware code -> element size in bytes (tma_helper ELEM_BYTES).
std::uint32_t element_bytes_for_code(std::uint32_t code) {
    switch (code) {
        case 0: return 1;    // UINT8
        case 1: return 2;    // UINT16
        case 2: return 4;    // UINT32
        case 3: return 4;    // INT32
        case 4: return 8;    // UINT64
        case 5: return 8;    // INT64
        case 6: return 2;    // FLOAT16
        case 7: return 4;    // FLOAT32 / TFLOAT32
        case 8: return 4;    // FLOAT32_FTZ / TFLOAT32_FTZ
        case 9: return 8;    // FLOAT64
        case 10: return 2;   // BFLOAT16
        case 11: case 12: case 13: return 0;  // packed U4/U6: not byte-addressed
        default: return 0;
    }
}

}  // namespace

std::string TensorMap::describe() const {
    std::ostringstream os;
    os << (mode == TensorMapMode::kTiled ? "tiled" : "im2col")
       << " rank=" << rank << " dtype=" << dtype_code
       << " elem=" << element_bytes << " base=0x" << std::hex << base_addr
       << std::dec << " swizzle=" << swizzle
       << " interleave=" << interleave
       << " tile_bytes=" << tile_bytes << " wide=" << wide;
    os << " dims=[";
    for (std::uint32_t i = 0; i < rank; ++i)
        os << (i ? "," : "") << global_dims[i];
    os << "] box=[";
    for (std::uint32_t i = 0; i < rank; ++i)
        os << (i ? "," : "") << box_dims[i];
    os << "] strides=[";
    for (std::uint32_t i = 0; i + 1 < rank; ++i)
        os << (i ? "," : "") << strides[i];
    os << "]";
    return os.str();
}

StatusOr<TensorMap> parse_tensor_map(const std::uint8_t* blob) {
    if (!blob) {
        return StatusOr<TensorMap>::failure(Error(
            ErrorCode::kInvalidArgument, "null tensor-map blob"));
    }
    TensorMap tm;
    tm.base_addr = le64(blob + 0);
    const std::uint32_t w2 = le32(blob + 8);
    const std::uint32_t w7 = le32(blob + 28);
    const std::uint32_t w13 = le32(blob + 52);
    const std::uint32_t w14 = le32(blob + 56);
    const std::uint32_t w16 = le32(blob + 64);
    const std::uint32_t w18 = le32(blob + 72);

    tm.mode = (w2 & 0x1) ? TensorMapMode::kIm2col : TensorMapMode::kTiled;
    tm.rank = ((w2 >> 4) & 0x7) + 1;
    tm.dtype_code = (w2 >> 7) & 0xF;
    tm.element_bytes = element_bytes_for_code(tm.dtype_code);
    tm.interleave = (w2 >> 11) & 0x3;
    tm.swizzle = ((w2 >> 13) & 0x3) + (((w2 >> 19) & 0x3) << 1);
    tm.oob_fill = (w2 >> 15) & 0x1;
    tm.tf32 = (w2 >> 16) & 0x1;
    tm.l2_promotion = (w2 >> 17) & 0x3;
    tm.wide = (w2 >> 21) & 0x1;
    tm.l2c_atomicity = (w2 >> 22) & 0x1;
    tm.cga_swizzle_override = (w2 >> 23) & 0x1;

    if (!tm.valid()) {
        return StatusOr<TensorMap>::failure(Error(
            ErrorCode::kInvalidArgument,
            "tensor-map rank " + std::to_string(tm.rank) + " out of 1..5"));
    }
    if (tm.element_bytes == 0 && tm.dtype_code >= 11 && tm.dtype_code <= 13) {
        // Packed U4/U6: tile size in bytes is not element-addressed; keep the
        // tile_bytes from the descriptor and mark element_bytes 0 (the copy
        // path must not use per-element addressing).
    } else if (tm.element_bytes == 0) {
        return StatusOr<TensorMap>::failure(Error(
            ErrorCode::kInvalidArgument,
            "tensor-map dtype code " + std::to_string(tm.dtype_code) +
                " is reserved/unknown"));
    }

    // Global dims (w8..w12, rank entries).
    for (std::uint32_t i = 0; i < tm.rank; ++i) {
        tm.global_dims[i] = le32(blob + 32 + 4 * i) + 1;
    }
    // Global strides: (w3..w6) low 32 bits of stride/16, w7 high nibbles.
    for (std::uint32_t i = 0; i + 1 < tm.rank; ++i) {
        const std::uint32_t low = le32(blob + 12 + 4 * i);
        const std::uint32_t hi = (w7 >> (4 * i)) & 0xF;
        tm.strides[i] = (static_cast<std::uint64_t>(hi) << 36 |
                         static_cast<std::uint64_t>(low)) *
                        16;
    }

    // Element strides: 3-bit packed in w13 [15:0].
    for (std::uint32_t i = 0; i < tm.rank; ++i) {
        tm.element_strides[i] = ((w13 >> (3 * i)) & 0x7) + 1;
    }
    // Swizzle info raw word (w18).
    tm.swizzle_info = w18;

    if (tm.mode == TensorMapMode::kTiled) {
        tm.box_dims[0] = ((w13 >> 24) & 0xFF) + 1;
        for (std::uint32_t i = 1; i < tm.rank; ++i) {
            tm.box_dims[i] = ((w14 >> (8 * (i - 1))) & 0xFF) + 1;
        }
        tm.tile_bytes = w16;
    } else {
        // im2col: w13 byte3 = cpp-1; w15 = ppc-1; w16 = tile bytes.
        tm.channels_per_pixel = ((w13 >> 24) & 0xFF) + 1;
        tm.pixels_per_column = le32(blob + 60) + 1;
        tm.tile_bytes = w16;
        // im2col box is (cpp x ppc x rank-2 pixel box); the address expansion
        // is decode-only for now (see header).
        tm.box_dims[0] = tm.channels_per_pixel;
    }
    return StatusOr<TensorMap>::success(std::move(tm));
}

StatusOr<TileAccessSet> expand_tile(const TensorMap& tm,
                                    const std::uint32_t* coords) {
    if (!tm.valid() || !coords) {
        return StatusOr<TileAccessSet>::failure(Error(
            ErrorCode::kInvalidArgument, "invalid tensor map for expansion"));
    }
    if (tm.mode == TensorMapMode::kIm2col) {
        // im2col tile expansion is not reverse-engineered; decode-only.
        return StatusOr<TileAccessSet>::failure(Error(
            ErrorCode::kNotSupported,
            "im2col tensor-map tile expansion is decode-only"));
    }
    if (tm.element_bytes == 0) {
        return StatusOr<TileAccessSet>::failure(Error(
            ErrorCode::kNotSupported,
            "packed U4/U6 tensor maps are decode-only (no per-element "
            "addressing)"));
    }
    TileAccessSet out;
    out.element_bytes = tm.element_bytes;
    // Swizzle != 0: the per-element global/shared layout inside a 128-byte
    // line is not fully reverse-engineered.  Fold to the linear layout and
    // mark the access set approximate (documented limitation).
    out.approximate = tm.swizzle != 0;

    std::uint64_t total_elements = 1;
    std::array<std::uint64_t, 5> box_volume{};
    for (std::uint32_t i = tm.rank; i-- > 0;) {
        box_volume[i] = total_elements;
        total_elements *= tm.box_dims[i];
    }
    if (total_elements == 0 || total_elements > (1u << 24)) {
        return StatusOr<TileAccessSet>::failure(Error(
            ErrorCode::kInvalidArgument, "tile volume out of range"));
    }

    // Iterative walk over box element indices; innermost dim varies fastest.
    std::array<std::uint64_t, 5> idx{};
    // Compute the global byte stride for each dim (innermost = elementBytes).
    std::array<std::uint64_t, 5> gstride{};
    for (std::uint32_t i = 0; i + 1 < tm.rank; ++i) {
        gstride[i] = tm.strides[i] * tm.element_strides[i];
    }
    gstride[tm.rank - 1] =
        static_cast<std::uint64_t>(tm.element_bytes) *
        tm.element_strides[tm.rank - 1];

    // Iterative odometer (rank up to 5).
    while (true) {
        std::uint64_t gbyte = tm.base_addr;
        std::uint32_t sbyte = 0;
        for (std::uint32_t i = 0; i < tm.rank; ++i) {
            const std::uint64_t elem =
                static_cast<std::uint64_t>(coords[i]) + idx[i];
            gbyte += elem * gstride[i];
            sbyte += static_cast<std::uint32_t>(idx[i] * box_volume[i]) *
                     tm.element_bytes;
        }
        out.global.push_back(gbyte);
        out.shared.push_back(sbyte);

        // Advance the odometer.
        std::uint32_t d = tm.rank;
        while (d-- > 0) {
            if (++idx[d] < tm.box_dims[d]) break;
            idx[d] = 0;
            if (d == 0) goto done;
        }
    }
done:
    out.total_global_bytes = total_elements * tm.element_bytes;
    return StatusOr<TileAccessSet>::success(std::move(out));
}

}  // namespace semu
