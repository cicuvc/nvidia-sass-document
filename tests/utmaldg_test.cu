// UTMALDG variant coverage: tensor dims 1D-5D, im2col, multicast.
#include <cstdint>
struct TMap { char x[128]; };  // stand-in for CUtensorMap descriptor

extern "C" __global__ void tma1d(const __grid_constant__ TMap tm, int c0) {
    extern __shared__ char smem[];
    __shared__ uint64_t bar;
    unsigned sd = __cvta_generic_to_shared(smem), sb = __cvta_generic_to_shared(&bar);
    const void* t = &tm;
    if (threadIdx.x == 0)
        asm volatile("cp.async.bulk.tensor.1d.shared::cluster.global.tile.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2}], [%3];" :: "r"(sd), "l"(t), "r"(c0), "r"(sb) : "memory");
}
extern "C" __global__ void tma2d(const __grid_constant__ TMap tm, int c0, int c1) {
    extern __shared__ char smem[];
    __shared__ uint64_t bar;
    unsigned sd = __cvta_generic_to_shared(smem), sb = __cvta_generic_to_shared(&bar);
    const void* t = &tm;
    if (threadIdx.x == 0)
        asm volatile("cp.async.bulk.tensor.2d.shared::cluster.global.tile.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2,%3}], [%4];" :: "r"(sd), "l"(t), "r"(c0), "r"(c1), "r"(sb) : "memory");
}
extern "C" __global__ void tma3d(const __grid_constant__ TMap tm, int c0, int c1, int c2) {
    extern __shared__ char smem[];
    __shared__ uint64_t bar;
    unsigned sd = __cvta_generic_to_shared(smem), sb = __cvta_generic_to_shared(&bar);
    const void* t = &tm;
    if (threadIdx.x == 0)
        asm volatile("cp.async.bulk.tensor.3d.shared::cluster.global.tile.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2,%3,%4}], [%5];" :: "r"(sd), "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(sb) : "memory");
}
extern "C" __global__ void tma4d(const __grid_constant__ TMap tm, int c0, int c1, int c2, int c3) {
    extern __shared__ char smem[];
    __shared__ uint64_t bar;
    unsigned sd = __cvta_generic_to_shared(smem), sb = __cvta_generic_to_shared(&bar);
    const void* t = &tm;
    if (threadIdx.x == 0)
        asm volatile("cp.async.bulk.tensor.4d.shared::cluster.global.tile.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2,%3,%4,%5}], [%6];" :: "r"(sd), "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(c3), "r"(sb) : "memory");
}
extern "C" __global__ void tma5d(const __grid_constant__ TMap tm, int c0, int c1, int c2, int c3, int c4) {
    extern __shared__ char smem[];
    __shared__ uint64_t bar;
    unsigned sd = __cvta_generic_to_shared(smem), sb = __cvta_generic_to_shared(&bar);
    const void* t = &tm;
    if (threadIdx.x == 0)
        asm volatile("cp.async.bulk.tensor.5d.shared::cluster.global.tile.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2,%3,%4,%5,%6}], [%7];" :: "r"(sd), "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(c3), "r"(c4), "r"(sb) : "memory");
}
// im2col (3d): coords + im2col offsets
extern "C" __global__ void tma3d_im2col(const __grid_constant__ TMap tm, int c0, int c1, int c2, short o0) {
    extern __shared__ char smem[];
    __shared__ uint64_t bar;
    unsigned sd = __cvta_generic_to_shared(smem), sb = __cvta_generic_to_shared(&bar);
    const void* t = &tm;
    if (threadIdx.x == 0)
        asm volatile("cp.async.bulk.tensor.3d.im2col.shared::cluster.global.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2,%3,%4}], [%5], {%6};"
            :: "r"(sd), "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(sb), "h"(o0) : "memory");
}
// multicast 2d
extern "C" __global__ void tma2d_mc(const __grid_constant__ TMap tm, int c0, int c1, uint16_t mask) {
    extern __shared__ char smem[];
    __shared__ uint64_t bar;
    unsigned sd = __cvta_generic_to_shared(smem), sb = __cvta_generic_to_shared(&bar);
    const void* t = &tm;
    if (threadIdx.x == 0)
        asm volatile("cp.async.bulk.tensor.2d.shared::cluster.global.tile.mbarrier::complete_tx::bytes.multicast::cluster"
            " [%0], [%1, {%2,%3}], [%4], %5;"
            :: "r"(sd), "l"(t), "r"(c0), "r"(c1), "r"(sb), "h"(mask) : "memory");
}
