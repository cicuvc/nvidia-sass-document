// Exact reproduction of the Zhihu cp.async kernel (conflict-free smem dst,
// stride-32-float scattered global source).
#include <cstdio>
#include <cuda_runtime.h>

__global__ void cp_async_test_kernel_2(float* d_ptr, int gstride) {
    __shared__ float smem[1024];
    int tid = threadIdx.x;
    float const* gmem_ptr = d_ptr + tid * gstride;          // SOURCE: stride gstride floats
    unsigned smem_int_ptr = (unsigned)__cvta_generic_to_shared(smem + 4 * tid);  // DEST: consecutive
    asm volatile("cp.async.ca.shared.global.L2::128B [%0], [%1], %2;\n"
                 :: "r"(smem_int_ptr), "l"(gmem_ptr), "n"(16) : "memory");
    asm volatile("cp.async.commit_group;\n" ::);
    asm volatile("cp.async.wait_group 0;\n" ::: "memory");
    __syncthreads();
    if (tid == 999999) d_ptr[0] = smem[tid];                // keep smem live
}

int main(int argc, char** argv) {
    int blk = argc > 1 ? atoi(argv[1]) : 256;
    int gstride = argc > 2 ? atoi(argv[2]) : 32;            // source stride in floats
    float* d;
    size_t n = (size_t)blk * (gstride + 4) + 64;
    cudaMalloc(&d, n * sizeof(float));
    cudaMemset(d, 0, n * sizeof(float));
    cp_async_test_kernel_2<<<1, blk>>>(d, gstride);
    cudaError_t e = cudaDeviceSynchronize();
    if (e != cudaSuccess) { fprintf(stderr, "err: %s\n", cudaGetErrorString(e)); return 1; }
    return 0;
}
