// Try reverse direction: narrow-to-wide conversions
// cvt.s32.u16, cvt.s32.u8, cvt.s32.s16, cvt.s32.s8
__global__ void i2i_extend(int* out, const unsigned short* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        int result;
        asm("cvt.s32.u16 %0, %1;" : "=r"(result) : "h"(in[idx]));
        out[idx] = result;
    }
}

__global__ void i2i_extend_s8(int* out, const char* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        int result;
        asm("cvt.s32.s8 %0, %1;" : "=r"(result) : "r"((int)in[idx]));
        out[idx] = result;
    }
}

__global__ void i2i_extend_u8(int* out, const unsigned char* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        int result;
        asm("cvt.s32.u8 %0, %1;" : "=r"(result) : "r"((int)in[idx]));
        out[idx] = result;
    }
}
