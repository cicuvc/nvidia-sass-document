#include <cstdint>

namespace {

__device__ __forceinline__ uint64_t read_clock() {
    uint64_t value;
    asm volatile("mov.u64 %0, %%clock64;" : "=l"(value));
    return value;
}

template <int N>
__device__ __forceinline__ void pad(uint32_t lane) {
#pragma unroll
    for (int i = 0; i < N; ++i)
        asm volatile("{ .reg .pred p; setp.eq.u32 p, %0, 0; }"
                     :: "r"(lane) : "memory");
}

__device__ __forceinline__ void ldtm_x16(uint32_t taddr,
                                         uint32_t (&r)[16]) {
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x16.b32 "
        "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15},"
        " [%16];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3]),
          "=r"(r[4]), "=r"(r[5]), "=r"(r[6]), "=r"(r[7]),
          "=r"(r[8]), "=r"(r[9]), "=r"(r[10]), "=r"(r[11]),
          "=r"(r[12]), "=r"(r[13]), "=r"(r[14]), "=r"(r[15])
        : "r"(taddr) : "memory");
    asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
}

template <bool Active>
__device__ __forceinline__ uint32_t fixed_burst(uint32_t lane) {
    float b = 2.5f, c = 0.75f;
    float r[8];
#pragma unroll
    for (int i = 0; i < 8; ++i) {
        if constexpr (Active) {
            // Distinct sources prevent ptxas from CSE-folding the eight
            // independent fixed-pipe writes into one FFMA.
            float a = __uint_as_float(0x3f800000u + (lane << 8) + i);
            asm volatile("fma.rn.f32 %0, %1, %2, %3;"
                         : "=f"(r[i]) : "f"(a), "f"(b), "f"(c));
        } else {
            asm volatile("{ .reg .pred p; setp.eq.u32 p, %0, 0; }"
                         :: "r"(lane) : "memory");
        }
    }
    if constexpr (Active) {
        uint32_t sink = 0;
#pragma unroll
        for (int i = 0; i < 8; ++i)
            sink ^= __float_as_uint(r[i]);
        return sink;
    }
    return 0;
}

template <int Phase, int TargetWarp, bool Active>
__device__ void probe(uint64_t *out) {
    __shared__ uint32_t taddr_s;
    uint32_t tid = threadIdx.x;
    uint32_t warp = tid >> 5;
    uint32_t lane = tid & 31;
    if (warp == 0)
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 32;"
            :: "r"(static_cast<uint32_t>(
                __cvta_generic_to_shared(&taddr_s))) : "memory");
    __syncthreads();
    uint32_t taddr = taddr_s;
    uint32_t sink = 0;
    __syncthreads();
    if (warp == 0) {
        if constexpr (Phase < 0)
            pad<-Phase>(lane);
        uint32_t r[16];
        uint64_t begin = read_clock();
        ldtm_x16(taddr, r);
        uint64_t end = read_clock();
        sink = r[0];
        if (lane == 0)
            out[0] = end - begin;
    } else if (warp == TargetWarp) {
        if constexpr (Phase > 0)
            pad<Phase>(lane);
        sink = fixed_burst<Active>(lane);
    }
    // Keep the contender result architecturally live without putting its
    // global-store traffic inside the victim's timed window.
    if (tid == static_cast<uint32_t>(TargetWarp * 32))
        out[1] = sink;
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

#define DEF_PHASE(tag, phase)                                              \
    extern "C" __global__ void rf_same_##tag(uint64_t *out) {             \
        probe<phase, 4, true>(out);                                        \
    }                                                                      \
    extern "C" __global__ void rf_same_nop_##tag(uint64_t *out) {         \
        probe<phase, 4, false>(out);                                       \
    }                                                                      \
    extern "C" __global__ void rf_diff_##tag(uint64_t *out) {             \
        probe<phase, 1, true>(out);                                        \
    }

DEF_PHASE(m8, -8)
DEF_PHASE(m4, -4)
DEF_PHASE(p0, 0)
DEF_PHASE(p4, 4)
DEF_PHASE(p8, 8)
