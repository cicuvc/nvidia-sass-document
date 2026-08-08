#include <cstdio>
#include <dlfcn.h>
#include <cuda_runtime.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark()
{
    static mark_fn fn = (mark_fn)dlsym(RTLD_DEFAULT, "nvtrace_mark");
    return fn;
}
#define MARK(msg) do { mark_fn f = get_mark(); if (f) f(msg); } while (0)

__global__ void k_void() {}

__global__ void k_ptr(float *x) { if (threadIdx.x == 0 && x) x[0] += 1.0f; }

__global__ void k_ints(int a, long b, short c, char d)
{
    if (threadIdx.x > 1024) printf("%d %ld %d %d", a, b, c, d);
}

__global__ void k_shared_static()
{
    __shared__ float s[1024];
    s[threadIdx.x] = threadIdx.x;
    __syncthreads();
    if (threadIdx.x > 1024) printf("%f", s[0]);
}

__global__ void k_shared_dyn()
{
    extern __shared__ float s[];
    s[threadIdx.x] = threadIdx.x;
    __syncthreads();
    if (threadIdx.x > 1024) printf("%f", s[0]);
}

__global__ void __launch_bounds__(64, 8) k_regs64(float *x)
{
    float a[8];
    for (int i = 0; i < 8; i++) a[i] = x ? x[i] : i;
    for (int r = 0; r < 16; r++)
        for (int i = 0; i < 8; i++) a[i] = a[i] * 1.0001f + a[(i + 1) & 7];
    float acc = 0;
    for (int i = 0; i < 8; i++) acc += a[i];
    if (x) x[threadIdx.x] = acc;
}

__global__ void k_local(float *x)
{
    float arr[64];
    for (int i = 0; i < 64; i++) arr[i] = i * 0.5f;
    float acc = 0;
    for (int i = 0; i < 64; i++) acc += arr[(i + threadIdx.x) & 63];
    if (x) x[threadIdx.x] = acc;
}

__global__ void k_barrier(float *x)
{
    __shared__ float s[256];
    s[threadIdx.x] = threadIdx.x;
    __syncthreads();
    float v = s[(threadIdx.x + 1) & 255];
    __syncthreads();
    if (x) x[threadIdx.x] = v;
}

__global__ void __cluster_dims__(2, 1, 1) k_cluster(float *x)
{
    if (x) x[threadIdx.x] += 1.0f;
}

__global__ void k_printf()
{
    if (threadIdx.x == 0) printf("hello from k_printf %d\n", blockIdx.x);
}

struct BigParams {
    float *p0, *p1, *p2, *p3;
    long a, b, c, d;
    int e, f, g, h;
};

__global__ void k_manyparams(BigParams bp)
{
    if (threadIdx.x > 1024)
        printf("%p %ld %d", bp.p0, bp.a, bp.e);
}

int main()
{
    MARK("qmdprobe start");
    float *dx;
    cudaMalloc(&dx, 1 << 20);
    cudaFuncSetAttribute(k_shared_dyn, cudaFuncAttributeMaxDynamicSharedMemorySize, 100 * 1024);
    MARK("setup done");

    MARK("L00 k_void 1x1x1 1x1x1");
    k_void<<<1, 1>>>();
    MARK("L01 k_void g3,5,7 b2,3,4");
    k_void<<<dim3(3, 5, 7), dim3(2, 3, 4)>>>();
    MARK("L02 k_void g1000,1,1 b128,1,1");
    k_void<<<1000, 128>>>();
    MARK("L03 k_ptr g4 b32");
    k_ptr<<<4, 32>>>(dx);
    MARK("L04 k_ints g1 b1");
    k_ints<<<1, 1>>>(42, 0x123456789abcdef0L, -7, 65);
    MARK("L05 k_shared_static g2 b256");
    k_shared_static<<<2, 256>>>();
    MARK("L06 k_shared_dyn 8K g2 b256");
    k_shared_dyn<<<2, 256, 8192>>>();
    MARK("L07 k_shared_dyn 100K g1 b128");
    k_shared_dyn<<<1, 128, 100 * 1024>>>();
    MARK("L08 k_regs64 g4 b64");
    k_regs64<<<4, 64>>>(dx);
    MARK("L09 k_local g2 b128");
    k_local<<<2, 128>>>(dx);
    MARK("L10 k_barrier g2 b256");
    k_barrier<<<2, 256>>>(dx);
    MARK("L11 k_cluster g4 b64");
    k_cluster<<<4, 64>>>(dx);
    MARK("L12 k_printf g3 b32");
    k_printf<<<3, 32>>>();
    MARK("L13 k_manyparams g1 b1");
    BigParams bp = {dx, dx, dx, dx, 1, 2, 3, 4, 5, 6, 7, 8};
    k_manyparams<<<1, 1>>>(bp);

    cudaDeviceSynchronize();
    MARK("all synced");
    cudaFree(dx);
    fprintf(stderr, "[qmdprobe] done\n");
    return 0;
}
