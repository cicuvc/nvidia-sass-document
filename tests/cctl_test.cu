// CCTL coverage: cache control ops. PTX: prefetch, discard, applypriority,
// and __threadfence-adjacent invalidations via inline asm.
#include <cstdint>

// prefetch to L1 -> CCTL.PF1 (address form)
extern "C" __global__ void cctl_prefetch_l1(const void* p) {
    asm volatile("prefetch.global.L1 [%0];" :: "l"(p) : "memory");
}
// prefetch to L2 -> CCTL.PF2 or PML2
extern "C" __global__ void cctl_prefetch_l2(const void* p) {
    asm volatile("prefetch.global.L2 [%0];" :: "l"(p) : "memory");
}
// discard L2 line -> CCTL variant (RML2/DML2?)
extern "C" __global__ void cctl_discard(void* p) {
    asm volatile("discard.global.L2 [%0], 128;" :: "l"(p) : "memory");
}
// applypriority evict_last -> CCTL
extern "C" __global__ void cctl_applyprio(const void* p) {
    asm volatile("applypriority.global.L2::evict_normal [%0], 128;" :: "l"(p) : "memory");
}
// raw inline SASS-triggering: use PTX prefetchu for uniform/const path
extern "C" __global__ void cctl_prefetchu(const void* p) {
    asm volatile("prefetchu.L1 [%0];" :: "l"(p) : "memory");
}
