#include <cuda.h>
#include <cstdint>

static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}
#define MMA(D,DA,DB) asm volatile( \
    "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 " \
    "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;" \
    : "+f"(D[0]), "+f"(D[1]), "+f"(D[2]), "+f"(D[3]), \
      "+f"(D[4]), "+f"(D[5]), "+f"(D[6]), "+f"(D[7]) \
    : "l"(DA), "l"(DB))

// Non-zero init for two independent accumulator groups, interleaved MMAs
// with asymmetric descriptor pairs (anti-CSE). BAR=1: fence-operand barriers.
template <int BAR>
__device__ __forceinline__ void body(float* o) {
    __shared__ __align__(1024) uint8_t smem[16384];
    uint32_t* s = (uint32_t*)smem;
    for (int i = threadIdx.x; i < 16384 / 4; i += blockDim.x) s[i] = 0x3f803f80u;
    __syncthreads();
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d0[8], d1[8];
    _Pragma("unroll")
    for (int i = 0; i < 8; i++) { d0[i] = 1.0f * (o[i] + 1); d1[i] = 0.5f * (o[i + 64] + 1); }
    if (BAR) {
        _Pragma("unroll")
        for (int i = 0; i < 8; i++) asm volatile("" : "+f"(d0[i]) :: "memory");
        _Pragma("unroll")
        for (int i = 0; i < 8; i++) asm volatile("" : "+f"(d1[i]) :: "memory");
    }
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    MMA(d0, da, db);     MMA(d1, da + 4, db + 4);
    MMA(d0, da + 4, db + 4); MMA(d1, da, db);
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");
    int t = threadIdx.x;
    _Pragma("unroll")
    for (int i = 0; i < 8; i++) { o[t * 16 + i] = d0[i]; o[t * 16 + 8 + i] = d1[i]; }
}

extern "C" __global__ void __launch_bounds__(128) k_init_bar(float* o) { body<1>(o); }
//extern "C" __global__ void __launch_bounds__(128) k_init_nobar(float* o) { body<0>(o); }
