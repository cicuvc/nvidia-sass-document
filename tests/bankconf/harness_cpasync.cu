// cp.async (LDGSTS) shared-write bank-conflict probe.
// One warp, one cp.async per thread: copies CPSZ bytes global->shared, with the
// per-thread DESTINATION shared WORD index from a file. Source is coalesced.
// The shared-WRITE side is what can bank-conflict (op_ldgsts counters).
//
// Build: -DCPSZ={4,8,16} -DCG={0,1}  (CG=1 => cp.async.cg, bypass L1; only CPSZ=16)
// Usage: harness_cpasync <ld|st ignored> <patternfile>   (arg1 kept for driver parity)
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#ifndef CPSZ
#define CPSZ 16
#endif
#ifndef CG
#define CG 0
#endif
#ifndef SRCSTRIDE
#define SRCSTRIDE 1
#endif
#ifndef SMEMW
#define SMEMW 8192
#endif

__global__ void kern(const int* __restrict__ idx, const char* __restrict__ gsrc,
                     int* __restrict__ out) {
    __shared__ __align__(16) int smem[SMEMW];
    int t = threadIdx.x;
    unsigned sa = (unsigned)__cvta_generic_to_shared(&smem[idx[t]]);
    const void* gp = gsrc + (size_t)t * CPSZ * SRCSTRIDE;
#if CG
    asm volatile("cp.async.cg.shared.global [%0], [%1], %2;" :: "r"(sa), "l"(gp), "n"(CPSZ));
#else
    asm volatile("cp.async.ca.shared.global [%0], [%1], %2;" :: "r"(sa), "l"(gp), "n"(CPSZ));
#endif
    asm volatile("cp.async.commit_group;");
    asm volatile("cp.async.wait_group 0;");
    __syncthreads();
    out[t] = smem[t];
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s <mode> <patternfile>\n", argv[0]); return 2; }
    FILE* f = fopen(argv[2], "r");
    if (!f) { perror("fopen"); return 2; }
    int h[32];
    for (int i = 0; i < 32; i++) { if (fscanf(f, "%d", &h[i]) != 1) { fprintf(stderr,"bad @%d\n",i); return 2; } }
    fclose(f);
    int align_words = CPSZ / 4;
    for (int i = 0; i < 32; i++)
        if (h[i] < 0 || h[i] >= SMEMW - align_words || (h[i] % align_words)) {
            fprintf(stderr, "idx bad (need mult %d, in-range): %d\n", align_words, h[i]); return 2; }

    int *didx, *dout; char* dsrc;
    cudaMalloc(&didx, 32 * sizeof(int));
    cudaMalloc(&dout, 32 * sizeof(int));
    cudaMalloc(&dsrc, (size_t)32 * CPSZ * SRCSTRIDE + 256);
    cudaMemset(dsrc, 0, (size_t)32 * CPSZ * SRCSTRIDE + 256);
    cudaMemcpy(didx, h, 32 * sizeof(int), cudaMemcpyHostToDevice);
    kern<<<1, 32>>>(didx, dsrc, dout);
    cudaError_t e = cudaDeviceSynchronize();
    if (e != cudaSuccess) { fprintf(stderr, "launch err: %s\n", cudaGetErrorString(e)); return 1; }
    return 0;
}
