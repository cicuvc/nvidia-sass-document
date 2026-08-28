// Force a large set of values to stay live across a runtime loop.  Compile
// this file with different --maxrregcount values to turn register pressure
// into ptxas-generated LDL/STL spills rather than an explicit .local array.

#include <cuda_runtime.h>

extern "C" __global__ void spill_probe(const float *in, float *out, int rounds)
{
    constexpr int N = 96;
    float x[N];
    const unsigned tid = blockIdx.x * blockDim.x + threadIdx.x;

    #pragma unroll
    for (int i = 0; i < N; ++i)
        x[i] = in[tid + i * 256] + float(i + 1);

    #pragma unroll 1
    for (int r = 0; r < rounds; ++r) {
        #pragma unroll
        for (int i = 0; i < N; ++i)
            x[i] = fmaf(x[i], 1.0001f + float(i) * 0.00001f,
                        x[(i + 1) % N]);
    }

    float sum = 0.0f;
    #pragma unroll
    for (int i = 0; i < N; ++i)
        sum += x[i];
    out[tid] = sum;
}

#ifdef RUN_MAIN
#include <cstdio>

int main()
{
    cudaFuncAttributes attr{};
    cudaError_t err = cudaFuncGetAttributes(&attr, spill_probe);
    if (err != cudaSuccess) {
        std::fprintf(stderr, "cudaFuncGetAttributes: %s\n",
                     cudaGetErrorString(err));
        return 1;
    }
    std::printf("numRegs=%d localSizeBytes=%zu maxThreadsPerBlock=%d\n",
                attr.numRegs, attr.localSizeBytes, attr.maxThreadsPerBlock);
    return 0;
}
#endif
