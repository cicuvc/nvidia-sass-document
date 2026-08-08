// demo_kernel.cu — reference kernel for cblaunch (from-scratch cubin launch).
// Kept extern "C" so the cubin's .text section name is plain ".text.demo".
extern "C" __global__ void demo(int *out, int a, int b)
{
    out[threadIdx.x] = a * b + threadIdx.x;
}
