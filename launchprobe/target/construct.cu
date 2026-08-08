// construct.c — from-scratch launch: build const bank + QMD + segment in
// userspace (no replayed template), inject via tracer's injectraw, verify.
//
// Layout in one pinned arena (cudaHostAlloc, UVM => CPU VA == GPU VA):
//   +0x0000  const bank (4KB, zeroed; c[0x0][0x358] desc = 0)
//   +0x1000  kernel code (SASS, from tools/gen_construct_kernel.py)
//   +0x2000  report semaphore (u32, polled from CPU)
// Device memory: QMD staging buffer, QMD semaphore, kernel out buffer.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <dlfcn.h>
#include <unistd.h>
#include <cuda_runtime.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark()
{
    static mark_fn fn = (mark_fn)dlsym(RTLD_DEFAULT, "nvtrace_mark");
    return fn;
}
#define MARK(msg) do { mark_fn f = get_mark(); if (f) f(msg); } while (0)

__global__ void warm() {}

struct Big { uint32_t a[64]; };
// reads c[0x0][i*4] into out[i] (negative dynamic index below param base 0x380)
__global__ void dumpc(__grid_constant__ const Big b, int base_word, int count, uint32_t *out)
{
    #pragma unroll 1
    for (int i = 0; i < count; ++i)
        out[i] = b.a[base_word + i];
}

static void die(const char *what, cudaError_t e)
{
    fprintf(stderr, "[construct] %s: %s\n", what, cudaGetErrorString(e));
    exit(1);
}
#define CK(x) do { cudaError_t e_ = (x); if (e_) die(#x, e_); } while (0)

int main()
{
    MARK("construct start");
    CK(cudaFree(0));
    warm<<<1,1>>>();
    CK(cudaDeviceSynchronize());
    MARK("warmup done");

    // warm-up 2: dump c[0x0] to learn the driver's QMD ring slot device VA
    // (c[0x0][0x148]) — we stage our inline QMD at the NEXT ring slot because
    // the QMD staging address field is only 32 bits (VA>>8) and our own
    // cudaMalloc'd buffers live at 0x7f.. UVM VAs that don't fit.
    uint32_t *cdump;
    CK(cudaMalloc(&cdump, 256 * 4));
    {
        Big dummy{};
        dummy.a[0] = 0xDEADBEEF;
        dumpc<<<1,1>>>(dummy, (0 - 0x380) / 4, 256, cdump);
        CK(cudaDeviceSynchronize());
    }
    uint32_t c0[256];
    CK(cudaMemcpy(c0, cdump, sizeof(c0), cudaMemcpyDeviceToHost));
    uint64_t qmd_ring_slot = ((uint64_t)c0[0x14c / 4] << 32) | c0[0x148 / 4];
    uint64_t stage_va = qmd_ring_slot + 0x800;   // next slot (driver advances +0x800/launch)
    uint64_t qmd_sema_va = stage_va + 0x400;     // unused tail of our staging slot
    fprintf(stderr, "[construct] qmd ring slot=%#lx -> staging at %#lx\n",
            qmd_ring_slot, stage_va);

    // --- allocations ---
    uint8_t *arena;
    CK(cudaHostAlloc((void **)&arena, 1 << 20, cudaHostAllocDefault));
    memset(arena, 0, 1 << 20);
    uint64_t cb_va   = (uint64_t)arena;          // const bank base
    uint64_t code_va = cb_va + 0x1000;
    volatile uint32_t *rep_sema = (volatile uint32_t *)(arena + 0x2000);
    uint64_t rep_sema_va = cb_va + 0x2000;
    arena[0x0f8] = 0xff; arena[0x0f9] = 0xff; arena[0xfa] = 0x0f; // 0x000fffff

    void *out;
    CK(cudaMalloc(&out, 0x100));
    CK(cudaMemset(out, 0, 0x100));
    uint64_t out_va = (uint64_t)out;
    fprintf(stderr, "[construct] arena=%#lx out=%#lx\n", cb_va, out_va);

    // --- kernel code via repo assembler ---
    char cmd[512];
    snprintf(cmd, sizeof cmd,
             "python3 tools/gen_construct_kernel.py %#lx 0xdeadbeef > /tmp/construct_kernel.bin",
             out_va);
    if (system(cmd) != 0) { fprintf(stderr, "[construct] gen failed\n"); return 1; }
    FILE *kf = fopen("/tmp/construct_kernel.bin", "rb");
    if (!kf) { perror("kernel bin"); return 1; }
    size_t klen = fread(arena + 0x1000, 1, 0x1000, kf);
    fclose(kf);
    fprintf(stderr, "[construct] kernel %zu bytes at %#lx\n", klen, code_va);

    // --- QMD (384B) ---
    uint32_t q[96] = {};
    q[0x10/4] = 0x013f0000;                       // version + cache invalidate
    q[0x30/4] = (uint32_t)(stage_va >> 8);        // next-QMD link -> self
    q[0x3c/4] = (uint32_t)qmd_sema_va;            // QMD semaphore VA (raw low32)
    q[0x40/4] = 2;
    q[0x50/4] = 1;                                // QMD sema payload
    q[0x80/4] = (uint32_t)(code_va >> 4);
    q[0x84/4] = (0x120u << 16) | (uint32_t)((code_va >> 36) & 0xffff);
    q[0x88/4] = 0x00010001;                       // blockDim (1,1,_)
    q[0x8c/4] = 0x00000801;                       // blockDim.z=1, regcount=8
    q[0x9c/4] = 1; q[0xa0/4] = 1; q[0xa4/4] = 1;  // gridDim
    q[0xa8/4] = (uint32_t)(cb_va >> 6);           // bank desc 0
    q[0xac/4] = 0x020001fe;
    q[0xb0/4] = (uint32_t)(cb_va >> 6);           // bank desc 1 (ours)
    q[0xb4/4] = 0x048001fe;
    q[0xd0/4] = ((uint32_t)(cb_va >> 6)) | 0xc;   // bank desc 2 (+invalidate?)
    q[0xd4/4] = 0x010001fe;
    q[0xe0/4] = (uint32_t)(cb_va >> 6);           // bank desc 3 (ours)
    q[0xe4/4] = 0x800001fe;
    q[0xe8/4] = 1;                                // enable
    q[0xec/4] = (uint32_t)(code_va >> 8);
    q[0xf0/4] = (uint32_t)(code_va >> 40);

    // --- segment: inline QMD record + report semaphore record ---
    uint32_t seg[1 + 98 + 1 + 4];
    int n = 0;
    seg[n++] = 0x206220c6;                        // hdr: INC cnt=98 subch=1 mthd=0x318
    seg[n++] = 0x40000000;                        // flags (launch)
    seg[n++] = (uint32_t)(stage_va >> 8);         // staging addr>>8
    memcpy(&seg[n], q, 384); n += 96;
    seg[n++] = 0x200426c0;                        // hdr: INC cnt=4 subch=1 mthd=0x1b00
    seg[n++] = (uint32_t)(rep_sema_va >> 32);
    seg[n++] = (uint32_t)(rep_sema_va & 0xffffffff);
    seg[n++] = 0xdead0001;                        // payload
    seg[n++] = 0x04;                              // flags
    FILE *sf = fopen("/tmp/rawseg.bin", "wb");
    fwrite(seg, 4, n, sf);
    fclose(sf);
    fprintf(stderr, "[construct] segment %d dwords written\n", n);

    // --- inject ---
    MARK("injectraw:/tmp/rawseg.bin");

    // --- poll report semaphore ---
    int ok = 0;
    for (int i = 0; i < 2000; i++) {
        if (*rep_sema == 0xdead0001u) { ok = 1; break; }
        usleep(1000);
    }
    fprintf(stderr, "[construct] report sema = %#x (%s)\n", *rep_sema,
            ok ? "SIGNALED" : "TIMEOUT");

    uint32_t h[4] = {};
    cudaError_t e = cudaMemcpy(h, out, 16, cudaMemcpyDeviceToHost);
    fprintf(stderr, "[construct] out = %08x %08x %08x %08x (memcpy %s)\n",
            h[0], h[1], h[2], h[3], e ? cudaGetErrorString(e) : "ok");
    e = cudaDeviceSynchronize();
    if (e) fprintf(stderr, "[construct] post sync err: %s\n", cudaGetErrorString(e));
    fprintf(stderr, "[construct] %s\n",
            (ok && h[0] == 0xdeadbeefu) ? "SUCCESS" : "FAIL");
    return (ok && h[0] == 0xdeadbeefu) ? 0 : 1;
}
