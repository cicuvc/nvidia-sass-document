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

__global__ void vecadd(const float *a, const float *b, float *c, int n)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}

__global__ void dummy2(float *x, long k)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < k) x[i] += 1.0f;
}

int main()
{
    MARK("main start");
    int n = 1 << 20;
    size_t bytes = n * sizeof(float);
    float *ha = new float[n], *hb = new float[n], *hc = new float[n];
    for (int i = 0; i < n; i++) { ha[i] = i * 1.0f; hb[i] = i * 2.0f; }

    float *da, *db, *dc;
    cudaMalloc(&da, bytes); cudaMalloc(&db, bytes); cudaMalloc(&dc, bytes);
    MARK("cudaMalloc done");
    cudaMemcpy(da, ha, bytes, cudaMemcpyHostToDevice);
    MARK("memcpy H2D da done");
    cudaMemcpy(db, hb, bytes, cudaMemcpyHostToDevice);
    MARK("memcpy H2D db done");

    for (int iter = 0; iter < 10; iter++) {
        char msg[64];
        snprintf(msg, sizeof(msg), "launch %d begin", iter);
        MARK(msg);
        vecadd<<<(n + 255) / 256, 256>>>(da, db, dc, n);
        snprintf(msg, sizeof(msg), "launch %d submitted", iter);
        MARK(msg);
    }
    cudaDeviceSynchronize();
    MARK("all synced");

    cudaMemcpy(hc, dc, bytes, cudaMemcpyDeviceToHost);
    bool ok = true;
    for (int i = 0; i < n; i++) if (hc[i] != ha[i] + hb[i]) { ok = false; break; }
    fprintf(stderr, "[vecadd] %s\n", ok ? "PASS" : "FAIL");

    MARK("dummy2 begin");
    dummy2<<<17, 128>>>(dc, 128 * 17);
    MARK("dummy2 submitted");
    cudaDeviceSynchronize();
    MARK("dummy2 synced");

    cudaFree(da); cudaFree(db); cudaFree(dc);
    delete[] ha; delete[] hb; delete[] hc;
    return ok ? 0 : 1;
}
