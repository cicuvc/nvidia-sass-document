// FMUL encoding verification — sm_90
// Rd = Ra * Rb  (float multiply)

__device__ __noinline__ float fmul_rr(float a, float b) {
    return a * b;  // -> FMUL RRR_RR
}

__device__ __noinline__ float fmul_rr_negate(float a, float b) {
    return -a * b;  // -> FMUL -Ra, Rb
}

__device__ __noinline__ float fmul_rr_double_negate(float a, float b) {
    return -a * -b;  // -> FMUL -Ra, -Rb (= a*b but encoded as double neg)
}

__device__ __noinline__ float fmul_imm(float a) {
    return a * 3.0f;  // -> FMUL RIR (imm Sb)
}

__device__ __noinline__ float fmul_rz(float a) {
    return a * 0.0f;  // -> FMUL Ra, RZ  (or optimized away)
}

__device__ __noinline__ float fmul_sat(float a, float b) {
    float r;
    asm("mul.rn.sat.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fmul_rm(float a, float b) {
    float r;
    asm("mul.rm.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fmul_rp(float a, float b) {
    float r;
    asm("mul.rp.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fmul_rz_round(float a, float b) {
    float r;
    asm("mul.rz.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fmul_ftz(float a, float b) {
    float r;
    asm("mul.ftz.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

extern "C" __global__ void fmul_kernel(float *out,
                                       float a, float b) {
    out[0] = fmul_rr(a, b);
    out[1] = fmul_rr_negate(a, b);
    out[2] = fmul_rr_double_negate(a, b);
    out[3] = fmul_imm(a);
    out[4] = fmul_rz(a);
    out[5] = fmul_sat(a, b);
    out[6] = fmul_rm(a, b);
    out[7] = fmul_rp(a, b);
    out[8] = fmul_rz_round(a, b);
    out[9] = fmul_ftz(a, b);
}
