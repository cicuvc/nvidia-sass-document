#include <cstdint>

// Basic B200 UTCHMMA throughput probe.  A and B are BF16 in shared memory,
// D is FP32 in TMEM.  M=128 and K=16 are fixed; N and D accumulation vary.

namespace {

constexpr int kOps = 512;

__device__ __forceinline__ uint64_t make_kmajor_desc(uint32_t smem_addr) {
    // BF16 K-major, no swizzle: LBO=256 B and SBO=128 B.
    return ((uint64_t)(smem_addr & 0x3ffffu) >> 4)
         | (16ull << 16) | (8ull << 32) | (1ull << 46);
}

__device__ __forceinline__ void init_mbarrier(uint64_t *bar) {
    uint32_t addr = static_cast<uint32_t>(__cvta_generic_to_shared(bar));
    asm volatile("mbarrier.init.shared.b64 [%0], 1;"
                 :: "r"(addr) : "memory");
}

__device__ __forceinline__ void commit_wait(uint64_t *bar) {
    uint32_t addr = static_cast<uint32_t>(__cvta_generic_to_shared(bar));
    asm volatile(
        "tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"
        :: "r"(addr) : "memory");
    asm volatile(
        "{\n"
        " .reg .pred p;\n"
        "L%=:\n"
        " mbarrier.try_wait.parity.shared.b64 p, [%0], 0;\n"
        " @!p bra L%=;\n"
        "}\n" :: "r"(addr) : "memory");
}

template <int CollectorMode>
__device__ __forceinline__ void issue_mma(
        uint32_t taddr, uint64_t adesc, uint64_t bdesc, uint32_t idesc,
        uint32_t accumulate) {
#define MMA_ASM(MOD)                                                        \
    asm volatile(                                                           \
        "{\n .reg .pred p;\n"                                             \
        " setp.ne.u32 p, %4, 0;\n"                                         \
        " tcgen05.mma.cta_group::1.kind::f16" MOD " "                     \
        "[%0], %1, %2, %3, {%5,%5,%5,%5}, p;\n }\n"                     \
        :: "r"(taddr), "l"(adesc), "l"(bdesc), "r"(idesc),               \
           "r"(accumulate), "r"(0u) : "memory")
    if constexpr (CollectorMode == 0)
        MMA_ASM("");
    else if constexpr (CollectorMode == 1)
        MMA_ASM(".collector::a::fill");
    else if constexpr (CollectorMode == 2)
        MMA_ASM(".collector::a::use");
    else
        MMA_ASM(".collector::a::lastuse");
#undef MMA_ASM
}

template <int N, bool Accumulate, int M = 128, bool Unroll6 = false>
__device__ __forceinline__ void run_probe(uint64_t *out) {
    constexpr int Cols = N < 32 ? 32 : N;
    static_assert((Cols & (Cols - 1)) == 0 && Cols <= 256);

    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    __shared__ __align__(128) uint16_t a[128 * 16];
    __shared__ __align__(128) uint16_t b[16 * 256];

    const uint32_t tid = threadIdx.x;
    for (int i = tid; i < 128 * 16; i += blockDim.x)
        a[i] = 0x3f80;  // BF16 1.0
    for (int i = tid; i < 16 * N; i += blockDim.x)
        b[i] = 0x3f80;
    if (tid == 0)
        init_mbarrier(&bar);
    __syncthreads();

    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
        "[%0], %1;" :: "r"((uint32_t)__cvta_generic_to_shared(&taddr_s)),
        "n"(Cols) : "memory");
    __syncwarp();

    uint32_t taddr = taddr_s;
    uint64_t adesc = make_kmajor_desc(
        (uint32_t)__cvta_generic_to_shared(a));
    uint64_t bdesc = make_kmajor_desc(
        (uint32_t)__cvta_generic_to_shared(b));
    constexpr uint32_t idesc = (1u << 4)             // D = FP32
                              | (1u << 7)             // A = BF16
                              | (1u << 10)            // B = BF16
                              | ((N >> 3) << 17)
                              | ((M >> 4) << 24);
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    __syncthreads();

    if (tid == 0) {
        uint64_t begin = clock64();
        int count = kOps;
        asm volatile("" : "+r"(count));
        if constexpr (Unroll6) {
#pragma unroll 1
            for (int i = 0; i < count / 6; ++i) {
#pragma unroll
                for (int j = 0; j < 6; ++j)
                    issue_mma<0>(taddr, adesc, bdesc, idesc,
                                 static_cast<uint32_t>(Accumulate));
            }
            for (int i = 0; i < count % 6; ++i)
                issue_mma<0>(taddr, adesc, bdesc, idesc,
                             static_cast<uint32_t>(Accumulate));
        } else {
#pragma unroll 1
            for (int i = 0; i < count; ++i) {
                issue_mma<0>(taddr, adesc, bdesc, idesc,
                             static_cast<uint32_t>(Accumulate));
            }
        }
        commit_wait(&bar);
        uint64_t end = clock64();
        out[0] = begin;
        out[1] = end;
    }
    __syncthreads();

    if constexpr (!Accumulate) {
        uint32_t check;
        asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0}, [%1];"
                     : "=r"(check) : "r"(taddr) : "memory");
        asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
        if (tid == 0) out[2] = check;
    }

    asm volatile(
        "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, %1;"
        :: "r"(taddr), "n"(Cols) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
        ::: "memory");
}

template <bool Accumulate>
__device__ __forceinline__ void run_reuse_probe(uint64_t *out) {
    constexpr int N = 128;
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    __shared__ __align__(128) uint16_t a[128 * 16];
    __shared__ __align__(128) uint16_t b[16 * N];
    uint32_t tid = threadIdx.x;
    for (int i = tid; i < 128 * 16; i += blockDim.x) a[i] = 0x3f80;
    for (int i = tid; i < 16 * N; i += blockDim.x) b[i] = 0x3f80;
    if (tid == 0) init_mbarrier(&bar);
    __syncthreads();
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 128;"
        :: "r"((uint32_t)__cvta_generic_to_shared(&taddr_s)) : "memory");
    __syncwarp();
    uint32_t taddr = taddr_s;
    uint64_t adesc = make_kmajor_desc(
        (uint32_t)__cvta_generic_to_shared(a));
    uint64_t bdesc = make_kmajor_desc(
        (uint32_t)__cvta_generic_to_shared(b));
    constexpr uint32_t idesc = (1u << 4) | (1u << 7) | (1u << 10)
                              | ((N >> 3) << 17) | ((128 >> 4) << 24);
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    __syncthreads();
    if (tid == 0) {
        uint64_t begin = clock64();
        issue_mma<1>(taddr, adesc, bdesc, idesc,
                     static_cast<uint32_t>(Accumulate));
#pragma unroll 1
        for (int i = 1; i < kOps - 1; ++i)
            issue_mma<2>(taddr, adesc, bdesc, idesc,
                         static_cast<uint32_t>(Accumulate));
        issue_mma<3>(taddr, adesc, bdesc, idesc,
                     static_cast<uint32_t>(Accumulate));
        commit_wait(&bar);
        uint64_t end = clock64();
        out[0] = begin;
        out[1] = end;
    }
    __syncthreads();
    asm volatile(
        "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 128;"
        :: "r"(taddr) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
        ::: "memory");
}

}  // namespace

#define MAKE_KERNEL(N, ACC, NAME)                         \
extern "C" __global__ void NAME(uint64_t *out) {          \
    run_probe<N, ACC>(out);                               \
}

MAKE_KERNEL(8,   false, mma_n8_overwrite)
MAKE_KERNEL(16,  false, mma_n16_overwrite)
MAKE_KERNEL(32,  false, mma_n32_overwrite)
MAKE_KERNEL(64,  false, mma_n64_overwrite)
MAKE_KERNEL(128, false, mma_n128_overwrite)
MAKE_KERNEL(256, false, mma_n256_overwrite)
MAKE_KERNEL(8,   true,  mma_n8_accumulate)
MAKE_KERNEL(16,  true,  mma_n16_accumulate)
MAKE_KERNEL(32,  true,  mma_n32_accumulate)
MAKE_KERNEL(64,  true,  mma_n64_accumulate)
MAKE_KERNEL(128, true,  mma_n128_accumulate)
MAKE_KERNEL(256, true,  mma_n256_accumulate)

extern "C" __global__ void mma_n128_reuse_overwrite(uint64_t *out) {
    run_reuse_probe<false>(out);
}

extern "C" __global__ void mma_n128_reuse_accumulate(uint64_t *out) {
    run_reuse_probe<true>(out);
}

extern "C" __global__ void mma_m64n128_overwrite(uint64_t *out) {
    run_probe<128, false, 64>(out);
}

extern "C" __global__ void mma_m64n256_overwrite(uint64_t *out) {
    run_probe<256, false, 64>(out);
}

extern "C" __global__ void mma_m128n128_unroll6_overwrite(uint64_t *out) {
    run_probe<128, false, 128, true>(out);
}

extern "C" __global__ void mma_m128n128_unroll6_accumulate(uint64_t *out) {
    run_probe<128, true, 128, true>(out);
}
