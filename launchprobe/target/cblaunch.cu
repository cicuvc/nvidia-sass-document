// cblaunch.cu — from-scratch launch of a real nvcc-compiled cubin kernel
// (SASS extracted from target/demo_kernel.cubin at runtime).
//
// Plan D (current working scheme): the reference launch demo(d_out, pa, pb)
// makes the DRIVER write {d_out, pa, pb} into its own const bank (GPU VA
// < 2^38, in the SM's constant-accessible domain). Our injected QMD reuses
// the SAME bank descriptors (captured from the driver's launch segment), so
// the SM reads the exact params we want — no bank writes needed.
//
// We tried (and ruled out, empirically this session):
//   - bank in own UVM arena (0x7f..): QMD descriptors encode only VA[37:6],
//     truncation aliases to random driver memory -> garbage params / fault.
//   - low-VA mmap + cudaHostRegister: GPU DMA (cudaMemcpy/CE) can read it,
//     but the SM's constant path (LDC c[0x0]) cannot -> params read as 0.
//     So a user-space host mapping is NOT in the constant-accessible domain.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <dlfcn.h>
#include <dirent.h>
#include <unistd.h>
#include <sys/mman.h>
#include <cuda_runtime.h>

#include "demo_kernel.cu"   // linked-in reference copy of `demo`
#include "demo2_kernel.cu"  // linked-in reference copy of `demo2`

typedef void (*mark_fn)(const char *);
static mark_fn get_mark()
{
    static mark_fn fn = (mark_fn)dlsym(RTLD_DEFAULT, "nvtrace_mark");
    return fn;
}
#define MARK(msg) do { mark_fn f = get_mark(); if (f) f(msg); } while (0)

__global__ void warm() {}

struct Big { uint32_t a[64]; };
__global__ void dumpc(__grid_constant__ const Big b, int base_word, int count, uint32_t *out)
{
    #pragma unroll 1
    for (int i = 0; i < count; ++i)
        out[i] = b.a[base_word + i];
}

static void die(const char *what, cudaError_t e)
{
    fprintf(stderr, "[cblaunch] %s: %s\n", what, cudaGetErrorString(e));
    exit(1);
}
#define CK(x) do { cudaError_t e_ = (x); if (e_) die(#x, e_); } while (0)

int main()
{
    MARK("cblaunch start");
    CK(cudaFree(0));
    warm<<<1,1>>>();
    CK(cudaDeviceSynchronize());

    // learn driver QMD ring slot (c[0x0][0x148])
    uint32_t *cdump;
    CK(cudaMalloc(&cdump, 256 * 4));
    {
        Big dummy{};
        dumpc<<<1,1>>>(dummy, (0 - 0x380) / 4, 256, cdump);
        CK(cudaDeviceSynchronize());
    }
    uint32_t c0[256];
    CK(cudaMemcpy(c0, cdump, sizeof(c0), cudaMemcpyDeviceToHost));
    uint64_t stage_va = (((uint64_t)c0[0x14c / 4] << 32) | c0[0x148 / 4]) + 0x800;
    uint64_t qmd_sema_va = stage_va + 0x400;

    // reference launch: driver writes {d_out, pa, pb} into ITS const bank.
    // CB_KERNEL=demo2 switches to the second cubin (same param layout).
    int pa = 7, pb = 9;
    if (getenv("CB_A")) pa = atoi(getenv("CB_A"));
    if (getenv("CB_B")) pb = atoi(getenv("CB_B"));
    const char *kname = getenv("CB_KERNEL") ? getenv("CB_KERNEL") : "demo";
    int is_demo2 = strcmp(kname, "demo2") == 0;
    const char *cubin_path = is_demo2 ? "target/demo2_kernel.cubin" : "target/demo_kernel.cubin";
    int *d_ref, *d_out;
    CK(cudaMalloc(&d_ref, 16));
    CK(cudaMalloc(&d_out, 256));
    CK(cudaMemset(d_ref, 0, 16));
    CK(cudaMemset(d_out, 0, 256));
    if (is_demo2) demo2<<<1,4>>>(d_out, pa, pb);
    else          demo <<<1,4>>>(d_out, pa, pb);
    CK(cudaDeviceSynchronize());
    MARK("reference done");
    CK(cudaMemset(d_out, 0, 256));
    CK(cudaDeviceSynchronize());

    // extract SASS from the cubin file (CB_CODE env overrides for bisection)
    const char *code_path = getenv("CB_CODE");
    if (!code_path) {
        char cmd[512];
        snprintf(cmd, sizeof cmd, "python3 tools/extract_cubin.py %s %s /tmp/cblaunch_code.bin",
                 cubin_path, kname);
        if (system(cmd) != 0) {
            fprintf(stderr, "[cblaunch] extract failed\n");
            return 1;
        }
        code_path = "/tmp/cblaunch_code.bin";
    }
    int regcount = 16;
    const char *reg_env = getenv("CB_REGCOUNT");
    if (reg_env) regcount = atoi(reg_env);

    // capture the driver's const-bank descriptors from its launch segment
    uint64_t cb_va = 0;
    uint32_t desc[8] = {};   // +0xa8,+0xac,+0xb0,+0xb4,+0xd0,+0xd4,+0xe0,+0xe4
    {
        const char *dd = getenv("NVTRACE_DUMP_DIR");
        char best[512] = "";
        DIR *dp = opendir(dd ? dd : ".");
        struct dirent *de;
        while (dp && (de = readdir(dp))) {
            if (strncmp(de->d_name, "nvtrace-seg-", 12) == 0 &&
                strcmp(de->d_name, best) > 0) {
                char p[600]; snprintf(p, sizeof(p), "%s/%s", dd, de->d_name);
                FILE *f = fopen(p, "rb");
                if (!f) continue;
                fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
                uint8_t *buf = (uint8_t *)malloc(sz);
                if (fread(buf, 1, sz, f) != (size_t)sz) { fclose(f); free(buf); continue; }
                fclose(f);
                uint64_t seg_bank_va = 0;
                uint32_t seg_desc[8] = {};
                for (long o = 0; o + 400 <= sz; o += 4) {
                    uint32_t w, fl, st;
                    memcpy(&w, buf + o, 4);
                    memcpy(&fl, buf + o + 4, 4);
                    memcpy(&st, buf + o + 8, 4);
                    if (w == 0x206220c6 && fl == 0x40000000 && (st >> 24) == 0x02) {
                        uint32_t qa8; memcpy(&qa8, buf + o + 12 + 0xa8, 4);
                        if (qa8) {
                            seg_bank_va = (uint64_t)qa8 << 6;
                            static const int offs[8] = {0xa8,0xac,0xb0,0xb4,0xd0,0xd4,0xe0,0xe4};
                            for (int k = 0; k < 8; k++)
                                memcpy(&seg_desc[k], buf + o + 12 + offs[k], 4);
                        }
                    }
                }
                if (seg_bank_va) {
                    cb_va = seg_bank_va;
                    memcpy(desc, seg_desc, sizeof(desc));
                    strncpy(best, de->d_name, sizeof(best) - 1);
                }
                free(buf);
            }
        }
        if (dp) closedir(dp);
        if (!cb_va) { fprintf(stderr, "[cblaunch] no driver QMD found\n"); return 1; }
        fprintf(stderr, "[cblaunch] driver bank VA %#lx (from %s)\n", cb_va, best);
    }

    // pinned arena: kernel code + report sema (full-width VA fields).
    uint8_t *arena;
    CK(cudaHostAlloc((void **)&arena, 1 << 20, cudaHostAllocDefault));
    memset(arena, 0, 1 << 20);
    uint64_t code_va = (uint64_t)arena + 0x1000;
    volatile uint32_t *rep_sema = (volatile uint32_t *)(arena + 0x2000);
    uint64_t rep_sema_va = (uint64_t)arena + 0x2000;

    FILE *kf = fopen(code_path, "rb");
    if (!kf) { perror("code bin"); return 1; }
    size_t klen = fread(arena + 0x1000, 1, 0x1000, kf);
    fclose(kf);
    fprintf(stderr, "[cblaunch] SASS %zu bytes, regcount=%d, staging %#lx\n",
            klen, regcount, stage_va);
    fprintf(stderr, "[cblaunch] VAs: cb=%#lx out=%#lx rep_sema=%#lx qmd_sema=%#lx\n",
            cb_va, (uint64_t)d_out, rep_sema_va, qmd_sema_va);

    // QMD — reuse driver's bank descriptors.
    uint32_t q[96] = {};
    q[0x10/4] = 0x013f0000;
    uint64_t spacer_va = stage_va + 0x1800;       // inert next-QMD (3 slots out)
    int link_mode = getenv("CB_NOLINK") ? 0 : (getenv("CB_SELFLINK") ? 1 : 2);
    if (link_mode == 0)      q[0x30/4] = 0;
    else if (link_mode == 1) q[0x30/4] = (uint32_t)(stage_va >> 8);
    else                     q[0x30/4] = (uint32_t)(spacer_va >> 8);
    q[0x3c/4] = (uint32_t)qmd_sema_va;
    q[0x40/4] = 2;
    q[0x50/4] = 1;
    q[0x80/4] = (uint32_t)(code_va >> 4);
    // +0x84hi = register/local allocation sizing: 0x100 + 4*regcount for
    // STACK=0 kernels (driver: reg8->0x120, reg16->0x140). Under-sizing it
    // silently clamps the usable register window (R8+ faults).
    uint32_t alloc84 = 0x100u + 4u * (uint32_t)regcount;
    q[0x84/4] = (alloc84 << 16) | (uint32_t)((code_va >> 36) & 0xffff);
    q[0x88/4] = 4 | (1u << 16);                       // blockDim (4,1,_)
    q[0x8c/4] = 1 | ((uint32_t)regcount << 8) | (2u << 16);  // blockDim.z=1, regcount, alloc mode=2
    q[0x9c/4] = 1; q[0xa0/4] = 1; q[0xa4/4] = 1;
    q[0xa8/4] = desc[0]; q[0xac/4] = desc[1];
    q[0xb0/4] = desc[2]; q[0xb4/4] = desc[3];
    q[0xd0/4] = desc[4]; q[0xd4/4] = desc[5];
    q[0xe0/4] = desc[6]; q[0xe4/4] = desc[7];
    q[0xe8/4] = 1;
    q[0xec/4] = (uint32_t)(code_va >> 8);
    q[0xf0/4] = (uint32_t)(code_va >> 40);

    uint32_t seg[256 * 5 + 3 + 98 + 1 + 98 + 1 + 4];
    int n = 0;
    // probe sema A: fires iff the channel survived up to the QMD record
    volatile uint32_t *sema_a = rep_sema + 4;
    uint64_t sema_a_va = rep_sema_va + 16;
    seg[n++] = 0x200426c0;
    seg[n++] = (uint32_t)(sema_a_va >> 32);
    seg[n++] = (uint32_t)(sema_a_va & 0xffffffff);
    seg[n++] = 0xaaaa0001;
    seg[n++] = 0x04;
    if (link_mode == 2) {
        // inert spacer QMD, staged at spacer_va, chain ends (+0x30=0)
        uint32_t sp[96] = {};
        sp[0x10/4] = 0x00800002;
        sp[0x28/4] = 0x00230000;
        sp[0x38/4] = 0x00500200;
        seg[n++] = 0x206220c6;
        seg[n++] = 0x40000000;
        seg[n++] = (uint32_t)(spacer_va >> 8);
        memcpy(&seg[n], sp, 384); n += 96;
    }
    seg[n++] = 0x206220c6;
    seg[n++] = 0x40000000;
    seg[n++] = (uint32_t)(stage_va >> 8);
    memcpy(&seg[n], q, 384); n += 96;
    seg[n++] = 0x200426c0;
    seg[n++] = (uint32_t)(rep_sema_va >> 32);
    seg[n++] = (uint32_t)(rep_sema_va & 0xffffffff);
    seg[n++] = 0xdead0002;
    seg[n++] = 0x04;
    FILE *sf = fopen("/tmp/rawseg.bin", "wb");
    fwrite(seg, 4, n, sf);
    fclose(sf);

    MARK("injectraw:/tmp/rawseg.bin");

    int ok = 0;
    for (int i = 0; i < 2000; i++) {
        if (*rep_sema == 0xdead0002u) { ok = 1; break; }
        usleep(1000);
    }
    fprintf(stderr, "[cblaunch] sema = %#x (%s) semaA = %#x\n", *rep_sema, ok ? "SIGNALED" : "TIMEOUT", *sema_a);
    int href[4] = {}, hout[64] = {};
    cudaError_t e1 = cudaMemcpy(hout, d_out, 256, cudaMemcpyDeviceToHost);
    fprintf(stderr, "[cblaunch] out = %d %d %d %d (memcpy %s)\n",
            hout[0], hout[1], hout[2], hout[3], e1 ? cudaGetErrorString(e1) : "ok");
    if (!e1)
        fprintf(stderr, "[cblaunch]   ptr=%08x_%08x a=%d b=%d tid=%d stk=%08x wide=%08x_%08x\n",
                hout[1], hout[0], hout[2], hout[3], hout[4], hout[5], hout[7], hout[6]);
    cudaError_t e2 = cudaMemcpy(href, d_ref, 16, cudaMemcpyDeviceToHost);
    fprintf(stderr, "[cblaunch] ref = %d %d %d %d (memcpy %s)\n",
            href[0], href[1], href[2], href[3], e2 ? cudaGetErrorString(e2) : "ok");
    cudaError_t e3 = cudaDeviceSynchronize();
    if (e3) fprintf(stderr, "[cblaunch] sync err: %s\n", cudaGetErrorString(e3));
    int good = ok && !e1;
    for (int i = 0; i < 4; i++)
        good &= (hout[i] == (is_demo2 ? pa * pb - i : pa * pb + i));
    fprintf(stderr, "[cblaunch] kernel=%s %s\n", kname, good ? "SUCCESS" : "FAIL");
    return good ? 0 : 1;
}
