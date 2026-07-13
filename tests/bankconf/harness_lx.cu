// L1 <-> shared interaction probe.
// Each iteration a warp issues (optionally) a vectorized GLOBAL v4 load (L1-cached)
// and (optionally) a vectorized SHARED v4 store/load, back to back, via volatile
// inline PTX so both are emitted every iteration and not hoisted. Global address
// cycles through a small L1-resident window so it stays a hit but is not loop-invariant.
//
// Build 4 variants via -DGLOB={0,1} -DSHAR={0,1} (SHAR uses store; -DSLD=1 -> shared load).
// Usage: harness_lx <iters>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#ifndef GLOB
#define GLOB 1
#endif
#ifndef SHAR
#define SHAR 1
#endif
#ifndef SLD
#define SLD 0
#endif
#ifndef BLK
#define BLK 32
#endif
#ifndef GWIN
#define GWIN 8          // number of distinct v4 rows cycled in the global window
#endif

__global__ void kern(const float4* __restrict__ gin, float4* __restrict__ gout, int iters) {
    __shared__ __align__(16) float4 smem[BLK];
    int t = threadIdx.x;
    float gx = 0.f;
    for (int i = 0; i < iters; i++) {
#if GLOB
        {
            const float4* p = gin + t + (unsigned)(i & (GWIN - 1)) * BLK;
            float a, b, c, d;
            asm volatile("ld.global.v4.f32 {%0,%1,%2,%3}, [%4];"
                         : "=f"(a), "=f"(b), "=f"(c), "=f"(d) : "l"(p));
            gx += a + b + c + d;
        }
#endif
#if SHAR
        {
            unsigned sa = (unsigned)__cvta_generic_to_shared(&smem[t]);
#if SLD
            float a, b, c, d;
            asm volatile("ld.shared.v4.f32 {%0,%1,%2,%3}, [%4];"
                         : "=f"(a), "=f"(b), "=f"(c), "=f"(d) : "r"(sa));
            gx += a + b + c + d;
#else
            asm volatile("st.shared.v4.f32 [%0], {%1,%1,%1,%1};" :: "r"(sa), "f"(gx));
#endif
        }
#endif
    }
    gout[t] = make_float4(gx, gx, gx, gx);
}

int main(int argc, char** argv) {
    int iters = argc > 1 ? atoi(argv[1]) : 1000;
    int nblk  = argc > 2 ? atoi(argv[2]) : 1;
    float4* gin; float4* gout;
    size_t n = (size_t)GWIN * BLK * nblk + 4096;
    cudaMalloc(&gin, n * sizeof(float4));
    cudaMalloc(&gout, (size_t)BLK * nblk * sizeof(float4));
    cudaMemset(gin, 0, n * sizeof(float4));
    kern<<<nblk, BLK>>>(gin, gout, iters);
    cudaError_t e = cudaDeviceSynchronize();
    if (e != cudaSuccess) { fprintf(stderr, "launch err: %s\n", cudaGetErrorString(e)); return 1; }
    return 0;
}
