#include <cstdint>

namespace {

constexpr int kGroups = 128;

enum Mode {
    EMPTY,
    LDS_ONLY,
    SHFL_ONLY,
    STTM_ONLY,
    STTM_LDS,
    STTM_SHFL,
    LDTM_ONLY,
    LDTM_LDS,
    LDTM_SHFL,
};

__device__ __forceinline__ uint64_t read_clock() {
    uint64_t value;
    asm volatile("mov.u64 %0, %%clock64;" : "=l"(value));
    return value;
}

__device__ __forceinline__ uint32_t lds(uint32_t addr) {
    uint32_t value;
    asm volatile("ld.volatile.shared.u32 %0, [%1];"
                 : "=r"(value) : "r"(addr) : "memory");
    return value;
}

__device__ __forceinline__ uint32_t shfl(uint32_t value) {
    uint32_t result;
    asm volatile("shfl.sync.bfly.b32 %0, %1, 1, 0x1f, 0xffffffff;"
                 : "=r"(result) : "r"(value) : "memory");
    return result;
}

template <Mode mode>
__device__ __forceinline__ void run_probe(uint32_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(128) uint32_t smem[32];
    __shared__ volatile uint32_t group_count;
    uint32_t lane = threadIdx.x & 31;
    smem[lane] = 0x31000000u | lane;
    if (lane == 0) group_count = kGroups;
    __syncwarp();
    asm volatile(
        "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0], 32;"
        :: "r"(static_cast<uint32_t>(__cvta_generic_to_shared(&taddr_s)))
        : "memory");
    __syncwarp();
    uint32_t taddr = taddr_s;
    uint32_t saddr = static_cast<uint32_t>(__cvta_generic_to_shared(smem));
    uint32_t seed = 0x41000000u | lane;
    uint32_t seed1 = seed + 0x100;
    uint32_t seed2 = seed + 0x200;
    uint32_t seed3 = seed + 0x300;
    asm volatile(
        "tcgen05.st.sync.aligned.32x32b.x4.b32 "
        "[%0], {%1,%2,%3,%4};"
        :: "r"(taddr), "r"(seed), "r"(seed1), "r"(seed2), "r"(seed3)
        : "memory");
    asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");

    uint32_t sink = seed;
    uint32_t groups = group_count;
    uint64_t begin = read_clock();
#pragma unroll 1
    for (int group = 0; group < groups; ++group) {
        if constexpr (mode == EMPTY) {
            asm volatile("" ::: "memory");
        } else if constexpr (mode == LDS_ONLY) {
            uint32_t value[4];
#pragma unroll
            for (int i = 0; i < 4; ++i) value[i] = lds(saddr + 4 * i);
#pragma unroll
            for (int i = 0; i < 4; ++i) sink ^= value[i];
        } else if constexpr (mode == SHFL_ONLY) {
            uint32_t value[4];
#pragma unroll
            for (int i = 0; i < 4; ++i)
                value[i] = shfl(seed + i + group);
#pragma unroll
            for (int i = 0; i < 4; ++i) sink ^= value[i];
        } else if constexpr (mode == STTM_ONLY || mode == STTM_LDS ||
                             mode == STTM_SHFL) {
            uint32_t value[4] = {};
#pragma unroll
            for (int i = 0; i < 4; ++i) {
                asm volatile(
                    "tcgen05.st.sync.aligned.32x32b.x1.b32 [%0], {%1};"
                    :: "r"(taddr), "r"(seed) : "memory");
                if constexpr (mode == STTM_LDS)
                    value[i] = lds(saddr + 4 * i);
                if constexpr (mode == STTM_SHFL)
                    value[i] = shfl(seed + i + group);
            }
            asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
            if constexpr (mode != STTM_ONLY)
#pragma unroll
                for (int i = 0; i < 4; ++i) sink ^= value[i];
        } else {
            uint32_t value[4];
            uint32_t side[4] = {};
#pragma unroll
            for (int i = 0; i < 4; ++i) {
                uint32_t column = taddr + static_cast<uint32_t>(i);
                asm volatile(
                    "tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0}, [%1];"
                    : "=r"(value[i]) : "r"(column) : "memory");
                if constexpr (mode == LDTM_LDS)
                    side[i] = lds(saddr + 4 * i);
                if constexpr (mode == LDTM_SHFL)
                    side[i] = shfl(seed + i + group);
            }
            asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
#pragma unroll
            for (int i = 0; i < 4; ++i) sink ^= value[i] ^ side[i];
        }
    }
    uint64_t end = read_clock();

    if (lane == 0) {
        uint64_t delta = end - begin;
        out[0] = static_cast<uint32_t>(delta);
        out[1] = static_cast<uint32_t>(delta >> 32);
        out[2] = sink;
    }
    asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;"
                 :: "r"(taddr) : "memory");
    asm volatile(
        "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
        ::: "memory");
}

}  // namespace

#define DEFINE_KERNEL(name, mode)                         \
    extern "C" __global__ void name(uint32_t *out) {      \
        run_probe<mode>(out);                             \
    }

DEFINE_KERNEL(empty, EMPTY)
DEFINE_KERNEL(lds_only, LDS_ONLY)
DEFINE_KERNEL(shfl_only, SHFL_ONLY)
DEFINE_KERNEL(sttm_only, STTM_ONLY)
DEFINE_KERNEL(sttm_lds, STTM_LDS)
DEFINE_KERNEL(sttm_shfl, STTM_SHFL)
DEFINE_KERNEL(ldtm_only, LDTM_ONLY)
DEFINE_KERNEL(ldtm_lds, LDTM_LDS)
DEFINE_KERNEL(ldtm_shfl, LDTM_SHFL)
