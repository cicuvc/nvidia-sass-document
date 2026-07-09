// UTCOMMA (PTX tcgen05.mma.kind::mxf4.block_scale) — FP4 MX MMA.
// Shares opcodes 0x15ea/0x19ea with UTCHMMA but distinguished by opType=1,
// SCALE_VECTOR_SZ at bit[62], and TMEMI scale operand.
// Also test .kind::mxf4nvf4 if ptxas accepts it.
//   nvcc -arch=sm_100a -cubin -o tests/utcomma_test.cubin tests/utcomma_test.cu
#include <cstdint>

// mxf4.block_scale, A from shared descriptor.
extern "C" __global__ void mxf4_desc(const uint64_t* descs, uint32_t idesc,
                                      uint32_t dtmem, uint32_t satmem,
                                      uint32_t sbtmem) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::1.kind::mxf4.block_scale "
        "[%0], %1, %2, %3, [%4], [%5], pe;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc),
           "r"(satmem), "r"(sbtmem) : "memory");
}

// mxf4.block_scale with .scale_vec::2X (tests SCALE_VECTOR_SZ override).
extern "C" __global__ void mxf4_scale2x(const uint64_t* descs, uint32_t idesc,
                                         uint32_t dtmem, uint32_t satmem,
                                         uint32_t sbtmem) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::1.kind::mxf4.block_scale.scale_vec::2X "
        "[%0], %1, %2, %3, [%4], [%5], pe;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc),
           "r"(satmem), "r"(sbtmem) : "memory");
}

// mxf4nvf4.block_scale (with .scale_vec::4X).
extern "C" __global__ void mxf4nvf4_desc(const uint64_t* descs, uint32_t idesc,
                                          uint32_t dtmem, uint32_t satmem,
                                          uint32_t sbtmem) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::1.kind::mxf4nvf4.block_scale.scale_vec::4X "
        "[%0], %1, %2, %3, [%4], [%5], pe;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc),
           "r"(satmem), "r"(sbtmem) : "memory");
}
