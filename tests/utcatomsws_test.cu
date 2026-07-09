// UTCATOMSWS coverage — try to surface CAS / .ONE / .2CTA / .OR variants.
// tcgen05.alloc/dealloc lower to UTCATOMSWS; cta_group::2 + a cluster launch
// should exercise the 2CTA path. Build:
//   nvcc -arch=sm_100a -cubin -o tests/utcatomsws_test.cubin tests/utcatomsws_test.cu
#include <cstdint>

extern "C" __global__ void alloc_1cta(uint32_t* out) {
    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 64;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    out[threadIdx.x] = taddr;
    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 64;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}

extern "C" __global__ void __cluster_dims__(2, 1, 1)
alloc_2cta(uint32_t* out) {
    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::2.sync.aligned.shared::cta.b32 [%0], 128;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    out[threadIdx.x] = taddr;
    asm volatile("tcgen05.dealloc.cta_group::2.sync.aligned.b32 %0, 128;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::2.sync.aligned;\n");
}
