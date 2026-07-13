// Bank-conflict probe harness — v4 (128-bit) vectorized shared access.
// One block, one warp. Exactly ONE measured LDS.128 / STS.128 per warp via
// volatile inline PTX. Per-thread BASE WORD index from a file (must be multiple
// of 4 => 16B aligned); the thread touches words [base .. base+3].
//
// Usage: harness_v4 <ld|st> <patternfile>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#ifndef SMEMW
#define SMEMW 16384
#endif

__global__ void kern_ld(const int* __restrict__ idx, int* __restrict__ out) {
    __shared__ __align__(16) int smem[SMEMW];
    int t = threadIdx.x;
    unsigned addr = (unsigned)__cvta_generic_to_shared(&smem[idx[t]]);
    int v0, v1, v2, v3;
    asm volatile("ld.shared.v4.u32 {%0,%1,%2,%3}, [%4];"
                 : "=r"(v0), "=r"(v1), "=r"(v2), "=r"(v3) : "r"(addr));
    out[t] = v0 + v1 + v2 + v3;
}

__global__ void kern_st(const int* __restrict__ idx, int* __restrict__ out) {
    __shared__ __align__(16) int smem[SMEMW];
    int t = threadIdx.x;
    unsigned addr = (unsigned)__cvta_generic_to_shared(&smem[idx[t]]);
    asm volatile("st.shared.v4.u32 [%0], {%1,%2,%3,%4};"
                 :: "r"(addr), "r"(t), "r"(t+100), "r"(t+200), "r"(t+300));
    __syncthreads();
    unsigned a2 = (unsigned)__cvta_generic_to_shared(&smem[t]);
    int v;
    asm volatile("ld.shared.u32 %0, [%1];" : "=r"(v) : "r"(a2));
    out[t] = v;
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s <ld|st> <patternfile>\n", argv[0]); return 2; }
    bool store = argv[1][0] == 's';
    FILE* f = fopen(argv[2], "r");
    if (!f) { perror("fopen"); return 2; }
    int h[32];
    for (int i = 0; i < 32; i++) { if (fscanf(f, "%d", &h[i]) != 1) { fprintf(stderr,"bad pattern @%d\n",i); return 2; } }
    fclose(f);
    for (int i = 0; i < 32; i++) if (h[i] < 0 || h[i] >= SMEMW-3 || (h[i]&3)) { fprintf(stderr,"idx bad(need mult4,in-range) %d\n",h[i]); return 2; }

    int *didx, *dout;
    cudaMalloc(&didx, 32 * sizeof(int));
    cudaMalloc(&dout, 32 * sizeof(int));
    cudaMemcpy(didx, h, 32 * sizeof(int), cudaMemcpyHostToDevice);

    if (store) kern_st<<<1, 32>>>(didx, dout);
    else       kern_ld<<<1, 32>>>(didx, dout);
    cudaError_t e = cudaDeviceSynchronize();
    if (e != cudaSuccess) { fprintf(stderr, "launch err: %s\n", cudaGetErrorString(e)); return 1; }
    return 0;
}
