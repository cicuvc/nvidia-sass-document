// tcgen05.fence in a realistic producer/consumer context (mirrors PTX doc
// example): a real tcgen05.cp before ::before_thread_sync, and TMEM use after
// ::after_thread_sync, to check whether the fence emits any SASS when it
// actually has async tcgen05 ops to order.
//   nvcc -arch=sm_100a -cubin -o tests/tcgen05_fence_ctx.cubin tests/tcgen05_fence_ctx.cu
#include <cstdint>

extern "C" __global__ void producer(uint32_t* flag, const uint64_t* sdesc_in) {
    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 128;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    uint64_t sdesc = sdesc_in[0];

    // Async producer op.
    asm volatile("tcgen05.cp.cta_group::1.128x256b [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // Order the prior async cp before the visible flag store.
    asm volatile("tcgen05.fence::before_thread_sync;\n" ::: "memory");
    asm volatile("st.relaxed.gpu.b32 [%0], 1;\n" :: "l"(flag) : "memory");

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 128;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}

extern "C" __global__ void consumer(uint32_t* flag, uint32_t* out) {
    uint32_t r;
    // Spin on the flag.
    asm volatile(
        "{\n"
        "  .reg .pred p;\n"
        "L_wait: ld.relaxed.gpu.b32 %0, [%1];\n"
        "        setp.eq.u32 p, %0, 1;\n"
        "        @!p bra L_wait;\n"
        "}\n"
        : "=r"(r) : "l"(flag) : "memory");

    // Order subsequent async tcgen05 ops after the acquire.
    asm volatile("tcgen05.fence::after_thread_sync;\n" ::: "memory");

    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 128;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;

    uint32_t v0, v1;
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x2.b32 {%0,%1}, [%2];\n"
                 : "=r"(v0), "=r"(v1) : "r"(taddr));
    asm volatile("tcgen05.wait::ld.sync.aligned;\n" ::: "memory");
    out[threadIdx.x] = v0 + v1;

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 128;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}
