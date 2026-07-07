// Direct PTX inline for I2I — try cvt.u16.u32 (non-saturating) and cvt.s8.s32
__global__ void i2i_direct_ptx(unsigned int* out, const int* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        int val = in[idx];
        int result;
        asm("cvt.u16.u32 %0, %1;" : "=r"(result) : "r"(val));
        out[idx] = result;
    }
}

__global__ void i2i_direct_s8(int* out, const int* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        int val = in[idx];
        int result;
        asm("cvt.s8.s32 %0, %1;" : "=r"(result) : "r"(val));
        out[idx] = result;
    }
}
