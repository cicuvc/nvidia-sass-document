// ctxprobe.cu — trace ioctl/mmap from context creation through first launch.
// Bare-minimum CUDA init path: primary context -> one launch. Used with
// libnvtrace to capture every RM ioctl and mapping in dependency order.
#include <cstdio>
#include <cstdint>
#include <dlfcn.h>
#include <cuda_runtime.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark(){ static mark_fn f=(mark_fn)dlsym(RTLD_DEFAULT,"nvtrace_mark"); return f; }
#define MARK(msg) do { mark_fn f=get_mark(); if(f) f(msg); } while(0)

__global__ void k(int *out){ out[threadIdx.x] = threadIdx.x + 1; }

int main(){
    MARK("ctx start");
    cudaError_t e = cudaFree(0);          // forces primary context creation
    printf("cudaFree(0): %s\n", cudaGetErrorString(e));
    MARK("ctx created");
    int *d; cudaMalloc(&d, 64);
    k<<<1,4>>>(d);
    e = cudaDeviceSynchronize();
    printf("launch: %s\n", cudaGetErrorString(e));
    int h[4]={}; cudaMemcpy(h,d,16,cudaMemcpyDeviceToHost);
    printf("out=%d %d %d %d\n",h[0],h[1],h[2],h[3]);
    MARK("ctx done");
    return e ? 1 : 0;
}
