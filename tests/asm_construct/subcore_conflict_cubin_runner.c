#include <cuda.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define CU(call) do {                                                        \
    CUresult _e = (call);                                                     \
    if (_e != CUDA_SUCCESS) {                                                 \
        const char *_s = NULL; cuGetErrorString(_e, &_s);                     \
        fprintf(stderr, "%s failed: %d (%s)\n", #call, (int)_e,             \
                _s ? _s : "unknown");                                       \
        return 2;                                                             \
    }                                                                         \
} while (0)

static void *read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    rewind(f);
    void *p = malloc((size_t)n);
    if (!p || fread(p, 1, (size_t)n, f) != (size_t)n) {
        fclose(f); free(p); return NULL;
    }
    fclose(f);
    return p;
}

int main(int argc, char **argv) {
    if (argc != 6) {
        fprintf(stderr, "usage: %s FILE.cubin N CONTENDER_WARP KIND REPS\n",
                argv[0]);
        return 1;
    }
    int n = atoi(argv[2]);
    int contender_warp = atoi(argv[3]);
    int kind = atoi(argv[4]);
    int reps = atoi(argv[5]);
    void *image = read_file(argv[1]);
    if (!image) { perror(argv[1]); return 1; }

    CUdevice dev;
    CUcontext ctx;
    CUmodule mod;
    CUfunction fn;
    CUdeviceptr out;
    CU(cuInit(0));
    CU(cuDeviceGet(&dev, 0));
    CU(cuDevicePrimaryCtxRetain(&ctx, dev));
    CU(cuCtxSetCurrent(ctx));
    CU(cuModuleLoadData(&mod, image));
    CU(cuModuleGetFunction(&fn, mod, "_Z6scconf"));
    CU(cuMemAlloc(&out, 256 * 16));
    CU(cuMemsetD8(out, 0, 256 * 16));

    void *args[] = {&out, &contender_warp, &kind};
    uint64_t times[2];
    uint64_t best = UINT64_MAX;
    for (int r = 0; r <= reps; ++r) {
        CU(cuLaunchKernel(fn, 1, 1, 1, 256, 1, 1, 0, 0, args, NULL));
        CU(cuCtxSynchronize());
        CU(cuMemcpyDtoH(times, out, sizeof(times)));
        uint64_t delta = times[1] - times[0];
        if (r && delta < best) best = delta;
    }
    printf("%s n=%d cw=%d kind=%d best=%" PRIu64 " cpi=%.6f\n",
           argv[1], n, contender_warp, kind, best, (double)best / n);

    cuMemFree(out);
    cuModuleUnload(mod);
    cuCtxSetCurrent(NULL);
    cuDevicePrimaryCtxRelease(dev);
    free(image);
    return 0;
}
