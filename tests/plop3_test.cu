// Test kernel to trigger PLOP3 emission via complex predicate logic
#include <cstdint>

// Nested conditionals combining multiple predicates
__global__ void plop3_predicate_chain(float* out, const float* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        float val = in[idx];

        // Complex predicate chain: multiple boolean conditions combined
        bool cond_a = (val > 0.0f);
        bool cond_b = (val < 100.0f);
        bool cond_c = (val != 0.5f);

        // AND of three conditions should trigger PLOP3
        if (cond_a && cond_b && cond_c) {
            out[idx] = val * 2.0f;
        } else {
            out[idx] = val;
        }
    }
}

// Explicit LOP3-style predicate combining via inline PTX with constant LUTs
__global__ void plop3_explicit_lut(float* out, const float* in, int n) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        float val = in[idx];

        int a = (val > 0.0f) ? 1 : 0;
        int b = (val < 100.0f) ? 1 : 0;
        int c = ((int)val & 1) ? 1 : 0;

        // LOP3 with LUT=0x80 (A & B & C)
        int sel;
        asm("lop3.b32 %0, %1, %2, %3, 0x80;" : "=r"(sel) : "r"(a), "r"(b), "r"(c));

        out[idx] = sel ? (val * 2.0f) : val;
    }
}

// Heavy branching to force predicate optimizations
__global__ void plop3_heavy_branch(float* out, const float* in, int n, float thresh_a, float thresh_b, float thresh_c) {
    int idx = threadIdx.x + blockIdx.x * blockDim.x;
    if (idx < n) {
        float v = in[idx];

        // Multiple threshold comparisons create predicate chains
        bool p1 = v > thresh_a;
        bool p2 = v < thresh_b;
        bool p3 = v == thresh_c;

        // XOR pattern
        if (p1 ^ p2 ^ p3) {
            out[idx] = v * 3.0f;
        } else if ((p1 && p2) || (p2 && p3) || (p1 && p3)) {
            out[idx] = v * 2.0f;
        } else if (p1 && p2 && p3) {
            out[idx] = v * 4.0f;
        } else {
            out[idx] = v;
        }
    }
}
