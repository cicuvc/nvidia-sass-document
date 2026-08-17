// GAP-11: reproducible source for the vecmix2.cubin sm120 fixture vectors.
// Build: nvcc -arch=sm_120 -O3 -cubin -o vecmix2.cubin vecmix2.cu
#include <cuda_fp16.h>
__global__ void k3(const half* a, const half* b, half* c, int n) {
    int i = threadIdx.x;
    half x = a[i], y = b[i];
    half2 p = __halves2half2(x, y);
    half2 q = __halves2half2(y, x);
    half2 r = __hadd2(p, q);
    c[i] = __low2half(r);
    c[i + 1] = __high2half(r);
    float f = __half2float(x);
    int qq = __float2int_rn(f * 2.5f);
    c[i] = __int2half_rn(qq);
}
__global__ void k4(long long* a, int n) {
    int i = threadIdx.x;
    long long v = a[i];
    long long w = v * 3LL + (long long)i;
    a[i] = w >> 2;
}
__global__ void k5(const unsigned* a, unsigned* b) {
    unsigned x = a[threadIdx.x];
    unsigned r = __brev(x) ^ __byte_perm(x, 0x44332211u, 0x1234);
    b[threadIdx.x] = r;
}
