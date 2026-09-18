#include <cstdint>

namespace {

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
__device__ void check_shift(uint32_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    uint32_t lane = threadIdx.x & 31;
    if (lane == 0) {
        uint32_t a = static_cast<uint32_t>(__cvta_generic_to_shared(&bar));
        asm volatile("mbarrier.init.shared.b64 [%0], 1;"
                     :: "r"(a) : "memory");
    }
    __syncwarp();
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;"
        :: "r"(static_cast<uint32_t>(
            __cvta_generic_to_shared(&taddr_s))) : "memory");
    __syncwarp();
    uint32_t taddr = taddr_s;
    uint32_t value = 0x51000000u | lane;
    asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0], {%1};"
                 :: "r"(taddr), "r"(value) : "memory");
    asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
    if (lane == 0) {
#pragma unroll
        for (int i = 0; i < Count; ++i)
            asm volatile("tcgen05.shift.down.cta_group::1 [%0];"
                         :: "r"(taddr) : "memory");
        commit_wait(&bar);
    }
    __syncwarp();
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0}, [%1];"
                 : "=r"(value) : "r"(taddr) : "memory");
    asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
    out[lane] = value;
    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;"
                 :: "r"(taddr) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
        ::: "memory");
}

}  // namespace

#define DEF_SHIFT(n)                                                       \
    extern "C" __global__ void shift_##n(uint32_t *out) { check_shift<n>(out); }

DEF_SHIFT(1)
DEF_SHIFT(2)
DEF_SHIFT(4)
DEF_SHIFT(8)
DEF_SHIFT(16)
DEF_SHIFT(32)
DEF_SHIFT(64)
DEF_SHIFT(128)
