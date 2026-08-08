// demo2_kernel.cu — second cubin for Phase 11 "other kernel" verification.
extern "C" __global__ void demo2(int *out, int a, int b)
{
    out[threadIdx.x] = a * b - threadIdx.x;
}
