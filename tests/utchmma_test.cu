// UTCHMMA (PTX tcgen05.mma.kind::f16) — 5th-gen tensor-core MMA test.
// D = A*B + D, single-thread-issued, operands/accumulator in TMEM; A/B via
// shared-memory matrix descriptors or A from TMEM.
//   nvcc -arch=sm_100a -cubin -o tests/utchmma_test.cubin tests/utchmma_test.cu
#include <cstdint>

// A from shared descriptor, accumulate (enable-input-d = true).
extern "C" __global__ void mma_desc(const uint64_t* descs, uint32_t idesc,
                                    uint32_t dtmem, uint32_t inMask) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    bool p = inMask & 1;
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, %4, 0;\n"
        "tcgen05.mma.cta_group::1.kind::f16 [%0], %1, %2, %3, {%5,%5,%5,%5}, pe;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc), "r"((uint32_t)p),
           "r"(0u) : "memory");
}

// A from TMEM.
extern "C" __global__ void mma_atmem(uint64_t bdesc, uint32_t idesc,
                                     uint32_t dtmem, uint32_t atmem) {
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::1.kind::f16 [%0], [%1], %2, %3, {%4,%4,%4,%4}, pe;\n }\n"
        :: "r"(dtmem), "r"(atmem), "l"(bdesc), "r"(idesc), "r"(0u) : "memory");
}

// With scale-input-d immediate.
extern "C" __global__ void mma_scale(const uint64_t* descs, uint32_t idesc,
                                     uint32_t dtmem) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::1.kind::f16 [%0], %1, %2, %3, {%4,%4,%4,%4}, pe, 3;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc), "r"(0u) : "memory");
}

// cta_group::2.
extern "C" __global__ void __cluster_dims__(2,1,1)
mma_2cta(const uint64_t* descs, uint32_t idesc, uint32_t dtmem) {
    uint64_t adesc = descs[0], bdesc = descs[1];
    asm volatile(
        "{\n .reg .pred pe;\n setp.ne.u32 pe, 1, 0;\n"
        "tcgen05.mma.cta_group::2.kind::f16 [%0], %1, %2, %3, {%4,%4,%4,%4,%4,%4,%4,%4}, pe;\n }\n"
        :: "r"(dtmem), "l"(adesc), "l"(bdesc), "r"(idesc), "r"(0u) : "memory");
}
