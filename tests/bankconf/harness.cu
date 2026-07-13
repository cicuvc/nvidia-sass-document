// Bank-conflict probe harness (inline-PTX version).
// One block, one warp (32 threads). Exactly ONE measured shared instruction
// per warp via volatile inline asm (guaranteed non-vectorized ld/st.shared.u32,
// never eliminated). ncu metrics then read out per-access:
//   wavefronts == serialized passes (N-way => N),  conflicts == wavefronts-1.
// Per-thread shared WORD index is read from a file (32 ints), fully general.
//
// Usage: harness <ld|st> <patternfile>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#ifndef SMEMW
#define SMEMW 8192            // 32 KB of int shared
#endif

__global__ void kern_ld(const int* __restrict__ idx, int* __restrict__ out) {
    __shared__ int smem[SMEMW];
    int t = threadIdx.x;
    unsigned addr = (unsigned)__cvta_generic_to_shared(&smem[idx[t]]);
    int v;
    asm volatile("ld.shared.u32 %0, [%1];" : "=r"(v) : "r"(addr));   // measured LDS
    out[t] = v;
}

__global__ void kern_st(const int* __restrict__ idx, int* __restrict__ out) {
    __shared__ int smem[SMEMW];
    int t = threadIdx.x;
    unsigned addr = (unsigned)__cvta_generic_to_shared(&smem[idx[t]]);
    asm volatile("st.shared.u32 [%0], %1;" :: "r"(addr), "r"(t));    // measured STS
    __syncthreads();
    unsigned a2 = (unsigned)__cvta_generic_to_shared(&smem[t]);
    int v;
    asm volatile("ld.shared.u32 %0, [%1];" : "=r"(v) : "r"(a2));     // readback (identity)
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
    for (int i = 0; i < 32; i++) if (h[i] < 0 || h[i] >= SMEMW) { fprintf(stderr,"idx OOR %d\n",h[i]); return 2; }

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
