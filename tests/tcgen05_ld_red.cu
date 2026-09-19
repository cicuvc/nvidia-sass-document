// tcgen05.ld.red lowering probes for sm_103a.
// Build: nvcc -arch=sm_103a -cubin -o /tmp/tcgen05_ld_red.cubin this_file.cu
#include <cstdint>

extern "C" __global__ void ldred_u32(uint32_t *out, uint32_t taddr) {
    uint32_t r0, r1, red;
    asm volatile(
        "tcgen05.ld.red.sync.aligned.32x32b.x2.u32.max "
        "{%0,%1}, %2, [%3];\n"
        : "=r"(r0), "=r"(r1), "=r"(red) : "r"(taddr));
    out[threadIdx.x * 3 + 0] = r0;
    out[threadIdx.x * 3 + 1] = r1;
    out[threadIdx.x * 3 + 2] = red;
}

extern "C" __global__ void ldred_s32(uint32_t *out, uint32_t taddr) {
    uint32_t r0, r1, r2, r3, red;
    asm volatile(
        "tcgen05.ld.red.sync.aligned.32x32b.x4.s32.min "
        "{%0,%1,%2,%3}, %4, [%5];\n"
        : "=r"(r0), "=r"(r1), "=r"(r2), "=r"(r3), "=r"(red)
        : "r"(taddr));
    out[threadIdx.x * 5 + 0] = r0;
    out[threadIdx.x * 5 + 1] = r1;
    out[threadIdx.x * 5 + 2] = r2;
    out[threadIdx.x * 5 + 3] = r3;
    out[threadIdx.x * 5 + 4] = red;
}

extern "C" __global__ void ldred_f32(float *out, uint32_t taddr) {
    float r0, r1, red;
    asm volatile(
        "tcgen05.ld.red.sync.aligned.32x32b.x2.f32.max.abs.NaN "
        "{%0,%1}, %2, [%3];\n"
        : "=f"(r0), "=f"(r1), "=f"(red) : "r"(taddr));
    out[threadIdx.x * 3 + 0] = r0;
    out[threadIdx.x * 3 + 1] = r1;
    out[threadIdx.x * 3 + 2] = red;
}

extern "C" __global__ void ldred_split(uint32_t *out, uint32_t taddr) {
    uint32_t r0, r1, r2, r3, red;
    asm volatile(
        "tcgen05.ld.red.sync.aligned.16x32bx2.x4.u32.min "
        "{%0,%1,%2,%3}, %4, [%5], 16;\n"
        : "=r"(r0), "=r"(r1), "=r"(r2), "=r"(r3), "=r"(red)
        : "r"(taddr));
    out[threadIdx.x * 5 + 0] = r0;
    out[threadIdx.x * 5 + 1] = r1;
    out[threadIdx.x * 5 + 2] = r2;
    out[threadIdx.x * 5 + 3] = r3;
    out[threadIdx.x * 5 + 4] = red;
}
