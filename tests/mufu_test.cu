// MUFU encoding verification — sm_90
// Multi-Function Unit: Rd = Op(Rb)
// On mio_pipe, single source operand

// FP32 MUFU operations (via PTX inline)
__device__ __noinline__ float mufu_rcp(float a) {
    float r; asm("rcp.approx.ftz.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}
__device__ __noinline__ float mufu_sqrt(float a) {
    float r; asm("sqrt.approx.ftz.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}
__device__ __noinline__ float mufu_sin(float a) {
    float r; asm("sin.approx.ftz.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}
__device__ __noinline__ float mufu_cos(float a) {
    float r; asm("cos.approx.ftz.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}
__device__ __noinline__ float mufu_ex2(float a) {
    float r; asm("ex2.approx.ftz.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}
__device__ __noinline__ float mufu_lg2(float a) {
    float r; asm("lg2.approx.ftz.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}
__device__ __noinline__ float mufu_rsq(float a) {
    float r; asm("rsqrt.approx.ftz.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}
__device__ __noinline__ float mufu_tanh(float a) {
    float r; asm("tanh.approx.f32 %0, %1;" : "=f"(r) : "f"(a)); return r;
}

// Standard math.h functions that map to MUFU
__device__ __noinline__ float mufu_sinf(float a) { return sinf(a); }
__device__ __noinline__ float mufu_cosf(float a) { return cosf(a); }
__device__ __noinline__ float mufu_exp2f(float a) { return exp2f(a); }
__device__ __noinline__ float mufu_log2f(float a) { return log2f(a); }

extern "C" __global__ void mufu_kernel(float *out, float a) {
    out[0]  = mufu_rcp(a);
    out[1]  = mufu_sqrt(a);
    out[2]  = mufu_sin(a);
    out[3]  = mufu_cos(a);
    out[4]  = mufu_ex2(a);
    out[5]  = mufu_lg2(a);
    out[6]  = mufu_rsq(a);
    out[7]  = mufu_tanh(a);
    out[8]  = mufu_sinf(a);
    out[9]  = mufu_cosf(a);
    out[10] = mufu_exp2f(a);
    out[11] = mufu_log2f(a);
}
