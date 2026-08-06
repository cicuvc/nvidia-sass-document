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
#define COMMIT asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory")
#define WAIT0 asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory")

// n8 shape: 4 acc regs -> lower pressure, hopefully no C7511 at large K
#define RS8_MMA                                                          \
    asm volatile(                                                      \
        "wgmma.mma_async.sync.aligned.m64n8k16.f32.bf16.bf16 "         \
        "{%0,%1,%2,%3}, {%4,%5,%6,%7}, %8, 1, 1, 1, 0;"                \
        : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3])               \
        : "r"(av[0]), "r"(av[1]), "r"(av[2]), "r"(av[3]), "l"(db))
#define RS16_MMA                                                         \
    asm volatile(                                                      \
        "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "        \
        "{%0,%1,%2,%3,%4,%5,%6,%7}, {%8,%9,%10,%11}, %12, 1, 1, 1, 0;" \
        : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),              \
          "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])               \
        : "r"(av[0]), "r"(av[1]), "r"(av[2]), "r"(av[3]), "l"(db))

#define PROLOGUE8                                                       \
    __shared__ __align__(1024) uint8_t smem[16384];                     \
    fill_ones(smem);                                                    \
    uint64_t db = make_desc(smem + 0xC00);                              \
    float d[4] = {0, 0, 0, 0};                                          \
    uint32_t av[4] = {0x3f803f80u, 0x3f803f80u, 0x3f803f80u, 0x3f803f80u}; \
    FENCE;
#define PROLOGUE16                                                      \
    __shared__ __align__(1024) uint8_t smem[16384];                     \
    fill_ones(smem);                                                    \
    uint64_t db = make_desc(smem + 0xC00);                              \
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};                              \
    uint32_t av[4] = {0x3f803f80u, 0x3f803f80u, 0x3f803f80u, 0x3f803f80u}; \
    FENCE;
#define EPILOGUE(NACC)                                                  \
    int tid = threadIdx.x;                                              \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < NACC; i++) out[tid * 16 + i] = d[i];            \
    out[tid * 16 + 8] = __uint_as_float(t0);                            \
    out[tid * 16 + 9] = __uint_as_float(t1);

#define K8(NAME, K)                                                     \
extern "C" __global__ void __launch_bounds__(128) NAME(float* out) {    \
    PROLOGUE8                                                           \
    uint32_t t0 = clock();                                              \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < K; i++) RS8_MMA;                                \
    COMMIT; WAIT0;                                                      \
    uint32_t t1 = clock();                                              \
    EPILOGUE(4)                                                         \
}
K8(rs8_32, 32)
K8(rs8_64, 64)
K8(rs8_128, 128)
K8(rs8_256, 256)

// find the n16 RS knee: latency chains of 8..40
#define K16(NAME, K)                                                    \
extern "C" __global__ void __launch_bounds__(128) NAME(float* out) {    \
    PROLOGUE16                                                          \
    uint32_t t0 = clock();                                              \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < K; i++) RS16_MMA;                               \
    COMMIT; WAIT0;                                                      \
    uint32_t t1 = clock();                                              \
    EPILOGUE(8)                                                         \
}
K16(rs16_12, 12)
K16(rs16_20, 20)
K16(rs16_24, 24)
K16(rs16_28, 28)
K16(rs16_40, 40)

// paced: bursts of B MMAs, wait 0 between bursts -> does slot-freeing restore the fast rate?
#define PACED(NAME, B, NB)                                              \
extern "C" __global__ void __launch_bounds__(128) NAME(float* out) {    \
    PROLOGUE16                                                          \
    uint32_t t0 = clock();                                              \
    _Pragma("unroll")                                                   \
    for (int j = 0; j < NB; j++) {                                      \
        _Pragma("unroll")                                               \
        for (int i = 0; i < B; i++) RS16_MMA;                           \
        COMMIT; WAIT0;                                                  \
    }                                                                   \
    uint32_t t1 = clock();                                              \
    EPILOGUE(8)                                                         \
}
PACED(rs16_p4x8, 4, 8)
PACED(rs16_p8x4, 8, 4)
PACED(rs16_p16x2, 16, 2)
