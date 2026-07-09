// tcgen05.commit — make an mbarrier track completion of prior async tcgen05 ops.
// Should lower to UTCBAR (mbarrier-arrive form). Test cta_group::1/::2 and the
// multicast variant.
//   nvcc -arch=sm_100a -cubin -o tests/tcgen05_commit_test.cubin tests/tcgen05_commit_test.cu
#include <cstdint>
#include <cuda/barrier>

extern "C" __global__ void commit_1cta(const uint64_t* sdesc_in) {
    __shared__ uint32_t s_taddr;
    __shared__ __align__(8) uint64_t s_mbar;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 128;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    asm volatile("mbarrier.init.shared.b64 [%0], 1;\n"
                 :: "r"((uint32_t)__cvta_generic_to_shared(&s_mbar)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    uint32_t mbar = (uint32_t)__cvta_generic_to_shared(&s_mbar);
    uint64_t sdesc = sdesc_in[0];

    asm volatile("tcgen05.cp.cta_group::1.128x256b [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // Commit: mbar tracks the prior cp's completion.
    asm volatile("tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];\n"
                 :: "r"(mbar) : "memory");

    // Wait on the mbarrier.
    asm volatile(
        "{\n .reg .pred p;\n"
        "L: mbarrier.try_wait.parity.shared.b64 p, [%0], 0;\n"
        "   @!p bra L;\n }\n"
        :: "r"(mbar) : "memory");

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 128;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}

extern "C" __global__ void commit_1cta_multicast(const uint64_t* sdesc_in,
                                                 uint16_t ctaMask) {
    __shared__ uint32_t s_taddr;
    __shared__ __align__(8) uint64_t s_mbar;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 128;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    asm volatile("mbarrier.init.shared.b64 [%0], 1;\n"
                 :: "r"((uint32_t)__cvta_generic_to_shared(&s_mbar)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    uint32_t mbar = (uint32_t)__cvta_generic_to_shared(&s_mbar);
    uint64_t sdesc = sdesc_in[0];

    asm volatile("tcgen05.cp.cta_group::1.128x256b [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // Multicast commit to CTAs selected by ctaMask (16-bit).
    asm volatile("tcgen05.commit.cta_group::1.mbarrier::arrive::one.multicast::cluster.b64 [%0], %1;\n"
                 :: "r"(mbar), "h"(ctaMask) : "memory");

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 128;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}

extern "C" __global__ void __cluster_dims__(2, 1, 1)
commit_2cta(const uint64_t* sdesc_in) {
    __shared__ uint32_t s_taddr;
    __shared__ __align__(8) uint64_t s_mbar;
    asm volatile(
        "tcgen05.alloc.cta_group::2.sync.aligned.shared::cta.b32 [%0], 128;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    asm volatile("mbarrier.init.shared.b64 [%0], 1;\n"
                 :: "r"((uint32_t)__cvta_generic_to_shared(&s_mbar)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    uint32_t mbar = (uint32_t)__cvta_generic_to_shared(&s_mbar);
    uint64_t sdesc = sdesc_in[0];

    asm volatile("tcgen05.cp.cta_group::2.128x256b [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    asm volatile("tcgen05.commit.cta_group::2.mbarrier::arrive::one.b64 [%0];\n"
                 :: "r"(mbar) : "memory");

    asm volatile("tcgen05.dealloc.cta_group::2.sync.aligned.b32 %0, 128;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::2.sync.aligned;\n");
}
