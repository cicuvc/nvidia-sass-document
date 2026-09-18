#include <cstdint>

// Port-contention probe: one warp launches M128N128K16 BF16->FP32 UTCHMMA,
// while another warp streams LDTM, STTM, or conflict-free LDS operations.

namespace {

constexpr int kMmaOps = 512;
constexpr int kTmemOps = 4096;
constexpr int kLdsOps = 8192;
constexpr int kLds128Ops = 2048;  // Same 1 MiB payload as kLdsOps scalar LDS.
constexpr int kSts128Ops = 2048;

__device__ __forceinline__ uint64_t desc(uint32_t a) {
    return ((uint64_t)(a & 0x3ffffu) >> 4)
         | (16ull << 16) | (8ull << 32) | (1ull << 46);
}

__device__ __forceinline__ void init_bar(uint64_t *bar) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(bar);
    asm volatile("mbarrier.init.shared.b64 [%0], 1;" :: "r"(a) : "memory");
}

__device__ __forceinline__ void commit_wait(uint64_t *bar) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(bar);
    asm volatile(
        "tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"
        :: "r"(a) : "memory");
    asm volatile(
        "{ .reg .pred p; L%=: mbarrier.try_wait.parity.shared.b64 p,[%0],0;"
        " @!p bra L%=; }" :: "r"(a) : "memory");
}

template <int Mode>
__device__ __forceinline__ void mma(uint32_t d, uint64_t a, uint64_t b,
                                    uint32_t idesc) {
#define DO_MMA(MOD)                                                        \
    asm volatile("{ .reg .pred p; setp.ne.u32 p, 1, 0; "                  \
                 "tcgen05.mma.cta_group::1.kind::f16" MOD                \
                 " [%0],%1,%2,%3,{%4,%4,%4,%4},p; }"                    \
                 :: "r"(d), "l"(a), "l"(b), "r"(idesc), "r"(0u)       \
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
        "{ .reg .pred p; setp.ne.u32 p, 0, 0; "
        "tcgen05.mma.cta_group::1.kind::f16 "
        "[%0],[%1],%2,%3,{%4,%4,%4,%4},p; }"
        :: "r"(d), "r"(a), "l"(b), "r"(idesc), "r"(0u) : "memory");
}

__device__ __forceinline__ uint32_t ldtm16(uint32_t a) {
    uint32_t r[16];
    asm volatile(
        "tcgen05.ld.sync.aligned.32x32b.x16.b32 "
        "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15},[%16];"
        : "=r"(r[0]), "=r"(r[1]), "=r"(r[2]), "=r"(r[3]),
          "=r"(r[4]), "=r"(r[5]), "=r"(r[6]), "=r"(r[7]),
          "=r"(r[8]), "=r"(r[9]), "=r"(r[10]), "=r"(r[11]),
          "=r"(r[12]), "=r"(r[13]), "=r"(r[14]), "=r"(r[15])
        : "r"(a) : "memory");
    return r[0];
}

__device__ __forceinline__ void sttm16(uint32_t a, const uint32_t *r) {
    asm volatile(
        "tcgen05.st.sync.aligned.32x32b.x16.b32 [%0],"
        "{%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15,%16};"
        :: "r"(a), "r"(r[0]), "r"(r[1]), "r"(r[2]), "r"(r[3]),
           "r"(r[4]), "r"(r[5]), "r"(r[6]), "r"(r[7]),
           "r"(r[8]), "r"(r[9]), "r"(r[10]), "r"(r[11]),
           "r"(r[12]), "r"(r[13]), "r"(r[14]), "r"(r[15]) : "memory");
}

enum Contender { None, Ldtm, Sttm, Lds, Lds128, Sts128 };

template <bool RunMma, bool ReuseA, Contender C, int N = 128,
          bool AFromTmem = false>
__device__ __forceinline__ void probe(uint64_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar;
    __shared__ __align__(128) uint16_t a[128 * 16];
    __shared__ __align__(128) uint16_t b[16 * 256];
    __shared__ __align__(128) uint32_t scratch[1024];
    uint32_t tid = threadIdx.x, warp = tid >> 5, lane = tid & 31;
    for (int i = tid; i < 128 * 16; i += blockDim.x) a[i] = 0x3f80;
    for (int i = tid; i < 16 * 256; i += blockDim.x) b[i] = 0x3f80;
    if (tid == 0) init_bar(&bar);
    __syncthreads();
    if (warp == 0)
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0],512;"
            :: "r"((uint32_t)__cvta_generic_to_shared(&taddr_s)) : "memory");
    __syncthreads();
    uint32_t taddr = taddr_s;
    uint32_t ataddr = taddr + 256;
    uint64_t ad = desc((uint32_t)__cvta_generic_to_shared(a));
    uint64_t bd = desc((uint32_t)__cvta_generic_to_shared(b));
    constexpr uint32_t id = (1u << 4) | (1u << 7) | (1u << 10)
                          | ((N >> 3) << 17) | (8u << 24);
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    __syncthreads();

    // A-from-TMEM consumes a 128x16 BF16 tile.  Four warps collectively
    // populate the four 32-row TMEM chunks; x8 32-bit columns = 32 B/row.
    if constexpr (AFromTmem) {
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
        __syncthreads();
    }

    if constexpr (RunMma) if (warp == 0 && lane == 0) {
        uint64_t begin = clock64();
        if constexpr (AFromTmem) {
#pragma unroll 1
            for (int i = 0; i < kMmaOps; ++i)
                mma_atmem(taddr, ataddr, bd, id);
        } else if constexpr (ReuseA) {
            mma<1>(taddr, ad, bd, id);
#pragma unroll 1
            for (int i = 1; i < kMmaOps - 1; ++i) mma<2>(taddr, ad, bd, id);
            mma<3>(taddr, ad, bd, id);
        } else {
#pragma unroll 1
            for (int i = 0; i < kMmaOps; ++i) mma<0>(taddr, ad, bd, id);
        }
        commit_wait(&bar);
        uint64_t end = clock64();
        out[0] = begin; out[1] = end;
    }

    if constexpr (C != None) {
        if (warp == 1) {
            uint64_t begin = clock64();
            uint32_t sink = lane;
            uint32_t regs[16];
#pragma unroll
            for (int i = 0; i < 16; ++i) regs[i] = tid * 17 + i;
            if constexpr (C == Ldtm) {
#pragma unroll 1
                for (int i = 0; i < kTmemOps; ++i) {
                    sink ^= ldtm16(taddr + 256);
                    if ((i & 7) == 7)
                        asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
                }
            } else if constexpr (C == Sttm) {
#pragma unroll 1
                for (int i = 0; i < kTmemOps; ++i) {
                    sttm16(taddr + 256, regs);
                    if ((i & 7) == 7)
                        asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
                }
            } else if constexpr (C == Lds) {
                uint32_t sa = (uint32_t)__cvta_generic_to_shared(a) + lane * 4;
#pragma unroll 1
                for (int i = 0; i < kLdsOps / 8; ++i) {
                    uint32_t x[8];
#pragma unroll
                    for (int j = 0; j < 8; ++j) {
                        uint32_t sj = sa + j * 128;
                        asm volatile("ld.shared.b32 %0,[%1];"
                                     : "=r"(x[j]) : "r"(sj) : "memory");
                    }
#pragma unroll
                    for (int j = 0; j < 8; ++j) sink ^= x[j];
                }
            } else if constexpr (C == Lds128) {
                uint32_t sa = (uint32_t)__cvta_generic_to_shared(a)
                            + lane * 16;
#pragma unroll 1
                for (int i = 0; i < kLds128Ops / 4; ++i) {
                    uint32_t x[4][4];
#pragma unroll
                    for (int j = 0; j < 4; ++j) {
                        uint32_t sj = sa + j * 512;
                        asm volatile(
                            "ld.shared.v4.u32 {%0,%1,%2,%3},[%4];"
                            : "=r"(x[j][0]), "=r"(x[j][1]),
                              "=r"(x[j][2]), "=r"(x[j][3])
                            : "r"(sj) : "memory");
                    }
#pragma unroll
                    for (int j = 0; j < 4; ++j)
                        sink ^= x[j][0] ^ x[j][1] ^ x[j][2] ^ x[j][3];
                }
            } else {
                uint32_t sa = (uint32_t)__cvta_generic_to_shared(scratch)
                            + lane * 16;
#pragma unroll 1
                for (int i = 0; i < kSts128Ops / 4; ++i) {
#pragma unroll
                    for (int j = 0; j < 4; ++j) {
                        uint32_t sj = sa + j * 512;
                        asm volatile(
                            "st.shared.v4.u32 [%0],{%1,%2,%3,%4};"
                            :: "r"(sj), "r"(regs[0]), "r"(regs[1]),
                               "r"(regs[2]), "r"(regs[3]) : "memory");
                    }
                }
            }
            uint64_t end = clock64();
            if (lane == 0) { out[2] = begin; out[3] = end; out[4] = sink; }
        }
    }
    __syncthreads();

    if constexpr (RunMma && AFromTmem) {
        uint32_t check;
        asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0},[%1];"
                     : "=r"(check) : "r"(taddr) : "memory");
        asm volatile("tcgen05.wait::ld.sync.aligned;" ::: "memory");
        if (tid == 0) out[4] = check;
    }
    __syncthreads();

    if (warp == 0) {
        asm volatile(
            "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0,512;"
            :: "r"(taddr) : "memory");
        asm volatile(
            "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;"
            ::: "memory");
    }
}

}  // namespace

#define KERNEL(NAME, RUN_MMA, REUSE, CONTENDER)                \
extern "C" __global__ void NAME(uint64_t *out) {               \
    probe<RUN_MMA, REUSE, CONTENDER>(out);                     \
}

KERNEL(mma_plain_only, true, false, None)
KERNEL(mma_reuse_only, true, true, None)
KERNEL(mma_plain_ldtm, true, false, Ldtm)
KERNEL(mma_reuse_ldtm, true, true, Ldtm)
KERNEL(mma_plain_sttm, true, false, Sttm)
KERNEL(mma_reuse_sttm, true, true, Sttm)
KERNEL(mma_plain_lds, true, false, Lds)
KERNEL(mma_reuse_lds, true, true, Lds)
KERNEL(ldtm_only, false, false, Ldtm)
KERNEL(sttm_only, false, false, Sttm)
KERNEL(lds_only, false, false, Lds)
KERNEL(lds128_only, false, false, Lds128)
KERNEL(mma_plain_lds128, true, false, Lds128)
KERNEL(mma_reuse_lds128, true, true, Lds128)
KERNEL(sts128_only, false, false, Sts128)
KERNEL(mma_plain_sts128, true, false, Sts128)
KERNEL(mma_reuse_sts128, true, true, Sts128)

extern "C" __global__ void mma_n8_plain_lds(uint64_t *out) {
    probe<true, false, Lds, 8>(out);
}

extern "C" __global__ void mma_n8_reuse_lds(uint64_t *out) {
    probe<true, true, Lds, 8>(out);
}

extern "C" __global__ void mma_n256_plain_lds(uint64_t *out) {
    probe<true, false, Lds, 256>(out);
}

extern "C" __global__ void mma_n256_reuse_lds(uint64_t *out) {
    probe<true, true, Lds, 256>(out);
}

extern "C" __global__ void mma_atmem_only(uint64_t *out) {
    probe<true, false, None, 128, true>(out);
}

extern "C" __global__ void mma_atmem_lds128(uint64_t *out) {
    probe<true, false, Lds128, 128, true>(out);
}

// Same 128-thread launch and idle warp population as the A-from-TMEM case.
extern "C" __global__ void mma_gdesc_lds128_128t(uint64_t *out) {
    probe<true, false, Lds128, 128, false>(out);
}

extern "C" __global__ void mma_atmem_sts128(uint64_t *out) {
    probe<true, false, Sts128, 128, true>(out);
}

extern "C" __global__ void mma_gdesc_sts128_128t(uint64_t *out) {
    probe<true, false, Sts128, 128, false>(out);
}

extern "C" __global__ void mma_atmem_n8_lds128(uint64_t *out) {
    probe<true, false, Lds128, 8, true>(out);
}

extern "C" __global__ void mma_atmem_n256_lds128(uint64_t *out) {
    probe<true, false, Lds128, 256, true>(out);
}

extern "C" __global__ void mma_atmem_n8_sts128(uint64_t *out) {
    probe<true, false, Sts128, 8, true>(out);
}

extern "C" __global__ void mma_atmem_n256_sts128(uint64_t *out) {
    probe<true, false, Sts128, 256, true>(out);
}
