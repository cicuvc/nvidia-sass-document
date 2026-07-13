// Bank-conflict probe harness — v2 (64-bit) vectorized shared access.
// One block, one warp. Exactly ONE measured shared vector instruction per warp
// via volatile inline PTX (guaranteed LDS.64 / STS.64, never eliminated).
// Per-thread BASE WORD index from a file (must be even => 8B aligned); the
// thread touches words [base, base+1].
//
// Usage: harness_v2 <ld|st> <patternfile>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#ifndef SMEMW
#define SMEMW 8192
#endif

__global__ void kern_ld(const int* __restrict__ idx, int* __restrict__ out) {
    __shared__ __align__(16) int smem[SMEMW];
    int t = threadIdx.x;
    unsigned addr = (unsigned)__cvta_generic_to_shared(&smem[idx[t]]);
    int v0, v1;
    asm volatile("ld.shared.v2.u32 {%0,%1}, [%2];" : "=r"(v0), "=r"(v1) : "r"(addr));
    out[t] = v0 + v1;
}

__global__ void kern_st(const int* __restrict__ idx, int* __restrict__ out) {
    __shared__ __align__(16) int smem[SMEMW];
    int t = threadIdx.x;
    unsigned addr = (unsigned)__cvta_generic_to_shared(&smem[idx[t]]);
    asm volatile("st.shared.v2.u32 [%0], {%1,%2};" :: "r"(addr), "r"(t), "r"(t + 100));
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
    for (int i = 0; i < 32; i++) if (h[i] < 0 || h[i] >= SMEMW-1 || (h[i]&1)) { fprintf(stderr,"idx bad(need even,in-range) %d\n",h[i]); return 2; }

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
