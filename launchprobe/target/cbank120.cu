#include <cstdio>
#include <cstdint>
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

// b.a[] is placed at c[0x0][0x380] on sm_120. b.a[idx] == c[0x0][0x380 + idx*4].
// A negative idx reaches the driver-preset region below the param base.
// #pragma unroll 1 keeps idx dynamic so ptxas's offset checker cannot see
// the out-of-bounds access and demote it to LDG.
__global__ void dumpc(__grid_constant__ const Big b, int base_word, int count, uint32_t *out)
{
    #pragma unroll 1
    for (int i = 0; i < count; ++i)
        out[i] = b.a[base_word + i];
}

int main(int argc, char **argv)
{
    const int PARAM_BASE = 0x380;
    const int start_off  = 0x000;
    const int end_off    = 0x400;
    const int count      = (end_off - start_off) / 4;
    const int base_word  = (start_off - PARAM_BASE) / 4;

    MARK("cbank120 start");
    uint32_t *d; cudaMalloc(&d, count * sizeof(uint32_t));
    Big dummy{};
    dummy.a[0] = 0xDEADBEEF; dummy.a[1] = 0xCAFEBABE;
    dummy.a[2] = 0x12345678; dummy.a[3] = 0xA5A5A5A5;
    MARK("dump launch");
    dumpc<<<dim3(3,5,7), dim3(2,4,6), 3072>>>(dummy, base_word, count, d);
    cudaError_t e = cudaDeviceSynchronize();
    MARK("dump done");
    if (e) { printf("launch err: %s\n", cudaGetErrorString(e)); return 1; }

    uint32_t *h = new uint32_t[count];
    cudaMemcpy(h, d, count * sizeof(uint32_t), cudaMemcpyDeviceToHost);
    FILE *f = fopen("/tmp/cbank120_dump.bin", "wb");
    fwrite(h, 4, count, f);
    fclose(f);

    printf("=== c[0x0] dump (sm_120) ===\n");
    for (int i = 0; i < count; ++i) {
        int off = start_off + i * 4;
        const char *tag = "";
        if (off == 0x380) tag = "  <- param base (sentinel check)";
        if (h[i]) printf("c[0x0][0x%03x] = 0x%08x%s\n", off, h[i], tag);
    }
    cudaFree(d);
    return 0;
}
