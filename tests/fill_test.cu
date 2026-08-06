// Data-dependence probe: same 64-MMA n16 chain, smem fill pattern as param.
#include <cuda.h>
#include <cstdint>
static __device__ __forceinline__ uint32_t gt_lo() {
    uint32_t v; asm volatile("mov.u32 %0, %%globaltimer_lo;" : "=r"(v)); return v;
}

#define KCHAIN 64

static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}

extern "C" __global__ void __launch_bounds__(128)
chain_fill(float* out, uint32_t fill, uint32_t do_fill) {
    __shared__ __align__(1024) uint8_t smem[16384];
    if (do_fill) {
        uint32_t* s = (uint32_t*)smem;
        for (int i = threadIdx.x; i < 16384 / 4; i += 128) s[i] = fill;
        __syncthreads();
    }
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    uint32_t t0 = clock(); uint32_t g0 = gt_lo();
#pragma unroll
    for (int i = 0; i < KCHAIN; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "l"(da), "l"(db));
    uint32_t t1 = clock();
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");
    uint32_t t2 = clock(); uint32_t g2 = gt_lo();
    int tid = threadIdx.x;
#pragma unroll
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d[i];
    out[tid * 16 + 8] = __uint_as_float(t0);
    out[tid * 16 + 9] = __uint_as_float(t1);
    out[tid * 16 + 10] = __uint_as_float(t2);
    out[tid * 16 + 11] = __uint_as_float(g0);
    out[tid * 16 + 12] = __uint_as_float(g2);
}
