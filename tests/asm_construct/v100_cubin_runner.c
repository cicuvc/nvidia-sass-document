#include <cuda.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define CU(call) do {                                                        \
    CUresult _e = (call);                                                     \
    if (_e != CUDA_SUCCESS) {                                                 \
        const char *_s = NULL; cuGetErrorString(_e, &_s);                     \
        fprintf(stderr, "%s failed: %d (%s)\n", #call, (int)_e,              \
                _s ? _s : "unknown");                                       \
        return 2;                                                             \
    }                                                                         \
} while (0)

static void *read_file(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    rewind(f);
    void *p = malloc((size_t)n);
    if (!p || fread(p, 1, (size_t)n, f) != (size_t)n) {
        fclose(f); free(p); return NULL;
    }
    fclose(f); *size = (size_t)n; return p;
}

int main(int argc, char **argv) {
    if (argc < 2 || argc > 4) {
        fprintf(stderr, "usage: %s FILE.cubin [instruction_count] [reps]\n", argv[0]);
        return 1;
    }
    int count = argc > 2 ? atoi(argv[2]) : 512;
    int reps = argc > 3 ? atoi(argv[3]) : 9;
    size_t image_size = 0;
    void *image = read_file(argv[1], &image_size);
    if (!image) { perror(argv[1]); return 1; }

    CUdevice dev; CUcontext ctx; CUmodule mod; CUfunction fn; CUdeviceptr out;
    CU(cuInit(0));
    CU(cuDeviceGet(&dev, 0));
    /* cuCtxCreate gained an incompatible v4 signature in CUDA 13.  The
       primary-context API is stable across the CUDA 12 V100 host and newer
       toolkits used to compile-check this helper. */
    CU(cuDevicePrimaryCtxRetain(&ctx, dev));
    CU(cuCtxSetCurrent(ctx));
    CU(cuModuleLoadData(&mod, image));
    CU(cuModuleGetFunction(&fn, mod, "_Z3thr"));
    CU(cuMemAlloc(&out, 32 * 16));
    CU(cuMemsetD8(out, 0, 32 * 16));
    void *args[] = {&out};
    uint64_t host[2], best = UINT64_MAX;
    for (int r = 0; r <= reps; ++r) {
        CU(cuLaunchKernel(fn, 1, 1, 1, 32, 1, 1, 0, 0, args, NULL));
        CU(cuCtxSynchronize());
        CU(cuMemcpyDtoH(host, out, sizeof(host)));
        uint64_t delta = host[1] - host[0];
        if (r && delta < best) best = delta;
    }
    printf("%s best=%" PRIu64 " cycles cycles/inst=%.6f\n",
           argv[1], best, (double)best / count);
    cuMemFree(out); cuModuleUnload(mod); cuCtxSetCurrent(NULL);
    cuDevicePrimaryCtxRelease(dev); free(image);
    return 0;
}
