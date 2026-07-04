// FMNMX encoding verification — sm_90
// Rd = MIN(MAX)(Ra, Rb), with optional predicate output Pp
// On int_pipe (not fmalighter_pipe!)

__device__ __noinline__ float fmnmx_max(float a, float b) {
    return fmaxf(a, b);
}

__device__ __noinline__ float fmnmx_min(float a, float b) {
    return fminf(a, b);
}

__device__ __noinline__ float fmnmx_max_imm(float a) {
    return fmaxf(a, 255.0f);
}

__device__ __noinline__ float fmnmx_min_imm(float a) {
    return fminf(a, 0.0f);
}

__device__ __noinline__ float fmnmx_nan_max(float a, float b) {
    float r;
    asm("max.NaN.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

__device__ __noinline__ float fmnmx_ftz_max(float a, float b) {
    float r;
    asm("max.ftz.f32 %0, %1, %2;" : "=f"(r) : "f"(a), "f"(b));
    return r;
}

extern "C" __global__ void fmnmx_kernel(float *out,
                                        float a, float b) {
    out[0] = fmnmx_max(a, b);
    out[1] = fmnmx_min(a, b);
    out[2] = fmnmx_max_imm(a);
    out[3] = fmnmx_min_imm(a);
    out[4] = fmnmx_nan_max(a, b);
    out[5] = fmnmx_ftz_max(a, b);
}
