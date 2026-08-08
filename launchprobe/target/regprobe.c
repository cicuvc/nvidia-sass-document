#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
#include <cuda.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark(void)
{
    return (mark_fn)dlsym(RTLD_DEFAULT, "nvtrace_mark");
}
#define MARK(msg) do { mark_fn f = get_mark(); if (f) f(msg); } while (0)

#define CU(x) do { CUresult r = (x); if (r != CUDA_SUCCESS) { \
    const char *s; cuGetErrorName(r, &s); \
    fprintf(stderr, "CUDA error %s at %s:%d\n", s, __FILE__, __LINE__); return 1; } } while (0)

int main()
{
    MARK("regprobe start");
    CU(cuInit(0));
    CUdevice dev;
    CU(cuDeviceGet(&dev, 0));
    CUcontext ctx;
    CU(cuCtxCreate(&ctx, 0, dev));
    CUdeviceptr dx;
    CU(cuMemAlloc(&dx, 1 << 20));
    MARK("setup done");

    const char *mods[] = {
        "regs/reg_r8.cubin", "regs/reg_r16.cubin", "regs/reg_r24.cubin",
        "regs/reg_r32.cubin", "regs/reg_r40.cubin", "regs/reg_r64.cubin",
        "regs/stk_s256.cubin", "regs/stk_s512.cubin", "regs/stk_s1024.cubin",
        "regs/stk_s2048.cubin",
    };
    char msg[128];
    for (int i = 0; i < (int)(sizeof(mods) / sizeof(mods[0])); i++) {
        CUmodule m;
        if (cuModuleLoad(&m, mods[i]) != CUDA_SUCCESS) {
            fprintf(stderr, "skip %s (load failed)\n", mods[i]);
            continue;
        }
        CUfunction f;
        CU(cuModuleGetFunction(&f, m, "kern"));
        snprintf(msg, sizeof(msg), "L%02d %s b64", i, mods[i]);
        MARK(msg);
        unsigned long long arg = dx;
        void *params[] = { &arg };
        CUresult r = cuLaunchKernel(f, 2, 1, 1, 64, 1, 1, 0, 0, params, 0);
        if (r != CUDA_SUCCESS) { const char *s; cuGetErrorName(r, &s); fprintf(stderr, "launch %s: %s\n", mods[i], s); }
        snprintf(msg, sizeof(msg), "L%02d submitted", i);
        MARK(msg);
    }
    CU(cuCtxSynchronize());
    MARK("all synced");
    fprintf(stderr, "[regprobe] done\n");
    return 0;
}
