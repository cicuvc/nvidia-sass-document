// cp.async L1-fill-bank vs shared-write-bank ALIGNMENT probe.
// dst = smem + 4*tid (consec, conflict-free). src = d + woff + 4*tid (+stream),
// coalesced (conflict-free on its own). woff shifts the L1-fill bank vs the
// shared-write bank by (woff % 32). stream=1 => every access misses (fills L1);
// stream=0 => small window, L1-resident (hits, no fill).
// Hypothesis: if fill+shared-write co-enable the same bank, woff%32!=0 costs more.
#include <cstdio>
#include <cuda_runtime.h>

__global__ void k(const float* __restrict__ d, float* __restrict__ out,
                  int woff, int iters, int stream) {
    __shared__ __align__(128) float smem[4096];
    int tid = threadIdx.x;
    unsigned sdst = (unsigned)__cvta_generic_to_shared(smem + 4 * tid);
    float keep = 0.f;
    for (int i = 0; i < iters; i++) {
        long off = (long)woff + 4 * tid + (stream ? (long)i * 1024 : (long)(i & 7) * 128);
        const float* src = d + off;
        asm volatile("cp.async.ca.shared.global.L2::128B [%0], [%1], %2;\n"
                     :: "r"(sdst), "l"(src), "n"(16) : "memory");
        asm volatile("cp.async.commit_group;\n");
        asm volatile("cp.async.wait_group 0;\n" ::: "memory");
    }
    __syncthreads();
    keep = smem[tid & 127];
    out[tid] = keep;
}

int main(int argc, char** argv) {
    int woff   = argc > 1 ? atoi(argv[1]) : 0;
    int iters  = argc > 2 ? atoi(argv[2]) : 2000;
    int stream = argc > 3 ? atoi(argv[3]) : 0;
    const float* d;
    size_t words = stream ? ((size_t)iters * 1024 + woff + 8192)
                          : ((size_t)8 * 128 + woff + 8192);
    float *dd, *out;
    cudaMalloc(&dd, words * sizeof(float));
    cudaMalloc(&out, 256 * sizeof(float));
    cudaMemset(dd, 0, words * sizeof(float));
    d = dd;
    k<<<1, 32>>>(d, out, woff, iters, stream);
    cudaError_t e = cudaDeviceSynchronize();
    if (e != cudaSuccess) { fprintf(stderr, "err: %s\n", cudaGetErrorString(e)); return 1; }
    return 0;
}
