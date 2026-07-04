// FADD encoding verification — sm_90
// Rd = Ra + Rc  (float add)

__device__ __noinline__ float fadd_rr(float a, float b) {
    return a + b;  // -> FADD RRR_RR
}

__device__ __noinline__ float fadd_rr_negate(float a, float b) {
    return a - b;  // -> FADD Ra, -Rc  (or -b)
}

__device__ __noinline__ float fadd_rr_double_negate(float a, float b) {
    return -a + b;  // -> FADD -Ra, Rc
}

__device__ __noinline__ float fadd_imm_c(float a) {
    return a + 3.0f;  // -> FADD RRI (imm Sc)
}

__device__ __noinline__ float fadd_rz(float a) {
    return a + 0.0f;  // -> FADD Ra, RZ
}

__device__ __noinline__ float fadd_sat(float a, float b) {
    float r;
    asm("add.rn.sat.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fadd_rm(float a, float b) {
    float r;
    asm("add.rm.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fadd_rp(float a, float b) {
    float r;
    asm("add.rp.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fadd_rz_round(float a, float b) {
    float r;
    asm("add.rz.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fadd_ftz(float a, float b) {
    float r;
    asm("add.ftz.rn.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fadd_neg_neg(float a, float b) {
    return -a - b;  // -> FADD -Ra, -Rc
}

extern "C" __global__ void fadd_kernel(float *out,
                                       float a, float b) {
    out[0]  = fadd_rr(a, b);
    out[1]  = fadd_rr_negate(a, b);
    out[2]  = fadd_rr_double_negate(a, b);
    out[3]  = fadd_imm_c(a);
    out[4]  = fadd_rz(a);
    out[5]  = fadd_sat(a, b);
    out[6]  = fadd_rm(a, b);
    out[7]  = fadd_rp(a, b);
    out[8]  = fadd_rz_round(a, b);
    out[9]  = fadd_ftz(a, b);
    out[10] = fadd_neg_neg(a, b);
}
