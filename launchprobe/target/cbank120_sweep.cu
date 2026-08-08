#include <cstdio>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <cuda_runtime.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark()
{
    static mark_fn fn = (mark_fn)dlsym(RTLD_DEFAULT, "nvtrace_mark");
    return fn;
}
#define MARK(msg) do { mark_fn f = get_mark(); if (f) f(msg); } while (0)

struct Big { uint32_t a[64]; };

__global__ void dumpc(__grid_constant__ const Big b, int base_word, int count, uint32_t *out)
{
    #pragma unroll 1
    for (int i = 0; i < count; ++i)
        out[i] = b.a[base_word + i];
}

static const int PARAM_BASE = 0x380;
static const int START = 0x000, END = 0x400;
static const int COUNT = (END - START) / 4;
static const int BASE_WORD = (START - PARAM_BASE) / 4;

static uint32_t *dout, *host;
static Big dummy;

static bool run_one(const char *name, dim3 grid, dim3 block, int smem,
                    const cudaLaunchAttribute *attrs, int nattrs, bool coop)
{
    char m[128]; snprintf(m, sizeof m, "launch %s", name); MARK(m);
    cudaError_t e;
    if (coop) {
        void *params[] = {&dummy, (void *)&BASE_WORD, (void *)&COUNT, &dout};
        e = cudaLaunchCooperativeKernel((void *)dumpc, grid, block, params, smem, 0);
    } else {
        cudaLaunchConfig_t cfg = {};
        cfg.gridDim = grid; cfg.blockDim = block; cfg.dynamicSmemBytes = smem;
        cfg.attrs = (cudaLaunchAttribute *)attrs; cfg.numAttrs = nattrs;
        e = cudaLaunchKernelEx(&cfg, dumpc, dummy, BASE_WORD, COUNT, dout);
    }
    if (e) { printf("[%s] launch err: %s\n", name, cudaGetErrorString(e)); return false; }
    e = cudaDeviceSynchronize();
    if (e) { printf("[%s] sync err: %s\n", name, cudaGetErrorString(e)); return false; }
    snprintf(m, sizeof m, "done %s", name); MARK(m);

    uint32_t *h = new uint32_t[COUNT];
    cudaMemcpy(h, dout, COUNT * 4, cudaMemcpyDeviceToHost);
    char path[128]; snprintf(path, sizeof path, "/tmp/cbank120_%s.bin", name);
    FILE *f = fopen(path, "wb"); fwrite(h, 4, COUNT, f); fclose(f);
    if (h[0x380 / 4] != 0xDEADBEEF) printf("[%s] WARN sentinel missing: %08x\n", name, h[0x380 / 4]);
    if (!host) { host = h; return true; }   // first = baseline, keep

    printf("=== diff baseline -> %s ===\n", name);
    for (int i = 0; i < COUNT; ++i)
        if (h[i] != host[i])
            printf("c[0x0][0x%03x]: %08x -> %08x\n", i * 4, host[i], h[i]);
    delete[] h;
    return true;
}

int main()
{
    MARK("cbank120 sweep start");
    dummy.a[0] = 0xDEADBEEF; dummy.a[1] = 0xCAFEBABE;
    dummy.a[2] = 0x12345678; dummy.a[3] = 0xA5A5A5A5;
    cudaMalloc(&dout, COUNT * 4);

    // baseline: same shape as previous probe
    run_one("base", dim3(3,5,7), dim3(2,4,6), 3072, nullptr, 0, false);

    // cluster(2,1,1), grid multiple of cluster
    cudaLaunchAttribute c2[1];
    c2[0].id = cudaLaunchAttributeClusterDimension;
    c2[0].val.clusterDim.x = 2; c2[0].val.clusterDim.y = 1; c2[0].val.clusterDim.z = 1;
    run_one("clu2", dim3(6,5,7), dim3(2,4,6), 3072, c2, 1, false);

    // cluster(4,2,1) = 8 CTAs (portable max), asymmetric to separate x/y
    cudaLaunchAttribute c42[1];
    c42[0].id = cudaLaunchAttributeClusterDimension;
    c42[0].val.clusterDim.x = 4; c42[0].val.clusterDim.y = 2; c42[0].val.clusterDim.z = 1;
    run_one("clu42", dim3(12,10,7), dim3(2,4,6), 3072, c42, 1, false);

    // cluster(1,1,2): z-axis only
    cudaLaunchAttribute cz[1];
    cz[0].id = cudaLaunchAttributeClusterDimension;
    cz[0].val.clusterDim.x = 1; cz[0].val.clusterDim.y = 1; cz[0].val.clusterDim.z = 2;
    run_one("cluz", dim3(3,5,14), dim3(2,4,6), 3072, cz, 1, false);

    // cooperative launch (small co-resident grid)
    run_one("coop", dim3(2,1,1), dim3(64,1,1), 0, nullptr, 0, true);

    cudaFree(dout);
    return 0;
}
