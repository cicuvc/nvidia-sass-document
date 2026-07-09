// tcgen05.wait::ld / ::st — completion waits. Isolate each so ptxas can't fold
// the ordering into a neighbouring op, and also test them in the ld/st context.
//   nvcc -arch=sm_100a -cubin -o tests/tcgen05_wait_test.cubin tests/tcgen05_wait_test.cu
#include <cstdint>

// wait::ld after a real tcgen05.ld, before a dependent use.
extern "C" __global__ void wait_ld(uint32_t* out) {
    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;

    uint32_t v0, v1;
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x2.b32 {%0,%1}, [%2];\n"
                 : "=r"(v0), "=r"(v1) : "r"(taddr));
    asm volatile("tcgen05.wait::ld.sync.aligned;\n" ::: "memory");
    out[threadIdx.x] = v0 + v1;

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}

// wait::st after a real tcgen05.st.
extern "C" __global__ void wait_st(const uint32_t* in) {
    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;

    uint32_t v0 = in[0], v1 = in[1];
    asm volatile("tcgen05.st.sync.aligned.32x32b.x2.b32 [%0], {%1,%2};\n"
                 :: "r"(taddr), "r"(v0), "r"(v1));
    asm volatile("tcgen05.wait::st.sync.aligned;\n" ::: "memory");

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}

// Both waits back-to-back with no async op in between (isolation probe).
extern "C" __global__ void wait_both(uint32_t* out) {
    asm volatile("tcgen05.wait::ld.sync.aligned;\n" ::: "memory");
    asm volatile("tcgen05.wait::st.sync.aligned;\n" ::: "memory");
    out[threadIdx.x] = 0;
}
