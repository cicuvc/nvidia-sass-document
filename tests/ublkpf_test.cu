// UBLKPF coverage: cp.async.bulk.prefetch (non-tensor, global -> L2).
#include <cstdint>

extern "C" __global__ void blkpf(const void* __restrict__ src, int nbytes) {
    asm volatile("cp.async.bulk.prefetch.L2.global [%0], %1;"
        :: "l"(src), "r"(nbytes) : "memory");
}

// with cache_hint policy operand
extern "C" __global__ void blkpf_hint(const void* __restrict__ src, int nbytes, uint64_t pol) {
    asm volatile("cp.async.bulk.prefetch.L2.global.L2::cache_hint [%0], %1, %2;"
        :: "l"(src), "r"(nbytes), "l"(pol) : "memory");
}
