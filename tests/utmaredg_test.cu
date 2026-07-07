// UTMAREDG coverage: cp.reduce.async.bulk.tensor shared->global, red ops + dims.
#include <cstdint>
struct TMap { char x[128]; };

#define RED2D(NAME, OP) \
extern "C" __global__ void NAME(const __grid_constant__ TMap tm, int c0, int c1) { \
    extern __shared__ char smem[]; \
    unsigned s = __cvta_generic_to_shared(smem); \
    const void* t = &tm; \
    if (threadIdx.x == 0) { \
        asm volatile("cp.reduce.async.bulk.tensor.2d.global.shared::cta." OP ".tile.bulk_group [%0, {%1,%2}], [%3];" \
            :: "l"(t), "r"(c0), "r"(c1), "r"(s) : "memory"); \
        asm volatile("cp.async.bulk.commit_group;"); \
    } \
}

RED2D(red_add, "add")
RED2D(red_min, "min")
RED2D(red_max, "max")
RED2D(red_inc, "inc")
RED2D(red_dec, "dec")
RED2D(red_and, "and")
RED2D(red_or,  "or")
RED2D(red_xor, "xor")

// dims for add
extern "C" __global__ void red1d(const __grid_constant__ TMap tm, int c0) {
    extern __shared__ char smem[]; unsigned s = __cvta_generic_to_shared(smem); const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.reduce.async.bulk.tensor.1d.global.shared::cta.add.tile.bulk_group [%0, {%1}], [%2];"
            :: "l"(t), "r"(c0), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
extern "C" __global__ void red3d(const __grid_constant__ TMap tm, int c0, int c1, int c2) {
    extern __shared__ char smem[]; unsigned s = __cvta_generic_to_shared(smem); const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.reduce.async.bulk.tensor.3d.global.shared::cta.add.tile.bulk_group [%0, {%1,%2,%3}], [%4];"
            :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
extern "C" __global__ void red5d(const __grid_constant__ TMap tm, int c0, int c1, int c2, int c3, int c4) {
    extern __shared__ char smem[]; unsigned s = __cvta_generic_to_shared(smem); const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.reduce.async.bulk.tensor.5d.global.shared::cta.add.tile.bulk_group [%0, {%1,%2,%3,%4,%5}], [%6];"
            :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(c3), "r"(c4), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
