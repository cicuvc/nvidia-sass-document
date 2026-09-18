#include <cstdint>

// INVALID AS A SATURATION PROBE; keep only as a ptxas-lowering reference.
// ptxas hoists the invariant LDS.128 operations out of the intended loop, so
// the generated loop does not apply sustained shared-memory pressure.  Do not
// patch this cubin or cite its timings.  Future executable probes must be
// generated fully from repository assembler source; see
// notes/sm100/arch/tcgen05_tooling_checkpoint.md.

namespace {

constexpr int kMmaOps = 512;
constexpr int kLdsOpsPerWarp = 2048;  // 4 wf/op = 8192 wf/warp.

__device__ __forceinline__ uint64_t desc(uint32_t a) {
    return ((uint64_t)(a & 0x3ffffu) >> 4)
         | (16ull << 16) | (8ull << 32) | (1ull << 46);
}

__device__ __forceinline__ void init_bar(uint64_t *bar) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(bar);
    asm volatile("mbarrier.init.shared.b64 [%0],1;"
                 :: "r"(a) : "memory");
}

__device__ __forceinline__ void commit_wait(uint64_t *bar) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(bar);
    asm volatile(
        "tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"
        :: "r"(a) : "memory");
    asm volatile(
        "{ .reg .pred p; L%=: mbarrier.try_wait.parity.shared.b64 "
        "p,[%0],0; @!p bra L%=; }" :: "r"(a) : "memory");
}

template <int Mode>
__device__ __forceinline__ void mma_gdesc(uint32_t d, uint64_t a, uint64_t b,
                                          uint32_t idesc) {
#define DO_MMA(MOD)                                                        \
    asm volatile("{ .reg .pred p; setp.ne.u32 p,0,0; "                    \
                 "tcgen05.mma.cta_group::1.kind::f16" MOD                \
                 " [%0],%1,%2,%3,{%4,%4,%4,%4},p; }"                    \
                 :: "r"(d), "l"(a), "l"(b), "r"(idesc), "r"(0u)    \
                 : "memory")
    if constexpr (Mode == 0) DO_MMA("");
    else if constexpr (Mode == 1) DO_MMA(".collector::a::fill");
    else if constexpr (Mode == 2) DO_MMA(".collector::a::use");
    else DO_MMA(".collector::a::lastuse");
#undef DO_MMA
}

__device__ __forceinline__ void mma_atmem(uint32_t d, uint32_t a,
                                          uint64_t b, uint32_t idesc) {
    asm volatile(
        "{ .reg .pred p; setp.ne.u32 p,0,0; "
        "tcgen05.mma.cta_group::1.kind::f16 "
        "[%0],[%1],%2,%3,{%4,%4,%4,%4},p; }"
        :: "r"(d), "r"(a), "l"(b), "r"(idesc), "r"(0u) : "memory");
}

template <bool RunMma, bool ReuseA, bool AFromTmem>
__device__ __forceinline__ void probe(uint64_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    __shared__ __align__(128) uint16_t a[128 * 16];
    __shared__ __align__(128) uint16_t b[16 * 128];
    __shared__ __align__(128) uint32_t scratch[1024];

    uint32_t tid = threadIdx.x;
    uint32_t warp = tid >> 5;
    uint32_t lane = tid & 31;
    for (int i = tid; i < 128 * 16; i += blockDim.x) a[i] = 0x3f80;
    for (int i = tid; i < 16 * 128; i += blockDim.x) b[i] = 0x3f80;
    if (tid == 0) init_bar(&bar);
    __syncthreads();
    if (warp == 0)
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0],512;" :: "r"((uint32_t)__cvta_generic_to_shared(&taddr_s))
            : "memory");
    __syncthreads();

    uint32_t taddr = taddr_s;
    uint32_t ataddr = taddr + 256;
    uint64_t ad = desc((uint32_t)__cvta_generic_to_shared(a));
    uint64_t bd = desc((uint32_t)__cvta_generic_to_shared(b));
    constexpr uint32_t id = (1u << 4) | (1u << 7) | (1u << 10)
                          | ((128 >> 3) << 17) | (8u << 24);
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    __syncthreads();

    if constexpr (AFromTmem) {
        if (warp < 4) {
            uint32_t ar[8];
#pragma unroll
            for (int i = 0; i < 8; ++i) ar[i] = 0x3f803f80u;
            asm volatile(
                "tcgen05.st.sync.aligned.32x32b.x8.b32 [%0],"
                "{%1,%2,%3,%4,%5,%6,%7,%8};"
                :: "r"(ataddr), "r"(ar[0]), "r"(ar[1]), "r"(ar[2]),
                   "r"(ar[3]), "r"(ar[4]), "r"(ar[5]), "r"(ar[6]),
                   "r"(ar[7]) : "memory");
            asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
        }
        __syncthreads();
    }

    if constexpr (RunMma) {
        if (warp == 0 && lane == 0) {
            uint64_t begin = clock64();
            if constexpr (AFromTmem) {
#pragma unroll 1
                for (int i = 0; i < kMmaOps; ++i)
                    mma_atmem(taddr, ataddr, bd, id);
            } else if constexpr (ReuseA) {
                mma_gdesc<1>(taddr, ad, bd, id);
#pragma unroll 1
                for (int i = 1; i < kMmaOps - 1; ++i)
                    mma_gdesc<2>(taddr, ad, bd, id);
                mma_gdesc<3>(taddr, ad, bd, id);
            } else {
#pragma unroll 1
                for (int i = 0; i < kMmaOps; ++i)
                    mma_gdesc<0>(taddr, ad, bd, id);
            }
            commit_wait(&bar);
            uint64_t end = clock64();
            out[0] = begin;
            out[1] = end;
        }
    }

    if (warp >= 1 && warp <= 4) {
        uint64_t begin = clock64();
        uint32_t sa = (uint32_t)__cvta_generic_to_shared(scratch) + lane * 16;
        uint32_t sink = lane;
#pragma unroll 1
        for (int i = 0; i < kLdsOpsPerWarp / 4; ++i) {
            uint32_t x[4][4];
#pragma unroll
            for (int j = 0; j < 4; ++j) {
                uint32_t sj = sa + j * 512;
                asm volatile(
                    "ld.shared.v4.u32 {%0,%1,%2,%3},[%4];"
                    : "=r"(x[j][0]), "=r"(x[j][1]),
                      "=r"(x[j][2]), "=r"(x[j][3]) : "r"(sj) : "memory");
            }
#pragma unroll
            for (int j = 0; j < 4; ++j)
                sink ^= x[j][0] ^ x[j][1] ^ x[j][2] ^ x[j][3];
        }
        uint64_t end = clock64();
        if (lane == 0) {
            int slot = 2 + 2 * (warp - 1);
            out[slot] = begin;
            out[slot + 1] = end;
            out[10 + warp - 1] = sink;
        }
    }

    __syncthreads();
    if (warp == 0) {
        asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0,512;"
                     :: "r"(taddr) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
            ::: "memory");
    }
}

}  // namespace

extern "C" __global__ void lds128x4_only(uint64_t *out) {
    probe<false, false, false>(out);
}
extern "C" __global__ void mma_gdesc_lds128x4(uint64_t *out) {
    probe<true, false, false>(out);
}
extern "C" __global__ void mma_reuse_lds128x4(uint64_t *out) {
    probe<true, true, false>(out);
}
extern "C" __global__ void mma_atmem_lds128x4(uint64_t *out) {
    probe<true, false, true>(out);
}
