#include <stdio.h>
#include <dlfcn.h>
#include <cuda_runtime.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark(void)
{
    return (mark_fn)dlsym(RTLD_DEFAULT, "nvtrace_mark");
}
#define MARK(msg) do { mark_fn f = get_mark(); if (f) f(msg); } while (0)

__global__ void k_ptr(float *x) { if (threadIdx.x == 0 && x) x[blockIdx.x] += 1.0f; }
__global__ void k_sub(float *x) { if (threadIdx.x == 0 && x) x[blockIdx.x] -= 1.0f; }
__global__ void k_stk(float *x)
{
    float arr[512];
    for (int i = 0; i < 512; i++) arr[i] = i * 0.5f;
    float acc = 0;
#pragma unroll 1
    for (int r = 0; r < 4; r++)
        for (int i = 0; i < 512; i++) acc += arr[(i + threadIdx.x + r) & 511];
    if (threadIdx.x == 0 && x) x[blockIdx.x] += acc;
}

int main(int argc, char **argv)
{
    const char *inject_msg = argc > 1 ? argv[1] : "inject";
    MARK("injectprobe start");
    float *dx;
    cudaMalloc(&dx, 4096);
    cudaMemset(dx, 0, 4096);
    MARK("setup done");

    MARK("sub launch");
    k_sub<<<2, 32>>>(dx);
    cudaDeviceSynchronize();

    MARK("normal launch");
    k_ptr<<<2, 32>>>(dx);
    MARK("stk launch");
    k_stk<<<2, 32>>>(dx + 4);
    cudaDeviceSynchronize();
    float v[8];
    cudaMemcpy(v, dx, sizeof(v), cudaMemcpyDeviceToHost);
    fprintf(stderr, "[injectprobe] after normal launch: ptr=[%.0f %.0f] stk=[%.0f %.0f]\n",
            v[0], v[1], v[4], v[5]);

    for (int i = 1; i < argc; i++) MARK(argv[i]);
    MARK("after inject");
    cudaDeviceSynchronize();
    cudaMemcpy(v, dx, sizeof(v), cudaMemcpyDeviceToHost);
    fprintf(stderr, "[injectprobe] after inject: ptr=[%.0f %.0f] stk=[%.0f %.0f]\n",
            v[0], v[1], v[4], v[5]);

    cudaFree(dx);
    return 0;
}
