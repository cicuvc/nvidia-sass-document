// Test kernel to trigger I2I emission
#include <cstdint>

// Pattern 1: Explicit narrow integer conversion — compiler might emit I2I for truncation
__global__ void i2i_narrow_cast(unsigned char* out, const int* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        // int -> unsigned char: truncation
        out[idx] = (unsigned char)(in[idx]);
    }
}

// Pattern 2: Saturating conversion via min/max (might trigger I2I.SAT)
__global__ void i2i_sat_u8(unsigned char* out, const int* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        int val = in[idx];
        // Manual saturate to U8 range
        val = max(0, min(255, val));
        out[idx] = (unsigned char)val;
    }
}

// Pattern 3: PTX inline with .sat modifier
__global__ void i2i_ptx_sat(unsigned char* out, const int* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        int val = in[idx];
        int result;
        // cvt.sat.u8.u32 — direct PTX for I2I.SAT.U8
        asm("cvt.sat.u8.u32 %0, %1;" : "=r"(result) : "r"(val));
        out[idx] = (unsigned char)result;
    }
}

// Pattern 4: Sub-word store — might force narrow int conversion
__global__ void i2i_narrow_store(short* out, const int* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        // int -> short: truncation (S16)
        out[idx] = (short)(in[idx] * 2);
    }
}
