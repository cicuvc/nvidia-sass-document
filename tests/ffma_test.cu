// FFMA encoding verification — sm_90
// Rd = Ra * Rb + Rc  (fused multiply-add, 32-bit float)
//
// Forward-declare so we can control inlining.

__device__ __noinline__ float ffma_rrr(float a, float b, float c) {
    return a * b + c;  // -> FFMA RRR_RRR (all registers)
}

__device__ __noinline__ float ffma_rrr_negate(float a, float b, float c) {
    return a * b - c;  // -> FFMA Ra, Rb, -Rc
}

__device__ __noinline__ float ffma_rrr_double_negate(float a, float b, float c) {
    return -a * b + c;  // -> FFMA -Ra, Rb, Rc
}

__device__ __noinline__ float ffma_imm_c(float a, float b) {
    return a * b + 3.0f;  // -> FFMA RRI (F32Imm Sc)
}

__device__ __noinline__ float ffma_imm_b(float a, float c) {
    return a * 2.0f + c;  // -> FFMA RIR (F32Imm Sb)
}

__device__ __noinline__ float ffma_rrz(float a, float b) {
    return a * b + 0.0f;  // -> FFMA Ra, Rb, RZ (Rz is zero-reg)
}

__device__ __noinline__ float ffma_fmz(float a, float b, float c) {
    return __fmul_rn(a, b) + c;  // may still be FFMA, .fmz discussed
}

__device__ __noinline__ float ffma_sat(float a, float b, float c) {
    float r;
    asm("fma.rn.sat.f32 %0, %1, %2, %3;" : "=f"(r) : "f"(a), "f"(b), "f"(c));
    return r;
}

__device__ __noinline__ float ffma_rz(float a, float b, float c) {
    float r;
    asm("fma.rz.f32 %0, %1, %2, %3;" : "=f"(r) : "f"(a), "f"(b), "f"(c));
    return r;
}

__device__ __noinline__ float ffma_rm(float a, float b, float c) {
    float r;
    asm("fma.rm.f32 %0, %1, %2, %3;" : "=f"(r) : "f"(a), "f"(b), "f"(c));
    return r;
}

__device__ __noinline__ float ffma_rp(float a, float b, float c) {
    float r;
    asm("fma.rp.f32 %0, %1, %2, %3;" : "=f"(r) : "f"(a), "f"(b), "f"(c));
    return r;
}

__device__ __noinline__ float ffma_ftz(float a, float b, float c) {
    float r;
    asm("fma.ftz.rn.f32 %0, %1, %2, %3;" : "=f"(r) : "f"(a), "f"(b), "f"(c));
    return r;
}

extern "C" __global__ void ffma_kernel(float *out,
                                       float a, float b, float c) {
    out[0]  = ffma_rrr(a, b, c);
    out[1]  = ffma_rrr_negate(a, b, c);
    out[2]  = ffma_rrr_double_negate(a, b, c);
    out[3]  = ffma_imm_c(a, b);
    out[4]  = ffma_imm_b(a, c);
    out[5]  = ffma_rrz(a, b);
    out[6]  = ffma_sat(a, b, c);
    out[7]  = ffma_rz(a, b, c);
    out[8]  = ffma_rm(a, b, c);
    out[9]  = ffma_rp(a, b, c);
    out[10] = ffma_ftz(a, b, c);
    out[11] = ffma_fmz(a, b, c);
}
