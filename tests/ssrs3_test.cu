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

static __device__ __forceinline__ uint64_t opaque_add64(uint64_t x, uint64_t c) {
    uint64_t r;
    asm volatile("add.u64 %0, %1, %2;" : "=l"(r) : "l"(x), "l"(c));
    return r;
}

#define FENCE asm volatile("wgmma.fence.sync.aligned;" ::: "memory")
#define COMMIT asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory")
#define WAIT0 asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory")

#define SS_MMA(DD, DB)                                                  \
    asm volatile(                                                     \
        "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "       \
        "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"           \
        : "+f"(DD[0]), "+f"(DD[1]), "+f"(DD[2]), "+f"(DD[3]),         \
          "+f"(DD[4]), "+f"(DD[5]), "+f"(DD[6]), "+f"(DD[7])          \
        : "l"(da), "l"(DB))
#define RS_MMA(DD, DB)                                                  \
    asm volatile(                                                     \
        "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "       \
        "{%0,%1,%2,%3,%4,%5,%6,%7}, {%8,%9,%10,%11}, %12, 1, 1, 1, 0;" \
        : "+f"(DD[0]), "+f"(DD[1]), "+f"(DD[2]), "+f"(DD[3]),         \
          "+f"(DD[4]), "+f"(DD[5]), "+f"(DD[6]), "+f"(DD[7])          \
        : "r"(av[0]), "r"(av[1]), "r"(av[2]), "r"(av[3]), "l"(DB))

#define BARRIER1(DD)                                                    \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < 8; i++) asm volatile("" : "+f"(DD[i]) :: "memory")

#define TIMER                                                           \
    out[tid * 16 + 8] = __uint_as_float(t0);                            \
    out[tid * 16 + 9] = __uint_as_float(t1)
#define STORE1(DD, OFF)                                                 \
    _Pragma("unroll")                                                   \
    for (int i = 0; i < 8; i++) out[OFF + tid * 16 + i] = DD[i]

extern "C" __global__ void __launch_bounds__(128) ss2_16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    int tid = threadIdx.x;
    uint64_t da = make_desc(smem + 0x400);
    uint64_t db1 = make_desc(smem + 0xC00);
    uint64_t db2 = opaque_add64(db1, 0x20);
    float d[8] = {0,0,0,0,0,0,0,0}, e[8] = {0,0,0,0,0,0,0,0};
    BARRIER1(d); BARRIER1(e);
    FENCE;
    uint32_t t0 = clock();
    #pragma unroll
    for (int i = 0; i < 16; i++) { SS_MMA(d, db1); SS_MMA(e, db2); }
    COMMIT; WAIT0;
    uint32_t t1 = clock();
    STORE1(d, 0); STORE1(e, 2048); TIMER;
}
extern "C" __global__ void __launch_bounds__(128) ss2_32(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    int tid = threadIdx.x;
    uint64_t da = make_desc(smem + 0x400);
    uint64_t db1 = make_desc(smem + 0xC00);
    uint64_t db2 = opaque_add64(db1, 0x20);
    float d[8] = {0,0,0,0,0,0,0,0}, e[8] = {0,0,0,0,0,0,0,0};
    BARRIER1(d); BARRIER1(e);
    FENCE;
    uint32_t t0 = clock();
    #pragma unroll
    for (int i = 0; i < 32; i++) { SS_MMA(d, db1); SS_MMA(e, db2); }
    COMMIT; WAIT0;
    uint32_t t1 = clock();
    STORE1(d, 0); STORE1(e, 2048); TIMER;
}
extern "C" __global__ void __launch_bounds__(128) rs2_16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    int tid = threadIdx.x;
    uint64_t db1 = make_desc(smem + 0xC00);
    uint64_t db2 = opaque_add64(db1, 0x20);
    float d[8] = {0,0,0,0,0,0,0,0}, e[8] = {0,0,0,0,0,0,0,0};
    uint32_t av[4] = {0x3f803f80u,0x3f803f80u,0x3f803f80u,0x3f803f80u};
    BARRIER1(d); BARRIER1(e);
    FENCE;
    uint32_t t0 = clock();
    #pragma unroll
    for (int i = 0; i < 16; i++) { RS_MMA(d, db1); RS_MMA(e, db2); }
    COMMIT; WAIT0;
    uint32_t t1 = clock();
    STORE1(d, 0); STORE1(e, 2048); TIMER;
}
extern "C" __global__ void __launch_bounds__(128) rs2_32(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    int tid = threadIdx.x;
    uint64_t db1 = make_desc(smem + 0xC00);
    uint64_t db2 = opaque_add64(db1, 0x20);
    float d[8] = {0,0,0,0,0,0,0,0}, e[8] = {0,0,0,0,0,0,0,0};
    uint32_t av[4] = {0x3f803f80u,0x3f803f80u,0x3f803f80u,0x3f803f80u};
    BARRIER1(d); BARRIER1(e);
    FENCE;
    uint32_t t0 = clock();
    #pragma unroll
    for (int i = 0; i < 32; i++) { RS_MMA(d, db1); RS_MMA(e, db2); }
    COMMIT; WAIT0;
    uint32_t t1 = clock();
    STORE1(d, 0); STORE1(e, 2048); TIMER;
}
extern "C" __global__ void __launch_bounds__(128) ss4_16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    int tid = threadIdx.x;
    uint64_t da = make_desc(smem + 0x400);
    uint64_t db1 = make_desc(smem + 0xC00);
    uint64_t db2 = opaque_add64(db1, 0x20);
    uint64_t db3 = opaque_add64(db1, 0x40);
    uint64_t db4 = opaque_add64(db1, 0x60);
    float d[8] = {0}, e[8] = {0}, f[8] = {0}, g[8] = {0};
    BARRIER1(d); BARRIER1(e); BARRIER1(f); BARRIER1(g);
    FENCE;
    uint32_t t0 = clock();
    #pragma unroll
    for (int i = 0; i < 16; i++) { SS_MMA(d, db1); SS_MMA(e, db2); SS_MMA(f, db3); SS_MMA(g, db4); }
    COMMIT; WAIT0;
    uint32_t t1 = clock();
    STORE1(d, 0); STORE1(e, 2048); STORE1(f, 4096); STORE1(g, 6144); TIMER;
}
extern "C" __global__ void __launch_bounds__(128) rs4_16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    int tid = threadIdx.x;
    uint64_t db1 = make_desc(smem + 0xC00);
    uint64_t db2 = opaque_add64(db1, 0x20);
    uint64_t db3 = opaque_add64(db1, 0x40);
    uint64_t db4 = opaque_add64(db1, 0x60);
    float d[8] = {0}, e[8] = {0}, f[8] = {0}, g[8] = {0};
    uint32_t av[4] = {0x3f803f80u,0x3f803f80u,0x3f803f80u,0x3f803f80u};
    BARRIER1(d); BARRIER1(e); BARRIER1(f); BARRIER1(g);
    FENCE;
    uint32_t t0 = clock();
    #pragma unroll
    for (int i = 0; i < 16; i++) { RS_MMA(d, db1); RS_MMA(e, db2); RS_MMA(f, db3); RS_MMA(g, db4); }
    COMMIT; WAIT0;
    uint32_t t1 = clock();
    STORE1(d, 0); STORE1(e, 2048); STORE1(f, 4096); STORE1(g, 6144); TIMER;
}
