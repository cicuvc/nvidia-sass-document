// tcgen05.shift.down — async row-shift of a TMEM matrix. Should lower to UTCSHIFT.
// Also confirm .ashift (fused MMA+shift) vs a standalone shift.
//   nvcc -arch=sm_100a -cubin -o tests/tcgen05_shift_test.cubin tests/tcgen05_shift_test.cu
#include <cstdint>

extern "C" __global__ void shift_1cta(uint32_t taddr) {
    asm volatile("tcgen05.shift.down.cta_group::1 [%0];\n" :: "r"(taddr) : "memory");
}

extern "C" __global__ void __cluster_dims__(2,1,1)
shift_2cta(uint32_t taddr) {
    asm volatile("tcgen05.shift.down.cta_group::2 [%0];\n" :: "r"(taddr) : "memory");
}

// A real alloc'd address, offset form.
extern "C" __global__ void shift_alloc(uint32_t* out) {
    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 128;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    asm volatile("tcgen05.shift.down.cta_group::1 [%0];\n" :: "r"(taddr) : "memory");
    out[threadIdx.x] = taddr;
    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 128;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}
