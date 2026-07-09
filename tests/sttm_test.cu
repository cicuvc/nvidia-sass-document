// STTM (PTX tcgen05.st) — tensor-memory store test.
// Allocates TMEM via tcgen05.alloc, then stores registers into it with several
// shape/num/unpack combinations to exercise the STTM/STT encodings.
// Build: nvcc -arch=sm_100a -cubin -o tests/sttm_test.cubin tests/sttm_test.cu
#include <cstdint>

extern "C" __global__ void sttm_variants(const uint32_t* in) {
    __shared__ uint32_t s_taddr;
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;

    uint32_t v0=in[0],v1=in[1],v2=in[2],v3=in[3],v4=in[4],v5=in[5],v6=in[6],v7=in[7];

    // .32x32b .x1  -> 1 reg
    asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0], {%1};\n"
                 :: "r"(taddr), "r"(v0));

    // .32x32b .x2  -> 2 regs
    asm volatile("tcgen05.st.sync.aligned.32x32b.x2.b32 [%0], {%1,%2};\n"
                 :: "r"(taddr), "r"(v0), "r"(v1));

    // .16x64b .x2  -> 2 regs
    asm volatile("tcgen05.st.sync.aligned.16x64b.x2.b32 [%0], {%1,%2};\n"
                 :: "r"(taddr), "r"(v0), "r"(v1));

    // .16x128b .x4 -> 8 regs
    asm volatile("tcgen05.st.sync.aligned.16x128b.x4.b32 "
                 "[%0], {%1,%2,%3,%4,%5,%6,%7,%8};\n"
                 :: "r"(taddr), "r"(v0),"r"(v1),"r"(v2),"r"(v3),
                    "r"(v4),"r"(v5),"r"(v6),"r"(v7));

    // .16x256b .x1 -> 4 regs
    asm volatile("tcgen05.st.sync.aligned.16x256b.x1.b32 [%0], {%1,%2,%3,%4};\n"
                 :: "r"(taddr), "r"(v0),"r"(v1),"r"(v2),"r"(v3));

    // .16x128b .x1 with .unpack::16b -> 2 regs
    asm volatile("tcgen05.st.sync.aligned.16x128b.x1.unpack::16b.b32 [%0], {%1,%2};\n"
                 :: "r"(taddr), "r"(v0), "r"(v1));

    // .16x32bx2 .x2 with immHalfSplitoff
    asm volatile("tcgen05.st.sync.aligned.16x32bx2.x2.b32 [%0], 16, {%1,%2};\n"
                 :: "r"(taddr), "r"(v0), "r"(v1));

    asm volatile("tcgen05.wait::st.sync.aligned;\n" ::: "memory");

    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}
