// STAS coverage: st.async.shared::cluster (distributed shared mem store), sizes/vec.
#include <cstdint>

// st.async to remote CTA shared memory + mbarrier tx signalling
extern "C" __global__ void stas_b32(uint32_t val, unsigned dst, unsigned bar) {
    asm volatile("st.async.shared::cluster.mbarrier::complete_tx::bytes.b32 [%0], %1, [%2];"
        :: "r"(dst), "r"(val), "r"(bar) : "memory");
}
extern "C" __global__ void stas_b64(uint64_t val, unsigned dst, unsigned bar) {
    asm volatile("st.async.shared::cluster.mbarrier::complete_tx::bytes.b64 [%0], %1, [%2];"
        :: "r"(dst), "l"(val), "r"(bar) : "memory");
}
extern "C" __global__ void stas_b128(uint4 val, unsigned dst, unsigned bar) {
    asm volatile("st.async.shared::cluster.mbarrier::complete_tx::bytes.v4.b32 [%0], {%1,%2,%3,%4}, [%5];"
        :: "r"(dst), "r"(val.x), "r"(val.y), "r"(val.z), "r"(val.w), "r"(bar) : "memory");
}
extern "C" __global__ void stas_v2_b32(uint2 val, unsigned dst, unsigned bar) {
    asm volatile("st.async.shared::cluster.mbarrier::complete_tx::bytes.v2.b32 [%0], {%1,%2}, [%3];"
        :: "r"(dst), "r"(val.x), "r"(val.y), "r"(bar) : "memory");
}
// weak variant
extern "C" __global__ void stas_weak_b32(uint32_t val, unsigned dst, unsigned bar) {
    asm volatile("st.async.weak.shared::cluster.mbarrier::complete_tx::bytes.b32 [%0], %1, [%2];"
        :: "r"(dst), "r"(val), "r"(bar) : "memory");
}
