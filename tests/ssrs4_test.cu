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

#define A16 "+f"(d[0]),"+f"(d[1]),"+f"(d[2]),"+f"(d[3]),"+f"(d[4]),"+f"(d[5]),"+f"(d[6]),"+f"(d[7]),"+f"(d[8]),"+f"(d[9]),"+f"(d[10]),"+f"(d[11]),"+f"(d[12]),"+f"(d[13]),"+f"(d[14]),"+f"(d[15])
#define V16 "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15}"

#define SS32_MMA                                                        \
    asm volatile(                                                     \
        "wgmma.mma_async.sync.aligned.m64n32k16.f32.bf16.bf16 " V16   \
        ", %16, %17, 1, 1, 1, 0, 0;" : A16 : "l"(da), "l"(db))
#define RS32_MMA                                                        \
    asm volatile(                                                     \
        "wgmma.mma_async.sync.aligned.m64n32k16.f32.bf16.bf16 " V16   \
        ", {%16,%17,%18,%19}, %20, 1, 1, 1, 0;" : A16                 \
        : "r"(av[0]), "r"(av[1]), "r"(av[2]), "r"(av[3]), "l"(db))

#define KERN(NAME, OP, K)                                               \
extern "C" __global__ void __launch_bounds__(128) NAME(float* out) {    \
    __shared__ __align__(1024) uint8_t smem[16384];                     \
    fill_ones(smem);                                                    \
    int tid = threadIdx.x;                                              \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[16] = {};                                                   \
    uint32_t av[4] = {0x3f803f80u, 0x3f803f80u, 0x3f803f80u, 0x3f803f80u}; \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < 16; i++) asm volatile("" : "+f"(d[i]) :: "memory"); \
    FENCE;                                                              \
    uint32_t t0 = clock();                                              \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < K; i++) OP;                                     \
    COMMIT; WAIT0;                                                      \
    uint32_t t1 = clock();                                              \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < 16; i++) out[tid * 20 + i] = d[i];              \
    out[tid * 20 + 16] = __uint_as_float(t0);                           \
    out[tid * 20 + 17] = __uint_as_float(t1);                           \
}

KERN(ss32_1, SS32_MMA, 1)
KERN(rs32_1, RS32_MMA, 1)
KERN(ss32_8, SS32_MMA, 8)
KERN(rs32_8, RS32_MMA, 8)
KERN(ss32_16, SS32_MMA, 16)
KERN(rs32_16, RS32_MMA, 16)
KERN(ss32_32, SS32_MMA, 32)
KERN(rs32_32, RS32_MMA, 32)
