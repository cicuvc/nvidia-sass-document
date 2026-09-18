#include <cstdint>

extern "C" __global__ void alloc32_v2_ref(uint32_t *out) {
    __shared__ uint32_t taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&taddr)) : "memory");
    __syncwarp();
    const uint32_t v = taddr;
    if (threadIdx.x == 0)
        out[0] = v;
    asm volatile(
        "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
        :: "r"(v) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
        ::: "memory");
}

extern "C" __global__ void alloc32_leak_v2_ref(uint32_t *out) {
    __shared__ uint32_t taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&taddr)) : "memory");
    __syncwarp();
    if (threadIdx.x == 0)
        out[0] = taddr;
}

// Reference lowering for the CTA-group::1 multi-warp TMEM allocator ABI.
// Compile with CUDA 12.8 for V1 or CUDA 13.x for V2 and compare the resulting
// user SASS/ELF contract with the hand-assembled kernels under asm_construct/.
extern "C" __global__ void alloc_multi_v2_ref(uint32_t *out) {
    __shared__ uint32_t taddr;
    const uint32_t tid = threadIdx.x;
    if (tid < 32) {
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 32;\n"
            :: "r"((uint32_t)__cvta_generic_to_shared(&taddr)) : "memory");
    }
    __syncthreads();
    if ((tid & 31) == 0)
        out[tid >> 5] = taddr;
    __syncthreads();
    if (tid < 32) {
        const uint32_t v = taddr;
        asm volatile(
            "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
            :: "r"(v) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
            ::: "memory");
    }
}
