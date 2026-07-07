// CCTLL coverage: local-memory cache control. PTX prefetch.local -> CCTLL.
#include <cstdint>

extern "C" __global__ void cctll_prefetch_l1(int sel) {
    int local_arr[64];
    #pragma unroll 1
    for (int i = 0; i < 64; i++) local_arr[i] = i * sel;
    asm volatile("prefetch.local.L1 [%0];" :: "l"((void*)&local_arr[sel & 63]) : "memory");
    // keep local array alive
    asm volatile("" :: "l"((void*)local_arr) : "memory");
    if (sel == 12345) ((volatile int*)0)[0] = local_arr[sel & 63];
}
extern "C" __global__ void cctll_prefetch_l2(int sel) {
    int local_arr[64];
    #pragma unroll 1
    for (int i = 0; i < 64; i++) local_arr[i] = i * sel;
    asm volatile("prefetch.local.L2 [%0];" :: "l"((void*)&local_arr[sel & 63]) : "memory");
    asm volatile("" :: "l"((void*)local_arr) : "memory");
    if (sel == 12345) ((volatile int*)0)[0] = local_arr[sel & 63];
}
