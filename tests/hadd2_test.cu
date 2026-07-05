// HADD2 test kernel — packed FP16x2 add with modifiers
// Compile: nvcc -arch=sm_90 -O3 -cubin -o tests/hadd2_test.cubin tests/hadd2_test.cu
// Disasm: cuobjdump -arch sm_90 -sass tests/hadd2_test.cubin

#include <cuda_fp16.h>

__device__ __forceinline__ unsigned h2bits(__half2 h) {
    return *reinterpret_cast<unsigned*>(&h);
}

// ── RR: plain add ───────────────────────────────────────────────────────────

extern "C" __global__ void hadd2_rr_plain(__half2 a, __half2 b, __half2 *out) {
    *out = a + b;
}

// ── F32 accumulator (widening) ──────────────────────────────────────────────

extern "C" __global__ void hadd2_f32(__half2 a, float *out) {
    *out = (float)__low2half(a);
}

// ── PTX asm: plain add.f16x2 ────────────────────────────────────────────────

extern "C" __global__ void hadd2_ptx_plain(__half2 a, __half2 b, __half2 *out) {
    unsigned ra = h2bits(a), rb = h2bits(b), rr;
    asm volatile("add.f16x2 %0, %1, %2;" : "=r"(rr) : "r"(ra), "r"(rb));
    *out = *reinterpret_cast<__half2*>(&rr);
}

// ── PTX asm: add.sat.f16x2 ──────────────────────────────────────────────────

extern "C" __global__ void hadd2_sat(__half2 a, __half2 b, __half2 *out) {
    unsigned ra = h2bits(a), rb = h2bits(b), rr;
    asm volatile("add.sat.f16x2 %0, %1, %2;" : "=r"(rr) : "r"(ra), "r"(rb));
    *out = *reinterpret_cast<__half2*>(&rr);
}

// ── PTX asm: add.ftz.f16x2 ──────────────────────────────────────────────────

extern "C" __global__ void hadd2_ftz(__half2 a, __half2 b, __half2 *out) {
    unsigned ra = h2bits(a), rb = h2bits(b), rr;
    asm volatile("add.ftz.f16x2 %0, %1, %2;" : "=r"(rr) : "r"(ra), "r"(rb));
    *out = *reinterpret_cast<__half2*>(&rr);
}

// ── PTX asm: add.ftz.sat.f16x2 ──────────────────────────────────────────────

extern "C" __global__ void hadd2_ftz_sat(__half2 a, __half2 b, __half2 *out) {
    unsigned ra = h2bits(a), rb = h2bits(b), rr;
    asm volatile("add.ftz.sat.f16x2 %0, %1, %2;" : "=r"(rr) : "r"(ra), "r"(rb));
    *out = *reinterpret_cast<__half2*>(&rr);
}
