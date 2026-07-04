// IMNMX — try to trigger with register operands (not uniform)

__device__ __noinline__ int imnmx_s32(int a, int b) {
    volatile int va = a, vb = b;  // force register allocation
    int r;
    asm("max.s32 %0, %1, %2;" : "=r"(r) : "r"(va), "r"(vb));
    return r;
}

__device__ __noinline__ int imnmx_u32(unsigned a, unsigned b) {
    volatile unsigned va = a, vb = b;
    int r;
    asm("max.u32 %0, %1, %2;" : "=r"(r) : "r"(va), "r"(vb));
    return r;
}

__device__ __noinline__ int imnmx_s32_min(int a, int b) {
    volatile int va = a, vb = b;
    int r;
    asm("min.s32 %0, %1, %2;" : "=r"(r) : "r"(va), "r"(vb));
    return r;
}

__device__ __noinline__ int imnmx_u32_min(unsigned a, unsigned b) {
    volatile unsigned va = a, vb = b;
    int r;
    asm("min.u32 %0, %1, %2;" : "=r"(r) : "r"(va), "r"(vb));
    return r;
}

extern "C" __global__ void imnmx_kernel(int *out, int a, int b,
                                        unsigned ua, unsigned ub) {
    out[0] = imnmx_s32(a, b);
    out[1] = imnmx_s32_min(a, b);
    out[2] = imnmx_u32(ua, ub);
    out[3] = imnmx_u32_min(ua, ub);
}
