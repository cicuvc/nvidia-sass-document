// multilaunch.cu — submit N async launches on one stream, verify each kernel
// reads its OWN params from the const bank (not a neighbor's). Exposes how the
// driver sizes the bank ring vs in-flight (queued) launches.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cuda_runtime.h>
#include <dlfcn.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark(){ static mark_fn f=(mark_fn)dlsym(RTLD_DEFAULT,"nvtrace_mark"); return f; }
#define MARK(msg) do { mark_fn f=get_mark(); if(f) f(msg); } while(0)

__global__ void probe(int tag, int a, int b, int *out)
{
    out[threadIdx.x] = a * b + tag + threadIdx.x;
}

int main(int argc, char **argv)
{
    int N = argc > 1 ? atoi(argv[1]) : 32;
    MARK("ml start");
    cudaFree(0);
    { int *tmp; cudaMalloc(&tmp, 64); probe<<<1,4>>>(0,1,1,tmp); cudaFree(tmp); }
    cudaDeviceSynchronize();
    MARK("ml warm");

    int *dout;
    cudaMalloc(&dout, N * 64);
    cudaMemset(dout, 0, N * 64);

    MARK("ml submit begin");
    for (int i = 0; i < N; i++)
        probe<<<1,4>>>(i, i + 1, i + 2, dout + i * 16);
    MARK("ml submit end");

    cudaError_t e = cudaDeviceSynchronize();
    printf("sync: %s\n", cudaGetErrorString(e));

    int h[1024] = {};
    cudaMemcpy(h, dout, N * 16, cudaMemcpyDeviceToHost);
    int bad = 0;
    for (int i = 0; i < N; i++) {
        int exp = (i + 1) * (i + 2) + i;
        for (int t = 0; t < 4; t++)
            if (h[i*4+t] != exp + t) { bad++; if (bad < 8) printf("  mismatch i=%d t=%d got=%d exp=%d\n", i, t, h[i*4+t], exp+t); }
    }
    printf("N=%d: %s (%d bad)\n", N, bad ? "CORRUPTED" : "OK", bad);
    MARK("ml done");
    return bad ? 1 : 0;
}
