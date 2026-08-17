// L0 unit tests: tensor-map descriptor parsing + tile expansion (Phase 9).
#include <semu/tensor_map.hpp>

#include <cstdint>
#include <vector>

#include "test_framework.hpp"

using namespace semu;

namespace {

// Build a tiled-mode descriptor blob following the cutensormap layout
// (tools/tma_helper.py semantics).  Returns 128 bytes.
std::vector<std::uint8_t> build_tiled(
    std::uint32_t rank, std::uint32_t dtype, std::uint64_t base,
    const std::vector<std::uint64_t>& dims,
    const std::vector<std::uint64_t>& strides,
    const std::vector<std::uint32_t>& box,
    const std::vector<std::uint32_t>& elem,
    std::uint32_t swizzle = 0, std::uint32_t interleave = 0) {
    std::vector<std::uint8_t> b(128, 0);
    auto w32 = [&b](std::size_t off, std::uint32_t v) {
        b[off] = v & 0xff; b[off + 1] = (v >> 8) & 0xff;
        b[off + 2] = (v >> 16) & 0xff; b[off + 3] = (v >> 24) & 0xff;
    };
    w32(0, static_cast<std::uint32_t>(base & 0xffffffffu));      // w0
    w32(4, static_cast<std::uint32_t>(base >> 32));              // w1
    std::uint32_t w2 = (rank - 1) << 4;
    w2 |= (dtype << 7);
    w2 |= (interleave & 3) << 11;
    w2 |= (std::min(swizzle, 3u)) << 13;
    w2 |= (std::max(swizzle, 3u) - 3) << 19;
    w32(8, w2);  // w2 at byte offset 8.
    for (std::uint32_t i = 0; i + 1 < rank; ++i) {
        const std::uint64_t sd = strides[i];
        const std::uint32_t low =
            static_cast<std::uint32_t>((sd >> 4) & 0xffffffffu);
        w32(12 + 4 * i, low);  // w3+i: low 32 of stride/16
        b[28] |= static_cast<std::uint8_t>(((sd >> 36) & 0xF) << (4 * i));
    }
    for (std::uint32_t i = 0; i < rank; ++i)
        w32(32 + 4 * i, static_cast<std::uint32_t>(dims[i] - 1));
    std::uint32_t w13 = 0;
    for (std::uint32_t i = 0; i < rank; ++i)
        w13 |= ((elem[i] - 1) & 7) << (3 * i);
    w13 |= (box[0] - 1) << 24;
    w32(52, w13);
    for (std::uint32_t i = 1; i < rank; ++i)
        b[56 + i - 1] = static_cast<std::uint8_t>(box[i] - 1);
    return b;
}

}  // namespace

TEST(tensor_map_parse_tiled_2d) {
    auto blob = build_tiled(2, 6, 0x0BE00000ULL, {16, 16}, {32, 0}, {16, 8},
                            {1, 1});
    auto r = parse_tensor_map(blob.data());
    CHECK(r.ok());
    if (!r.ok()) return;
    const TensorMap& tm = r.value();
    CHECK(tm.rank == 2);
    CHECK(tm.dtype_code == 6);
    CHECK(tm.element_bytes == 2);
    CHECK(tm.base_addr == 0x0BE00000ULL);
    CHECK(tm.global_dims[0] == 16);
    CHECK(tm.global_dims[1] == 16);
    CHECK(tm.strides[0] == 32);
    CHECK(tm.box_dims[0] == 16);
    CHECK(tm.box_dims[1] == 8);
    CHECK(tm.element_strides[0] == 1);
    CHECK(tm.swizzle == 0);
    CHECK(tm.mode == TensorMapMode::kTiled);
}

TEST(tensor_map_parse_rank5) {
    auto blob = build_tiled(5, 2, 0x1000ULL, {16, 16, 8, 8, 8},
                            {32, 512, 4096, 32768, 0}, {8, 8, 8, 8, 8},
                            {1, 1, 1, 1, 1});
    auto r = parse_tensor_map(blob.data());
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(r.value().rank == 5);
    CHECK(r.value().global_dims[4] == 8);
    CHECK(r.value().strides[1] == 512);
    CHECK(r.value().strides[2] == 4096);
    CHECK(r.value().strides[3] == 32768);
    CHECK(r.value().element_bytes == 4);
}

TEST(tensor_map_expand_2d_coords) {
    auto blob = build_tiled(2, 6, 0, {16, 16}, {32, 0}, {16, 8}, {1, 1});
    auto r = parse_tensor_map(blob.data());
    CHECK(r.ok());
    if (!r.ok()) return;
    std::uint32_t c[2] = {0, 0};
    auto a = expand_tile(r.value(), c);
    CHECK(a.ok());
    if (!a.ok()) return;
    CHECK(a.value().global.size() == 16u * 8u);
    CHECK(a.value().element_bytes == 2);
    CHECK(a.value().shared.size() == a.value().global.size());
    CHECK(a.value().global[0] == 0);
    CHECK(a.value().shared[0] == 0);
    CHECK(a.value().global[1] == 2);
    CHECK(a.value().shared[1] == 2);
    CHECK(a.value().global[8] == 32);     // row 1, col 0
    CHECK(a.value().shared[8] == 16);     // shared: 8 elems per row * 2B
    CHECK(!a.value().approximate);
    std::uint32_t c8[2] = {0, 8};
    auto a8 = expand_tile(r.value(), c8);
    CHECK(a8.ok());
    if (!a8.ok()) return;
    CHECK(a8.value().global[0] == 16);
    CHECK(a8.value().global[1] == 18);
    CHECK(a8.value().global[7] == 30);
}

TEST(tensor_map_expand_3d) {
    auto blob = build_tiled(3, 2, 0, {16, 16, 8}, {32, 16, 0}, {16, 8, 8},
                            {1, 1, 1});
    auto r = parse_tensor_map(blob.data());
    CHECK(r.ok());
    if (!r.ok()) return;
    std::uint32_t c[3] = {0, 0, 0};
    auto a = expand_tile(r.value(), c);
    CHECK(a.ok());
    if (!a.ok()) return;
    CHECK(a.value().global.size() == 16u * 8u * 8u);
    CHECK(a.value().global[1] == 4);   // element (0,0,1): 4 bytes
    CHECK(a.value().shared[1] == 4);
    CHECK(a.value().global[8] == 16);  // element (0,1,0): +16B stride
    CHECK(a.value().shared[8] == 32);  // 8 * 4B
}

TEST(tensor_map_swizzle_approximate) {
    auto blob = build_tiled(2, 6, 0, {16, 16}, {32, 0}, {16, 8}, {1, 1},
                            /*swizzle=*/2);
    auto r = parse_tensor_map(blob.data());
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(r.value().swizzle == 2);
    std::uint32_t c[2] = {0, 0};
    auto a = expand_tile(r.value(), c);
    CHECK(a.ok());
    if (!a.ok()) return;
    CHECK(a.value().approximate);
}

TEST(tensor_map_im2col_decode_only) {
    auto blob = build_tiled(3, 6, 0, {16, 16, 16}, {256, 32, 0}, {4, 4, 4},
                            {1, 1, 1});
    blob[8] |= 0x1;  // im2col marker bit
    auto r = parse_tensor_map(blob.data());
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(r.value().mode == TensorMapMode::kIm2col);
    std::uint32_t c[3] = {0, 0, 0};
    auto a = expand_tile(r.value(), c);
    CHECK(a.failed());  // decode-only
}

int main() {
    int failures = semu_test::run_all("semu-tensor-map");
    if (failures == 0) std::fprintf(stdout, "[  PASSED  ] all tensor-map tests\n");
    return failures == 0 ? 0 : 1;
}
