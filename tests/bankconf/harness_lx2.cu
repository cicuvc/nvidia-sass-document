// L1 <-> shared interaction probe (v2).
// Per iteration a warp issues (optionally) a vectorized GLOBAL v4 load (L1-cached,
// address cycles a small hot window) and (optionally) a vectorized SHARED v4
// store + xor-neighbor v4 load. Both shared ops are kept live (load feeds output,
// store feeds a different lane's load) so nothing is dead-store-eliminated.
// All memory ops are volatile inline PTX (emitted every iter, not hoisted).
//
// Build variants: -DGLOB={0,1} -DSHAR={0,1}. Usage: harness_lx2 <iters> <nblk>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#ifndef GLOB
#define GLOB 1
#endif
#ifndef SHAR
#define SHAR 1
#endif
#ifndef BLK
#define BLK 256
#endif
#ifndef GWIN
#define GWIN 8
#endif
#ifndef GSTRIDE
#define GSTRIDE 1
#endif

__global__ void kern(const float4* __restrict__ gin, float4* __restrict__ gout, int iters) {
    __shared__ __align__(16) float4 smem[BLK];
    int t = threadIdx.x;
#if SHCONF
    int st = ((t * 8) & (BLK - 1));   // 8-way collisions among float4 slots (heavy shared conflict)
#else
    int st = t;
#endif
    unsigned sa = (unsigned)__cvta_generic_to_shared(&smem[st]);
    unsigned sn = (unsigned)__cvta_generic_to_shared(&smem[st ^ 1]);
    float gx = 1.0f;
    for (int i = 0; i < iters; i++) {
#if GLOB
        {
            const float4* p = gin + (unsigned)t * GSTRIDE + (unsigned)(i & (GWIN - 1)) * BLK * GSTRIDE;
            float a, b, c, d;
            asm volatile("ld.global.v4.f32 {%0,%1,%2,%3}, [%4];"
                         : "=f"(a), "=f"(b), "=f"(c), "=f"(d) : "l"(p));
            gx += a + b + c + d;
        }
#endif
#if SHAR
        {
            asm volatile("st.shared.v4.f32 [%0], {%1,%1,%1,%1};" :: "r"(sa), "f"(gx));
            float a, b, c, d;
            asm volatile("ld.shared.v4.f32 {%0,%1,%2,%3}, [%4];"
                         : "=f"(a), "=f"(b), "=f"(c), "=f"(d) : "r"(sn));
            gx += a - b + c - d;
        }
#endif
    }
    gout[blockIdx.x * BLK + t] = make_float4(gx, gx, gx, gx);
}

int main(int argc, char** argv) {
    int iters = argc > 1 ? atoi(argv[1]) : 2000;
    int nblk  = argc > 2 ? atoi(argv[2]) : 1;
    float4 *gin, *gout;
    size_t n = (size_t)GWIN * BLK + 4096;
    cudaMalloc(&gin, n * sizeof(float4));
    cudaMalloc(&gout, (size_t)BLK * nblk * sizeof(float4));
    cudaMemset(gin, 0, n * sizeof(float4));
    kern<<<nblk, BLK>>>(gin, gout, iters);
    cudaError_t e = cudaDeviceSynchronize();
    if (e != cudaSuccess) { fprintf(stderr, "launch err: %s\n", cudaGetErrorString(e)); return 1; }
    return 0;
}
