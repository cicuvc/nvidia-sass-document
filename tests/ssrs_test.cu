#include <cuda.h>
#include <cstdint>

static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}

__device__ __forceinline__ void fill_ones(uint8_t* smem) {
    uint32_t* s = (uint32_t*)smem;
    for (int i = threadIdx.x; i < 16384 / 4; i += blockDim.x) s[i] = 0x3f803f80u;
    __syncthreads();
}

#define FENCE asm volatile("wgmma.fence.sync.aligned;" ::: "memory")
#define COMMIT_WAIT                            \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory"); \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory")

#define SS_MMA                                                          \
    asm volatile(                                                     \
        "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "       \
        "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"           \
        : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),             \
          "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])              \
        : "l"(da), "l"(db))
#define RS_MMA                                                          \
    asm volatile(                                                     \
        "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "       \
        "{%0,%1,%2,%3,%4,%5,%6,%7}, {%8,%9,%10,%11}, %12, 1, 1, 1, 0;" \
        : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),             \
          "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])              \
        : "r"(av[0]), "r"(av[1]), "r"(av[2]), "r"(av[3]), "l"(db))

#define PROLOGUE                                                        \
    __shared__ __align__(1024) uint8_t smem[16384];                     \
    fill_ones(smem);                                                    \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};                              \
    uint32_t av[4] = {0x3f803f80u, 0x3f803f80u, 0x3f803f80u, 0x3f803f80u}; \
    FENCE;
#define EPILOGUE                                                        \
    int tid = threadIdx.x;                                              \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d[i];               \
    out[tid * 16 + 8] = __uint_as_float(t0);                            \
    out[tid * 16 + 9] = __uint_as_float(t1);

// latency: K MMAs, timed from before first issue to after full drain
#define LAT_KERNEL(NAME, OP, K)                                         \
extern "C" __global__ void __launch_bounds__(128) NAME(float* out) {    \
    PROLOGUE                                                            \
    uint32_t t0 = clock();                                              \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < K; i++) OP;                                     \
    COMMIT_WAIT;                                                        \
    uint32_t t1 = clock();                                              \
    EPILOGUE                                                            \
}
// throughput: K chained MMAs, wall = drain of full chain
#define THRU_KERNEL(NAME, OP, K) LAT_KERNEL(NAME, OP, K)

LAT_KERNEL(lat_ss_1, SS_MMA, 1)
LAT_KERNEL(lat_ss_2, SS_MMA, 2)
LAT_KERNEL(lat_ss_4, SS_MMA, 4)
LAT_KERNEL(lat_ss_8, SS_MMA, 8)
LAT_KERNEL(lat_ss_16, SS_MMA, 16)
LAT_KERNEL(lat_rs_1, RS_MMA, 1)
LAT_KERNEL(lat_rs_2, RS_MMA, 2)
LAT_KERNEL(lat_rs_4, RS_MMA, 4)
LAT_KERNEL(lat_rs_8, RS_MMA, 8)
LAT_KERNEL(lat_rs_16, RS_MMA, 16)
THRU_KERNEL(thru_ss_32, SS_MMA, 32)
THRU_KERNEL(thru_ss_64, SS_MMA, 64)
THRU_KERNEL(thru_ss_128, SS_MMA, 128)
THRU_KERNEL(thru_rs_32, RS_MMA, 32)
THRU_KERNEL(thru_rs_64, RS_MMA, 64)
THRU_KERNEL(thru_rs_128, RS_MMA, 128)
