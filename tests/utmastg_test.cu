// UTMASTG variant coverage: tensor store shared->global, dims 1D-5D + im2col_no.
#include <cstdint>
struct TMap { char x[128]; };

extern "C" __global__ void st1d(const __grid_constant__ TMap tm, int c0) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.async.bulk.tensor.1d.global.shared::cta.bulk_group [%0, {%1}], [%2];"
            :: "l"(t), "r"(c0), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
        asm volatile("cp.async.bulk.wait_group.read 0;");
    }
}
extern "C" __global__ void st2d(const __grid_constant__ TMap tm, int c0, int c1) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.async.bulk.tensor.2d.global.shared::cta.bulk_group [%0, {%1,%2}], [%3];"
            :: "l"(t), "r"(c0), "r"(c1), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
extern "C" __global__ void st3d(const __grid_constant__ TMap tm, int c0, int c1, int c2) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.async.bulk.tensor.3d.global.shared::cta.bulk_group [%0, {%1,%2,%3}], [%4];"
            :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
extern "C" __global__ void st4d(const __grid_constant__ TMap tm, int c0, int c1, int c2, int c3) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.async.bulk.tensor.4d.global.shared::cta.bulk_group [%0, {%1,%2,%3,%4}], [%5];"
            :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(c3), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
extern "C" __global__ void st5d(const __grid_constant__ TMap tm, int c0, int c1, int c2, int c3, int c4) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.async.bulk.tensor.5d.global.shared::cta.bulk_group [%0, {%1,%2,%3,%4,%5}], [%6];"
            :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(c3), "r"(c4), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
// im2col store (3d)
extern "C" __global__ void st3d_im2col(const __grid_constant__ TMap tm, int c0, int c1, int c2) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    const void* t = &tm;
    if (threadIdx.x == 0) {
        asm volatile("cp.async.bulk.tensor.3d.im2col_no_offs.global.shared::cta.bulk_group [%0, {%1,%2,%3}], [%4];"
            :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(s) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
    }
}
