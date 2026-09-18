#include <cstdint>

// B200 UTCCP/STTM interaction probe.  Warp 0's lane 0 drives the CTA-wide
// shared->TMEM copy stream.  A second warp drives a collective STTM.x8 stream.
// Selecting warp 1 or warp 4 distinguishes a different-SMSP contender from a
// same-SMSP contender (the established warp-id modulo four mapping).

namespace {

constexpr int kCpOps = 512;
constexpr int kStOps = 16384;

__device__ __forceinline__ void init_mbarrier(uint64_t *bar) {
    uint32_t addr = static_cast<uint32_t>(__cvta_generic_to_shared(bar));
    asm volatile("mbarrier.init.shared.b64 [%0], 1;" :: "r"(addr) : "memory");
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

// CpMode: 0 = 128x256b, 1 = 64x128b.warpx2::01_23,
//         2 = 32x128b.warpx4.
template <int CpWarps, int StWarp, int StColumn,
          int CpMode = 0, int CpOps = kCpOps>
__device__ __forceinline__ void run_probe(uint64_t *out) {
    __shared__ uint32_t taddr_s;
    __shared__ __align__(8) uint64_t bar[4];
    __shared__ __align__(128) uint32_t src[4096];

    uint32_t tid = threadIdx.x;
    uint32_t warp = tid >> 5;
    uint32_t lane = tid & 31;
    for (int i = tid; i < 4096; i += blockDim.x)
        src[i] = 0xc0000000u | static_cast<uint32_t>(i);
    if constexpr (CpWarps > 0) {
        if (lane == 0 && warp < static_cast<uint32_t>(CpWarps))
            init_mbarrier(&bar[warp]);
    }
    __syncthreads();

    if (warp == 0) {
        asm volatile(
            "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
            "[%0], 32;" :: "r"(static_cast<uint32_t>(
                __cvta_generic_to_shared(&taddr_s))) : "memory");
    }
    __syncthreads();

    uint32_t taddr = taddr_s;
    uint32_t staddr = taddr + StColumn;
    uint32_t saddr = static_cast<uint32_t>(__cvta_generic_to_shared(src));
    uint64_t desc = ((uint64_t)(saddr & 0x3ffffu) >> 4)
                  | (1ull << 16) | (8ull << 32) | (1ull << 46);
    uint32_t r[8];
#pragma unroll
    for (int i = 0; i < 8; ++i)
        r[i] = 0x51000000u | (tid << 8) | static_cast<uint32_t>(i);
    asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
    __syncthreads();

    if constexpr (CpWarps > 0) {
        if (lane == 0 && warp < static_cast<uint32_t>(CpWarps)) {
            uint64_t begin = clock64();
            int count = CpOps;
            asm volatile("" : "+r"(count));
#pragma unroll 1
            for (int i = 0; i < count; ++i) {
                if constexpr (CpMode == 0) {
                    asm volatile(
                        "tcgen05.cp.cta_group::1.128x256b [%0], %1;"
                        :: "r"(taddr), "l"(desc) : "memory");
                } else if constexpr (CpMode == 1) {
                    asm volatile(
                        "tcgen05.cp.cta_group::1.64x128b."
                        "warpx2::01_23 [%0], %1;"
                        :: "r"(taddr), "l"(desc) : "memory");
                } else {
                    asm volatile(
                        "tcgen05.cp.cta_group::1.32x128b.warpx4 [%0], %1;"
                        :: "r"(taddr), "l"(desc) : "memory");
                }
            }
            commit_wait(&bar[warp]);
            uint64_t end = clock64();
            if (warp == 0) {
                out[0] = begin;
                out[1] = end;
            } else if (warp == 1) {
                out[4] = begin;
                out[5] = end;
            } else if (warp == 2) {
                out[6] = begin;
                out[7] = end;
            } else {
                out[8] = begin;
                out[9] = end;
            }
        }
    }

    if constexpr (StWarp >= 0) {
        if (warp == static_cast<uint32_t>(StWarp)) {
            uint64_t begin = clock64();
            int count = kStOps;
            asm volatile("" : "+r"(count));
#pragma unroll 1
            for (int i = 0; i < count; ++i) {
                asm volatile(
                    "tcgen05.st.sync.aligned.32x32b.x8.b32 [%0], "
                    "{%1,%2,%3,%4,%5,%6,%7,%8};"
                    :: "r"(staddr), "r"(r[0]), "r"(r[1]), "r"(r[2]),
                       "r"(r[3]), "r"(r[4]), "r"(r[5]), "r"(r[6]),
                       "r"(r[7]) : "memory");
            }
            asm volatile("tcgen05.wait::st.sync.aligned;" ::: "memory");
            uint64_t end = clock64();
            if (lane == 0) {
                out[2] = begin;
                out[3] = end;
            }
        }
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

extern "C" __global__ void cp_only(uint64_t *out) {
    run_probe<1, -1, 0>(out);
}

extern "C" __global__ void cp2_only(uint64_t *out) {
    run_probe<2, -1, 0>(out);
}

extern "C" __global__ void cp4_only(uint64_t *out) {
    run_probe<4, -1, 0>(out);
}

extern "C" __global__ void st_w1_only(uint64_t *out) {
    run_probe<0, 1, 0>(out);
}

extern "C" __global__ void st_w4_only(uint64_t *out) {
    run_probe<0, 4, 0>(out);
}

extern "C" __global__ void mix_w1_overlap(uint64_t *out) {
    run_probe<1, 1, 0>(out);
}

extern "C" __global__ void mix_w1_disjoint(uint64_t *out) {
    run_probe<1, 1, 8>(out);
}

extern "C" __global__ void mix_w4_overlap(uint64_t *out) {
    run_probe<1, 4, 0>(out);
}

extern "C" __global__ void mix_w4_disjoint(uint64_t *out) {
    run_probe<1, 4, 8>(out);
}

extern "C" __global__ void mix2_w4_overlap(uint64_t *out) {
    run_probe<2, 4, 0>(out);
}

extern "C" __global__ void mix2_w4_disjoint(uint64_t *out) {
    run_probe<2, 4, 8>(out);
}

extern "C" __global__ void mix4_w4_overlap(uint64_t *out) {
    run_probe<4, 4, 0>(out);
}

extern "C" __global__ void mix4_w4_disjoint(uint64_t *out) {
    run_probe<4, 4, 8>(out);
}

// Equal shared-source traffic relative to 512 x 128x256b copies:
// warpx2 needs 4x as many instructions and produces 2x the TMEM bytes;
// warpx4 needs 8x as many and produces 4x the TMEM bytes.
extern "C" __global__ void cp4_w2_norm_only(uint64_t *out) {
    run_probe<4, -1, 0, 1, 2048>(out);
}

extern "C" __global__ void mix4_w2_norm_overlap(uint64_t *out) {
    run_probe<4, 4, 0, 1, 2048>(out);
}

extern "C" __global__ void mix4_w2_norm_disjoint(uint64_t *out) {
    run_probe<4, 4, 8, 1, 2048>(out);
}

extern "C" __global__ void cp4_w4_norm_only(uint64_t *out) {
    run_probe<4, -1, 0, 2, 4096>(out);
}

extern "C" __global__ void mix4_w4_norm_overlap(uint64_t *out) {
    run_probe<4, 4, 0, 2, 4096>(out);
}

extern "C" __global__ void mix4_w4_norm_disjoint(uint64_t *out) {
    run_probe<4, 4, 8, 2, 4096>(out);
}
