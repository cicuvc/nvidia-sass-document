// LD (generic address space) coverage: loads through a generic pointer whose
// state space is unknown at compile time -> LD.E (not LDG/LDS/LDL).
#include <cstdint>

// generic pointer: could be global/shared/local -> ptxas must emit generic LD
extern "C" __global__ void ld_generic_u32(void* p, uint32_t* out) {
    uint32_t v;
    asm volatile("ld.u32 %0, [%1];" : "=r"(v) : "l"(p) : "memory");
    *out = v;
}
extern "C" __global__ void ld_generic_u8(void* p, uint32_t* out) {
    uint32_t v;
    asm volatile("ld.u8 %0, [%1];" : "=r"(v) : "l"(p) : "memory");
    *out = v;
}
extern "C" __global__ void ld_generic_u16(void* p, uint32_t* out) {
    uint32_t v;
    asm volatile("ld.u16 %0, [%1];" : "=r"(v) : "l"(p) : "memory");
    *out = v;
}
extern "C" __global__ void ld_generic_u64(void* p, uint64_t* out) {
    uint64_t v;
    asm volatile("ld.u64 %0, [%1];" : "=l"(v) : "l"(p) : "memory");
    *out = v;
}
extern "C" __global__ void ld_generic_v4(void* p, uint4* out) {
    uint4 v;
    asm volatile("ld.v4.u32 {%0,%1,%2,%3}, [%4];"
        : "=r"(v.x), "=r"(v.y), "=r"(v.z), "=r"(v.w) : "l"(p) : "memory");
    *out = v;
}
// volatile generic (strong-ish) + offset
extern "C" __global__ void ld_generic_vol(void* p, uint32_t* out) {
    uint32_t v;
    asm volatile("ld.volatile.u32 %0, [%1+16];" : "=r"(v) : "l"(p) : "memory");
    *out = v;
}
