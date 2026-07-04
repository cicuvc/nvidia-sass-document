// FSET encoding verification — sm_90
// Rd = comparison result (bool 0xFFFFFFFF/0 in register)
// On int_pipe

__device__ __noinline__ int fset_eq(float a, float b) {
    int r; asm("set.eq.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_ne(float a, float b) {
    int r; asm("set.ne.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_lt(float a, float b) {
    int r; asm("set.lt.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_gt(float a, float b) {
    int r; asm("set.gt.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_le(float a, float b) {
    int r; asm("set.le.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_ge(float a, float b) {
    int r; asm("set.ge.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_num(float a, float b) {
    int r; asm("set.num.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_nan(float a, float b) {
    int r; asm("set.nan.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_ltu(float a, float b) {
    int r; asm("set.ltu.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_gtu(float a, float b) {
    int r; asm("set.gtu.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_equ(float a, float b) {
    int r; asm("set.equ.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_neu(float a, float b) {
    int r; asm("set.neu.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_leu(float a, float b) {
    int r; asm("set.leu.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_geu(float a, float b) {
    int r; asm("set.geu.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
__device__ __noinline__ int fset_ftz(float a, float b) {
    int r; asm("set.lt.ftz.f32.f32 %0, %1, %2;" : "=r"(r) : "f"(a), "f"(b)); return r;
}
extern "C" __global__ void fset_kernel(int *out, float a, float b) {
    out[0]  = fset_eq(a, b);
    out[1]  = fset_ne(a, b);
    out[2]  = fset_lt(a, b);
    out[3]  = fset_gt(a, b);
    out[4]  = fset_le(a, b);
    out[5]  = fset_ge(a, b);
    out[6]  = fset_num(a, b);
    out[7]  = fset_nan(a, b);
    out[8]  = fset_ltu(a, b);
    out[9]  = fset_gtu(a, b);
    out[10] = fset_equ(a, b);
    out[11] = fset_neu(a, b);
    out[12] = fset_leu(a, b);
    out[13] = fset_geu(a, b);
    out[14] = fset_ftz(a, b);
}
