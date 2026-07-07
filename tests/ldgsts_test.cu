// LDGSTS coverage: cp.async variants -> sizes, cop (.ca/.cg), zfill, prefetch(sp2), bypass.
#include <cstdint>

// .ca 4/8/16 bytes (SZ 32/64/128)
extern "C" __global__ void ca4(float* o, const float* in) {
    __shared__ float s[128]; int t = threadIdx.x;
    unsigned d = __cvta_generic_to_shared(&s[t]);
    asm volatile("cp.async.ca.shared.global [%0], [%1], 4;" :: "r"(d), "l"(in+t));
    asm volatile("cp.async.wait_all;"); __syncthreads(); o[t]=s[t];
}
extern "C" __global__ void ca8(float2* o, const float2* in) {
    __shared__ float2 s[128]; int t = threadIdx.x;
    unsigned d = __cvta_generic_to_shared(&s[t]);
    asm volatile("cp.async.ca.shared.global [%0], [%1], 8;" :: "r"(d), "l"(in+t));
    asm volatile("cp.async.wait_all;"); __syncthreads(); o[t]=s[t];
}
extern "C" __global__ void ca16(float4* o, const float4* in) {
    __shared__ float4 s[128]; int t = threadIdx.x;
    unsigned d = __cvta_generic_to_shared(&s[t]);
    asm volatile("cp.async.ca.shared.global [%0], [%1], 16;" :: "r"(d), "l"(in+t));
    asm volatile("cp.async.wait_all;"); __syncthreads(); o[t]=s[t];
}
// .cg (16 only) -> different cop
extern "C" __global__ void cg16(float4* o, const float4* in) {
    __shared__ float4 s[128]; int t = threadIdx.x;
    unsigned d = __cvta_generic_to_shared(&s[t]);
    asm volatile("cp.async.cg.shared.global [%0], [%1], 16;" :: "r"(d), "l"(in+t));
    asm volatile("cp.async.wait_all;"); __syncthreads(); o[t]=s[t];
}
// zfill: src-size < cp-size -> FILLCTRL.ZFILL
extern "C" __global__ void zfill(float4* o, const float4* in, int ss) {
    __shared__ float4 s[128]; int t = threadIdx.x;
    unsigned d = __cvta_generic_to_shared(&s[t]);
    asm volatile("cp.async.ca.shared.global [%0], [%1], 16, %2;" :: "r"(d), "l"(in+t), "r"(ss));
    asm volatile("cp.async.wait_all;"); __syncthreads(); o[t]=s[t];
}
// L2 prefetch size -> sp2 (LTC64B/128B/256B)
extern "C" __global__ void pf128(float4* o, const float4* in) {
    __shared__ float4 s[128]; int t = threadIdx.x;
    unsigned d = __cvta_generic_to_shared(&s[t]);
    asm volatile("cp.async.ca.shared.global.L2::128B [%0], [%1], 16;" :: "r"(d), "l"(in+t));
    asm volatile("cp.async.wait_all;"); __syncthreads(); o[t]=s[t];
}
// cache_policy -> descriptor variant
extern "C" __global__ void hint(float4* o, const float4* in, uint64_t pol) {
    __shared__ float4 s[128]; int t = threadIdx.x;
    unsigned d = __cvta_generic_to_shared(&s[t]);
    asm volatile("cp.async.ca.shared.global.L2::cache_hint [%0], [%1], 16, %2;"
        :: "r"(d), "l"(in+t), "l"(pol));
    asm volatile("cp.async.wait_all;"); __syncthreads(); o[t]=s[t];
}
