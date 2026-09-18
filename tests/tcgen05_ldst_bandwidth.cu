#include <cstdint>

namespace {

constexpr uint32_t kGroups = 256;
constexpr uint32_t kColumns = 128;

__device__ __forceinline__ uint64_t read_clock() {
    uint64_t value;
    asm volatile("mov.u64 %0, %%clock64;" : "=l"(value));
    return value;
}

template <int N>
__device__ __forceinline__ uint32_t ldtm(uint32_t taddr);

template <>
__device__ __forceinline__ uint32_t ldtm<1>(uint32_t a) {
    uint32_t r;
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0}, [%1];"
                 : "=r"(r) : "r"(a) : "memory");
    return r;
}

template <>
__device__ __forceinline__ uint32_t ldtm<2>(uint32_t a) {
    uint32_t r[2];
    asm volatile("tcgen05.ld.sync.aligned.32x32b.x2.b32 {%0,%1}, [%2];"
                 : "=r"(r[0]), "=r"(r[1]) : "r"(a) : "memory");
    return r[0];
}

template <>
__device__ __forceinline__ uint32_t ldtm<4>(uint32_t a) {
    uint32_t r[4];
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x4.b32 {%0,%1,%2,%3}, [%4];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3])
        : "r"(a) : "memory");
    return r[0];
}

template <>
__device__ __forceinline__ uint32_t ldtm<8>(uint32_t a) {
    uint32_t r[8];
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x8.b32 "
        "{%0,%1,%2,%3,%4,%5,%6,%7}, [%8];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3]),
          "=r"(r[4]), "=r"(r[5]), "=r"(r[6]), "=r"(r[7])
        : "r"(a) : "memory");
    return r[0];
}

template <>
__device__ __forceinline__ uint32_t ldtm<16>(uint32_t a) {
    uint32_t r[16];
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x16.b32 "
        "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15}, [%16];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3]),
          "=r"(r[4]), "=r"(r[5]), "=r"(r[6]), "=r"(r[7]),
          "=r"(r[8]), "=r"(r[9]), "=r"(r[10]), "=r"(r[11]),
          "=r"(r[12]), "=r"(r[13]), "=r"(r[14]), "=r"(r[15])
        : "r"(a) : "memory");
    return r[0];
}

template <int N>
__device__ __forceinline__ void sttm(uint32_t taddr, const uint32_t *r);

template <>
__device__ __forceinline__ void sttm<1>(uint32_t a, const uint32_t *r) {
    asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0], {%1};"
                 :: "r"(a), "r"(r[0]) : "memory");
}

template <>
__device__ __forceinline__ void sttm<2>(uint32_t a, const uint32_t *r) {
    asm volatile("tcgen05.st.sync.aligned.32x32b.x2.b32 [%0], {%1,%2};"
                 :: "r"(a), "r"(r[0]), "r"(r[1]) : "memory");
}

template <>
__device__ __forceinline__ void sttm<4>(uint32_t a, const uint32_t *r) {
    asm volatile(
        "tcgen05.st.sync.aligned.32x32b.x4.b32 [%0], {%1,%2,%3,%4};"
        :: "r"(a), "r"(r[0]), "r"(r[1]), "r"(r[2]), "r"(r[3])
        : "memory");
}

template <>
__device__ __forceinline__ void sttm<8>(uint32_t a, const uint32_t *r) {
    asm volatile(
        "tcgen05.st.sync.aligned.32x32b.x8.b32 "
        "[%0], {%1,%2,%3,%4,%5,%6,%7,%8};"
        :: "r"(a), "r"(r[0]), "r"(r[1]), "r"(r[2]), "r"(r[3]),
           "r"(r[4]), "r"(r[5]), "r"(r[6]), "r"(r[7]) : "memory");
}

template <>
__device__ __forceinline__ void sttm<16>(uint32_t a, const uint32_t *r) {
    asm volatile(
        "tcgen05.st.sync.aligned.32x32b.x16.b32 "
        "[%0], {%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15,%16};"
        :: "r"(a), "r"(r[0]), "r"(r[1]), "r"(r[2]), "r"(r[3]),
           "r"(r[4]), "r"(r[5]), "r"(r[6]), "r"(r[7]),
           "r"(r[8]), "r"(r[9]), "r"(r[10]), "r"(r[11]),
           "r"(r[12]), "r"(r[13]), "r"(r[14]), "r"(r[15])
        : "memory");
}

template <int N, int OpsPerGroup, bool Store>
__device__ __forceinline__ void bandwidth(uint32_t *out) {
    static_assert(N * OpsPerGroup <= kColumns);
    __shared__ uint32_t taddr_s;
    __shared__ volatile uint32_t group_count;
    uint32_t tid = threadIdx.x;
    uint32_t warp = tid >> 5;
    uint32_t lane = tid & 31;
    if (tid == 0) group_count = kGroups;
    __syncthreads();
    if (warp == 0)
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 128;"
            :: "r"(static_cast<uint32_t>(
                __cvta_generic_to_shared(&taddr_s))) : "memory");
    __syncthreads();
    uint32_t taddr = taddr_s;
    uint32_t src[16];
#pragma unroll
    for (int i = 0; i < 16; ++i)
        src[i] = 0x51000000u | (tid << 8) | static_cast<uint32_t>(i);

    uint32_t groups = group_count;
    uint32_t sink = tid;
    __syncthreads();
    uint64_t begin = read_clock();
#pragma unroll 1
    for (uint32_t group = 0; group < groups; ++group) {
#pragma unroll
        for (int i = 0; i < OpsPerGroup; ++i) {
            uint32_t column = static_cast<uint32_t>(i * N);
            if constexpr (Store)
                sttm<N>(taddr + column, src);
            else
                sink ^= ldtm<N>(taddr + column);
        }
        if constexpr (Store)
            asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
        else
            asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
    }
    uint64_t end = read_clock();
    if (lane == 0) {
        uint64_t delta = end - begin;
        out[warp * 4 + 0] = static_cast<uint32_t>(delta);
        out[warp * 4 + 1] = static_cast<uint32_t>(delta >> 32);
        out[warp * 4 + 2] = sink;
        out[warp * 4 + 3] = N;
    }
    __syncthreads();
    if (warp == 0) {
        asm volatile(
            "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 128;"
            :: "r"(taddr) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
            ::: "memory");
    }
}

}  // namespace

#define DEFINE_BW_KERNELS(n)                                      \
    extern "C" __global__ void ldtm_x##n(uint32_t *out) {         \
        bandwidth<n, 4, false>(out);                              \
    }                                                             \
    extern "C" __global__ void sttm_x##n(uint32_t *out) {         \
        bandwidth<n, 4, true>(out);                               \
    }                                                             \
    extern "C" __global__ void ldtm_b8_x##n(uint32_t *out) {      \
        bandwidth<n, 8, false>(out);                              \
    }                                                             \
    extern "C" __global__ void sttm_b8_x##n(uint32_t *out) {      \
        bandwidth<n, 8, true>(out);                               \
    }

DEFINE_BW_KERNELS(1)
DEFINE_BW_KERNELS(2)
DEFINE_BW_KERNELS(4)
DEFINE_BW_KERNELS(8)
DEFINE_BW_KERNELS(16)
