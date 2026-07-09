// UTCQMMA / UTCMXQMMA (PTX tcgen05.mma MX block-scale) — quarter-precision MMA.
// .kind::mxf8f6f4 / .kind::mxf4 / .kind::mxf4nvf4 with block-scale operands in TMEM.
//   nvcc -arch=sm_100a -cubin -o tests/utcqmma_test.cubin tests/utcqmma_test.cu
#include <cstdint>

// mxf8f6f4.block_scale, A from shared descriptor, scale operands in TMEM.
extern "C" __global__ void mxf8f6f4_desc(const uint64_t* descs, uint32_t idesc,
                                          uint32_t dtmem, uint32_t satmem,
                                          uint32_t sbtmem) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::1.kind::mxf8f6f4.block_scale "
        "[%0], %1, %2, %3, [%4], [%5], pe;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc),
           "r"(satmem), "r"(sbtmem) : "memory");
}

// mxf8f6f4.block_scale, A from TMEM.
extern "C" __global__ void mxf8f6f4_atmem(uint64_t bdesc, uint32_t idesc,
                                           uint32_t dtmem, uint32_t atmem,
                                           uint32_t satmem, uint32_t sbtmem) {
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::1.kind::mxf8f6f4.block_scale "
        "[%0], [%1], %2, %3, [%4], [%5], pe;\n }\n"
        :: "r"(dtmem), "r"(atmem), "l"(bdesc), "r"(idesc),
           "r"(satmem), "r"(sbtmem) : "memory");
}

// mxf8f6f4.block_scale .2CTA
extern "C" __global__ void __cluster_dims__(2,1,1)
mxf8f6f4_2cta(const uint64_t* descs, uint32_t idesc,
               uint32_t dtmem, uint32_t satmem, uint32_t sbtmem) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::2.kind::mxf8f6f4.block_scale "
        "[%0], %1, %2, %3, [%4], [%5], pe;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc),
           "r"(satmem), "r"(sbtmem) : "memory");
}
