#include <cstdint>

__constant__ uint32_t const_arr[256] = {0};

// Test 1: ULDC from constant bank 0 immediate (ULDC Rd, c[bank][offset])
// ptxas generates ULDC for kernel parameter loads
__global__ void uldc_param_load(float* out, float* in, int n, float alpha) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        out[idx] = in[idx] * alpha;  // alpha loaded via ULDC
    }
}

// Test 2: ULDC.64 (64-bit load) — kernel with double params
__global__ void uldc_64_param(double* out, double* in, int n, double alpha) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        out[idx] = in[idx] * alpha;  // alpha (double) loaded via ULDC.64
    }
}

// Test 3: ULDC from indexed constant (ULDC URd, c[bank][URa+offset])
// This should trigger uldc_ur_offs_ variant
__global__ void uldc_indexed(float* out, int idx) {
    out[0] = const_arr[idx];  // lowered to ULDC URd, c[bank][URa+offset]
}

// Test 4: ULDC.64 from indexed constant
__global__ void uldc_indexed_64(uint64_t* out, int idx) {
    out[0] = ((uint64_t*)const_arr)[idx];  // may trigger ULDC.64 URd, c[bank][URa+offset]
}

// Test 5: ULDC unsigned 16-bit (triggered by __ldcv)
__global__ void uldc_u16(float* out, int idx) {
    uint16_t val = __ldg((const uint16_t*)&const_arr[idx]);
    out[0] = (float)val;
}

// Test 6: ULDC signed 16-bit
__global__ void uldc_s16(float* out, int idx) {
    int16_t val = __ldg((const int16_t*)&const_arr[idx]);
    out[0] = (float)val;
}

// Test 7: ULDC unsigned 8-bit
__global__ void uldc_u8(float* out, int idx) {
    uint8_t val = __ldg((const uint8_t*)&const_arr[idx]);
    out[0] = (float)val;
}

// Test 8: ULDC signed 8-bit
__global__ void uldc_s8(float* out, int idx) {
    int8_t val = __ldg((const int8_t*)&const_arr[idx]);
    out[0] = (float)val;
}

// Test 9: ULDC with large cache-indexed offset (>255 for RTV)
// Use many kernel params to force large offsets
__global__ void uldc_many_params(
    float* out, float p1, float p2, float p3, float p4, float p5,
    float p6, float p7, float p8, float p9, float p10, float p11, float p12) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx == 0) {
        out[0] = p1 + p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9 + p10 + p11 + p12;
    }
}
