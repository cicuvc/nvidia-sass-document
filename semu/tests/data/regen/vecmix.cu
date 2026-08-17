// GAP-11: reproducible source for the vecmix.cubin sm120 fixture vectors.
// Build: nvcc -arch=sm_120 -O3 -cubin -o vecmix.cubin vecmix.cu
__global__ void k1(const float* a, const float* b, float* c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        float x = a[i];
        float y = b[i];
        c[i] = fmaf(x, y, 1.0f) + sinf(x) - __frcp_rn(y);
        unsigned u = __float_as_uint(x);
        int s = __ffs(u);
        c[i] += (float)s;
    }
}
__global__ void k2(const int* a, int* b, int n) {
    int i = threadIdx.x;
    int v = a[i];
    if (v > 0) b[i] = v * 3 + 7;
    else b[i] = v ^ 0xFF;
}
