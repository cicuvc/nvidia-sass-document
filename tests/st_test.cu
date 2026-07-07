// ST (generic address space) coverage: stores through a generic pointer.
#include <cstdint>

extern "C" __global__ void st_generic_u32(void* p, uint32_t v) {
    asm volatile("st.u32 [%0], %1;" :: "l"(p), "r"(v) : "memory");
}
extern "C" __global__ void st_generic_u8(void* p, uint32_t v) {
    asm volatile("st.u8 [%0], %1;" :: "l"(p), "r"(v) : "memory");
}
extern "C" __global__ void st_generic_u16(void* p, uint32_t v) {
    asm volatile("st.u16 [%0], %1;" :: "l"(p), "r"(v) : "memory");
}
extern "C" __global__ void st_generic_u64(void* p, uint64_t v) {
    asm volatile("st.u64 [%0], %1;" :: "l"(p), "l"(v) : "memory");
}
extern "C" __global__ void st_generic_v4(void* p, uint4 v) {
    asm volatile("st.v4.u32 [%0], {%1,%2,%3,%4};" :: "l"(p), "r"(v.x), "r"(v.y), "r"(v.z), "r"(v.w) : "memory");
}
extern "C" __global__ void st_generic_vol(void* p, uint32_t v) {
    asm volatile("st.volatile.u32 [%0+16], %1;" :: "l"(p), "r"(v) : "memory");
}
