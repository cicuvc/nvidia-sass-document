#include <cstdint>

namespace {

__device__ __forceinline__ uint64_t read_clock() {
    uint64_t value;
    asm volatile("mov.u64 %0, %%clock64;" : "=l"(value));
    return value;
}

__device__ __forceinline__ void init_barrier(uint64_t *bar) {
    uint32_t a = static_cast<uint32_t>(__cvta_generic_to_shared(bar));
    asm volatile("mbarrier.init.shared.b64 [%0], 1;"
                 :: "r"(a) : "memory");
}

__device__ __forceinline__ void commit_wait(uint64_t *bar) {
    uint32_t a = static_cast<uint32_t>(__cvta_generic_to_shared(bar));
    asm volatile(
        "tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"
        :: "r"(a) : "memory");
    asm volatile(
        "{ .reg .pred p; L%=: mbarrier.try_wait.parity.shared.b64 "
        "p, [%0], 0; @!p bra L%=; }"
        :: "r"(a) : "memory");
    asm volatile("tcgen05.fence::after_thread_sync;" ::: "memory");
}

template <int Count>
__device__ void shift_bandwidth(uint64_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    uint32_t tid = threadIdx.x;
    uint32_t warp = tid >> 5;
    if (tid == 0)
        init_barrier(&bar);
    __syncthreads();
    if (warp == 0)
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 32;"
            :: "r"(static_cast<uint32_t>(
                __cvta_generic_to_shared(&taddr_s))) : "memory");
    __syncthreads();
    uint32_t taddr = taddr_s;
    if (tid == 0) {
        uint64_t begin = read_clock();
#pragma unroll
        for (int i = 0; i < Count; ++i)
            asm volatile("tcgen05.shift.down.cta_group::1 [%0];"
                         :: "r"(taddr) : "memory");
        commit_wait(&bar);
        uint64_t end = read_clock();
        out[0] = end - begin;
        out[1] = Count;
    }
    __syncthreads();
    if (warp == 0) {
        asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;"
                     :: "r"(taddr) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
            ::: "memory");
    }
}

}  // namespace

#define DEF_SHIFT(n)                                                        \
    extern "C" __global__ void shift_##n(uint64_t *out) {                  \
        shift_bandwidth<n>(out);                                           \
    }

DEF_SHIFT(1)
DEF_SHIFT(2)
DEF_SHIFT(4)
DEF_SHIFT(8)
DEF_SHIFT(16)
DEF_SHIFT(32)
DEF_SHIFT(64)
DEF_SHIFT(128)
