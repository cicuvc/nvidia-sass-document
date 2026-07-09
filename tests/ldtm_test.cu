// LDTM (PTX tcgen05.ld) — tensor-memory load test.
// Allocates TMEM via tcgen05.alloc, then loads it back into registers with
// several shape/num/pack combinations to exercise the LDTM/LDT encodings.
// Build: nvcc -arch=sm_100a -cubin -o tests/ldtm_test.cubin tests/ldtm_test.cu
#include <cstdint>

extern "C" __global__ void ldtm_variants(uint32_t* out) {
    __shared__ uint32_t s_taddr;
    // Allocate 32 TMEM columns; base address written to shared.
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;\n"
        :: "r"((uint32_t)__cvta_generic_to_shared(&s_taddr)));
    __syncwarp();
    uint32_t taddr = s_taddr;

    // .32x32b .x1  -> 1 reg
    uint32_t r0;
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0}, [%1];\n"
                 : "=r"(r0) : "r"(taddr));

    // .32x32b .x2  -> 2 regs
    uint32_t r1a, r1b;
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x2.b32 {%0,%1}, [%2];\n"
                 : "=r"(r1a), "=r"(r1b) : "r"(taddr));

    // .16x64b .x2  -> 2 regs
    uint32_t r2a, r2b;
    asm volatile("tcgen05.ld.sync.aligned.16x64b.x2.b32 {%0,%1}, [%2];\n"
                 : "=r"(r2a), "=r"(r2b) : "r"(taddr));

    // .16x128b .x4 -> 8 regs
    uint32_t r3[8];
    asm volatile("tcgen05.ld.sync.aligned.16x128b.x4.b32 "
                 "{%0,%1,%2,%3,%4,%5,%6,%7}, [%8];\n"
                 : "=r"(r3[0]),"=r"(r3[1]),"=r"(r3[2]),"=r"(r3[3]),
                   "=r"(r3[4]),"=r"(r3[5]),"=r"(r3[6]),"=r"(r3[7])
                 : "r"(taddr));

    // .16x256b .x1 -> 4 regs
    uint32_t r4[4];
    asm volatile("tcgen05.ld.sync.aligned.16x256b.x1.b32 {%0,%1,%2,%3}, [%4];\n"
                 : "=r"(r4[0]),"=r"(r4[1]),"=r"(r4[2]),"=r"(r4[3])
                 : "r"(taddr));

    // .32x32b .x2 with .pack::16b
    uint32_t r5a, r5b;
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x2.pack::16b.b32 {%0,%1}, [%2];\n"
                 : "=r"(r5a), "=r"(r5b) : "r"(taddr));

    // .16x32bx2 .x2 with immHalfSplitoff
    uint32_t r6a, r6b;
    asm volatile("tcgen05.ld.sync.aligned.16x32bx2.x2.b32 {%0,%1}, [%2], 16;\n"
                 : "=r"(r6a), "=r"(r6b) : "r"(taddr));

    asm volatile("tcgen05.wait::ld.sync.aligned;\n" ::: "memory");

    uint32_t t = threadIdx.x;
    out[t*8+0] = r0;
    out[t*8+1] = r1a + r1b;
    out[t*8+2] = r2a + r2b;
    out[t*8+3] = r3[0]+r3[7];
    out[t*8+4] = r4[0]+r4[3];
    out[t*8+5] = r5a + r5b;
    out[t*8+6] = r6a + r6b;

    // Deallocate.
    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
                 :: "r"(taddr));
    asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n");
}
