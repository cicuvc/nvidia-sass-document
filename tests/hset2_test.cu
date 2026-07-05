// HSET2 / HSETP2 test kernel — packed FP16x2 comparisons
// Compile: nvcc -arch=sm_90 -O3 -cubin -o tests/hset2_test.cubin tests/hset2_test.cu
// Disasm: cuobjdump -arch sm_90 -sass tests/hset2_test.cubin

#include <cuda_fp16.h>

// ── HSET2: register output comparisons ──────────────────────────────────────

extern "C" __global__ void hset2_lt(__half2 a, __half2 b, __half2 *out) {
    *out = __hlt2(a, b);
}

extern "C" __global__ void hset2_eq(__half2 a, __half2 b, __half2 *out) {
    *out = __heq2(a, b);
}

extern "C" __global__ void hset2_le(__half2 a, __half2 b, __half2 *out) {
    *out = __hle2(a, b);
}

extern "C" __global__ void hset2_gt(__half2 a, __half2 b, __half2 *out) {
    *out = __hgt2(a, b);
}

extern "C" __global__ void hset2_ne(__half2 a, __half2 b, __half2 *out) {
    *out = __hne2(a, b);
}

extern "C" __global__ void hset2_ge(__half2 a, __half2 b, __half2 *out) {
    *out = __hge2(a, b);
}

// ── HSETP2: predicate output comparison ─────────────────────────────────────

extern "C" __global__ void hsetp2_if(__half2 a, __half2 b, float *out) {
    if (__hlt2(a, b).x)
        *out = 1.0f;
    else
        *out = 0.0f;
}
