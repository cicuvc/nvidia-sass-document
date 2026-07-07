// st.bulk: initialize shared memory region to zero.
#include <cstdint>

extern "C" __global__ void stbulk_32(unsigned n) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    asm volatile("st.bulk.shared::cta [%0], %1, 0;" :: "r"(s), "r"(n) : "memory");
}
extern "C" __global__ void stbulk_64(uint64_t n) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    asm volatile("st.bulk.shared::cta [%0], %1, 0;" :: "r"(s), "l"(n) : "memory");
}
extern "C" __global__ void stbulk_weak(unsigned n) {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    asm volatile("st.bulk.weak.shared::cta [%0], %1, 0;" :: "r"(s), "r"(n) : "memory");
}
extern "C" __global__ void stbulk_imm() {
    extern __shared__ char smem[];
    unsigned s = __cvta_generic_to_shared(smem);
    asm volatile("st.bulk.shared::cta [%0], 1024, 0;" :: "r"(s) : "memory");
}
