// UTCCP (PTX tcgen05.cp) — async shared-memory -> TMEM copy test.
// Allocates TMEM, builds a matrix descriptor, and issues tcgen05.cp in several
// shape / multicast / decompress-format combinations.
// Build: nvcc -arch=sm_100a -cubin -o tests/utccp_test.cubin tests/utccp_test.cu
#include <cstdint>

extern "C" __global__ void utccp_variants(const uint64_t* sdesc_in) {
    __shared__ uint32_t s_taddr;
    __shared__ __align__(128) uint32_t s_mat[1024];
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 256;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;
    (void)s_mat;

    uint64_t sdesc = sdesc_in[0];

    // Base 128x256b copy.
    asm volatile("tcgen05.cp.cta_group::1.128x256b [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // 128x128b.
    asm volatile("tcgen05.cp.cta_group::1.128x128b [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // 4x256b.
    asm volatile("tcgen05.cp.cta_group::1.4x256b [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // 64x128b requires a warpx2 multicast.
    asm volatile("tcgen05.cp.cta_group::1.64x128b.warpx2::02_13 [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));
    asm volatile("tcgen05.cp.cta_group::1.64x128b.warpx2::01_23 [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // 32x128b requires warpx4 multicast.
    asm volatile("tcgen05.cp.cta_group::1.32x128b.warpx4 [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    // Decompression variants: dst .b8x16 from packed src formats.
    asm volatile("tcgen05.cp.cta_group::1.128x128b.b8x16.b6x16_p32 [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));
    asm volatile("tcgen05.cp.cta_group::1.128x128b.b8x16.b4x16_p64 [%0], %1;\n"
                 :: "r"(taddr), "l"(sdesc));

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 256;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}
