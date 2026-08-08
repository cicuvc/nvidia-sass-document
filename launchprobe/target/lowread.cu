// lowread.cu — can a kernel's plain LDG read the low-address regions that the
// driver maps in this process (GPFIFO ring, pushbuffer, channel userd, UVM)?
// For each candidate we also write a known marker from the CPU first, so a
// successful LDG proves the GPU actually sees our write (not stale content).
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <sys/mman.h>
#include <unistd.h>
#include <cuda_runtime.h>

typedef unsigned long long u64;
typedef unsigned int u32;

__global__ void ldg_read(const unsigned long long *addrs, u32 *out, int n)
{
    for (int i = threadIdx.x; i < n; i += blockDim.x)
        out[i] = *(volatile u32 *)(uintptr_t)addrs[i];
}

int main()
{
    cudaFree(0);
    struct C { u64 va; const char *name; int writable; } cand[] = {
        { 0x200400000ull, "GPFIFO ring", 1 },
        { 0x200600000ull, "pushbuffer",  1 },
        { 0x207200000ull, "channelA",    1 },
        { 0x207400000ull, "channelB",    1 },
        { 0x207600000ull, "uvm-low",     1 },
    };
    const int n = sizeof(cand)/sizeof(cand[0]);
    unsigned long long addrs[8];
    u32 marker[8];

    for (int i = 0; i < n; i++) {
        addrs[i] = cand[i].va;
        marker[i] = 0xBAD00000u + (u32)i;
        if (cand[i].writable) {
            volatile u32 *p = (volatile u32 *)(uintptr_t)cand[i].va;
            *p = marker[i];
            __sync_synchronize();
        }
    }

    unsigned long long *daddrs;
    u32 *dout;
    cudaMalloc(&daddrs, 64);
    cudaMalloc(&dout, 64);
    cudaMemcpy(daddrs, addrs, sizeof(addrs), cudaMemcpyHostToDevice);
    ldg_read<<<1,64>>>(daddrs, dout, n);
    cudaError_t e = cudaDeviceSynchronize();
    printf("sync: %s\n", cudaGetErrorString(e));
    u32 hout[8] = {};
    cudaMemcpy(hout, dout, 64, cudaMemcpyDeviceToHost);
    for (int i = 0; i < n; i++) {
        volatile u32 *p = (volatile u32 *)(uintptr_t)cand[i].va;
        u32 cpu_read = *p;
        printf("0x%llx %-14s cpu=%08x  gpu_ldg=%08x  %s\n",
               (unsigned long long)cand[i].va, cand[i].name, cpu_read, hout[i],
               hout[i]==marker[i] ? "MATCH" : "no");
    }
    return 0;
}
