#include <cstdint>

__device__ __forceinline__ void init_mbarrier(uint64_t *bar) {
    uint32_t a = static_cast<uint32_t>(__cvta_generic_to_shared(bar));
    asm volatile("mbarrier.init.shared.b64 [%0], 1;" :: "r"(a) : "memory");
}

__device__ __forceinline__ void commit_wait(uint64_t *bar) {
    uint32_t a = static_cast<uint32_t>(__cvta_generic_to_shared(bar));
    asm volatile(
        "tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"
        :: "r"(a) : "memory");
    asm volatile(
        "{\n"
        " .reg .pred p;\n"
        "L%=:\n"
        " mbarrier.try_wait.parity.shared.b64 p, [%0], 0;\n"
        " @!p bra L%=;\n"
        "}\n" :: "r"(a) : "memory");
    asm volatile("tcgen05.fence::after_thread_sync;" ::: "memory");
}

extern "C" __global__ void shift_runtime(uint32_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    if (threadIdx.x == 0) init_mbarrier(&bar);
    __syncwarp();
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;"
        :: "r"(static_cast<uint32_t>(__cvta_generic_to_shared(&taddr_s)))
        : "memory");
    __syncwarp();
    uint32_t taddr = taddr_s;
    uint32_t lane = threadIdx.x & 31;
    uint32_t r[8];
#pragma unroll
    for (int i = 0; i < 8; ++i)
        r[i] = 0x10000000u | (lane << 8) | static_cast<uint32_t>(i);
    asm volatile(
        "tcgen05.st.sync.aligned.32x32b.x8.b32 [%0], "
        "{%1,%2,%3,%4,%5,%6,%7,%8};"
        :: "r"(taddr), "r"(r[0]), "r"(r[1]), "r"(r[2]), "r"(r[3]),
           "r"(r[4]), "r"(r[5]), "r"(r[6]), "r"(r[7]) : "memory");
    asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
    // Unlike tcgen05.ld/st, tcgen05.shift is a single-thread issue operation.
    // Issuing it from all 32 lanes applies the in-place shift 32 times.
    if (lane == 0) {
        asm volatile("tcgen05.shift.down.cta_group::1 [%0];"
                     :: "r"(taddr) : "memory");
        commit_wait(&bar);
    }
    __syncwarp();
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x8.b32 "
        "{%0,%1,%2,%3,%4,%5,%6,%7}, [%8];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3]),
          "=r"(r[4]), "=r"(r[5]), "=r"(r[6]), "=r"(r[7])
        : "r"(taddr) : "memory");
    asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
#pragma unroll
    for (int i = 0; i < 8; ++i)
        out[lane * 8 + i] = r[i];
    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;"
                 :: "r"(taddr) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
        ::: "memory");
}

// Four-warp probe: issue the shift from warp 1 only, then inspect all four
// warp-private 32-lane TMEM chunks.  This distinguishes a CTA-wide 128-row
// shift from a shift local to the issuing warp's 32 rows.
extern "C" __global__ void shift_warp_runtime(uint32_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    uint32_t tid = threadIdx.x;
    uint32_t warp = tid >> 5;
    if (tid == 0) init_mbarrier(&bar);
    __syncthreads();
    if (warp == 0)
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 32;"
            :: "r"(static_cast<uint32_t>(
                __cvta_generic_to_shared(&taddr_s))) : "memory");
    __syncthreads();
    uint32_t taddr = taddr_s;
    uint32_t r[8];
#pragma unroll
    for (int i = 0; i < 8; ++i)
        r[i] = 0x20000000u | (tid << 8) | static_cast<uint32_t>(i);
    asm volatile(
        "tcgen05.st.sync.aligned.32x32b.x8.b32 [%0], "
        "{%1,%2,%3,%4,%5,%6,%7,%8};"
        :: "r"(taddr), "r"(r[0]), "r"(r[1]), "r"(r[2]), "r"(r[3]),
           "r"(r[4]), "r"(r[5]), "r"(r[6]), "r"(r[7]) : "memory");
    asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
    __syncthreads();
    if (tid == 32) {
        asm volatile("tcgen05.shift.down.cta_group::1 [%0];"
                     :: "r"(taddr) : "memory");
        commit_wait(&bar);
    }
    __syncthreads();
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x8.b32 "
        "{%0,%1,%2,%3,%4,%5,%6,%7}, [%8];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3]),
          "=r"(r[4]), "=r"(r[5]), "=r"(r[6]), "=r"(r[7])
        : "r"(taddr) : "memory");
    asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
#pragma unroll
    for (int i = 0; i < 8; ++i)
        out[tid * 8 + i] = r[i];
    __syncthreads();
    if (warp == 0) {
        asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;"
                     :: "r"(taddr) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
            ::: "memory");
    }
}

extern "C" __global__ void cp_runtime(uint32_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    __shared__ __align__(128) uint32_t src[4096];
    uint32_t tid = threadIdx.x;
    uint32_t warp = tid >> 5;
    for (int i = tid; i < 4096; i += blockDim.x)
        src[i] = 0xc0000000u | static_cast<uint32_t>(i);
    __syncthreads();
    if (tid == 0) init_mbarrier(&bar);
    __syncthreads();
    if (warp == 0)
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 32;"
            :: "r"(static_cast<uint32_t>(
                __cvta_generic_to_shared(&taddr_s))) : "memory");
    __syncthreads();
    uint32_t taddr = taddr_s;
    uint32_t saddr = static_cast<uint32_t>(__cvta_generic_to_shared(src));
    // No-swizzle K-major descriptor.  The source word index is encoded in the
    // payload so the observed shared -> TMEM traversal can be reconstructed.
    uint64_t desc = ((uint64_t)(saddr & 0x3ffffu) >> 4)
                  | (1ull << 16) | (8ull << 32) | (1ull << 46);
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    // tcgen05.cp, like tcgen05.shift, is issued by one elected thread.
    if (tid == 0) {
        asm volatile("tcgen05.cp.cta_group::1.128x256b [%0], %1;"
                     :: "r"(taddr), "l"(desc) : "memory");
        commit_wait(&bar);
    }
    __syncthreads();
    uint32_t r[8];
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x8.b32 "
        "{%0,%1,%2,%3,%4,%5,%6,%7}, [%8];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3]),
          "=r"(r[4]), "=r"(r[5]), "=r"(r[6]), "=r"(r[7])
        : "r"(taddr) : "memory");
    asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
#pragma unroll
    for (int i = 0; i < 8; ++i)
        out[tid * 8 + i] = r[i];
    __syncthreads();
    if (warp == 0) {
        asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;"
                     :: "r"(taddr) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
            ::: "memory");
    }
}
