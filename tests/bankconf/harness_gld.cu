// Global L1 data-array bank-conflict probe.
// One warp. Each thread reads global word index gidx[t] via LDG in a loop so the
// data is L1-resident (steady-state hits); volatile asm => re-executed each iter.
// Measures the L1 *global* read bank conflict (mem_gds_op_ld) vs the access pattern,
// to derive the condition under which scattered global reads conflict.
//
// Build: -DVEC={1,4} (1 => ld.global.ca.u32 ; 4 => ld.global.ca.v4.u32).
// Usage: harness_gld <mode-ignored> <patternfile> <iters>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#ifndef VEC
#define VEC 1
#endif
#ifndef GWIN
#define GWIN 8
#endif

__global__ void kern(const int* __restrict__ gidx, const int* __restrict__ gdata,
                     int* __restrict__ out, int iters, int win) {
    int t = threadIdx.x;
    const int* base = gdata + gidx[t];
    int acc = 0;
    for (int i = 0; i < iters; i++) {
        const int* p = base + (size_t)(i & (GWIN - 1)) * win;   // cycle L1-resident windows
#if VEC == 4
        int a, b, c, d;
        asm volatile("ld.global.ca.v4.u32 {%0,%1,%2,%3}, [%4];"
                     : "=r"(a), "=r"(b), "=r"(c), "=r"(d) : "l"(p));
        acc += a + b + c + d;
#else
        int v;
        asm volatile("ld.global.ca.u32 %0, [%1];" : "=r"(v) : "l"(p));
        acc += v;
#endif
    }
    out[t] = acc;
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s <mode> <patternfile> [iters]\n", argv[0]); return 2; }
    int iters = argc > 3 ? atoi(argv[3]) : 2000;
    FILE* f = fopen(argv[2], "r");
    if (!f) { perror("fopen"); return 2; }
    int h[32], maxi = 0;
    for (int i = 0; i < 32; i++) { if (fscanf(f, "%d", &h[i]) != 1) { fprintf(stderr,"bad @%d\n",i); return 2; } if (h[i] > maxi) maxi = h[i]; }
    fclose(f);
    size_t win = (size_t)maxi + 4;
    size_t words = win * GWIN + 16;
    int *didx, *dout, *ddata;
    cudaMalloc(&didx, 32 * sizeof(int));
    cudaMalloc(&dout, 32 * sizeof(int));
    cudaMalloc(&ddata, words * sizeof(int));
    cudaMemset(ddata, 0, words * sizeof(int));
    cudaMemcpy(didx, h, 32 * sizeof(int), cudaMemcpyHostToDevice);
    kern<<<1, 32>>>(didx, ddata, dout, iters, (int)win);
    cudaError_t e = cudaDeviceSynchronize();
    if (e != cudaSuccess) { fprintf(stderr, "launch err: %s\n", cudaGetErrorString(e)); return 1; }
    return 0;
}
