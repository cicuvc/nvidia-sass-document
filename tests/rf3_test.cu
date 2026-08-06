#include <cuda.h>
#include <cstdint>
static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}
#define KH 64
#define NF 160
__device__ __forceinline__ void fill_ones(uint8_t* smem) {
    uint32_t* sp = (uint32_t*)smem;
    for (int i = threadIdx.x; i < 16384 / 4; i += blockDim.x) sp[i] = 0x3f803f80u;
    __syncthreads();
}
// SOP: 0=FFMA 3 reads, 1=FFMA 2 reads (1 imm), 2=IADD 1 read
template <int SOP>
__device__ __forceinline__ void storm(float* out, float* ts) {
    float c[8], a[16], b[16];
    int tid = threadIdx.x;
    int vi = tid * 3 + 1;
    _Pragma("unroll")
    for (int i = 0; i < 8; i++) c[i] = 0.01f * (i + 1);
    _Pragma("unroll")
    for (int i = 0; i < 16; i++) {
        a[i] = 0.5f + (tid + i) * 1e-3f;
        b[i] = 0.25f + (tid * 3 + i) * 7e-4f;
    }
    uint32_t t0 = clock();
    _Pragma("unroll")
    for (int i = 0; i < NF; i++) {
        _Pragma("unroll")
        for (int k = 0; k < 8; k++) {
            int ai = (i + k) & 15, bi = (i * 3 + k * 5 + 7) & 15;
            if (SOP == 0)
                asm volatile("fma.rn.f32 %0, %1, %2, %0;"
                             : "+f"(c[k]) : "f"(a[ai]), "f"(b[bi]));
            else if (SOP == 1)
                asm volatile("fma.rn.f32 %0, %1, 0f3F000000, %0;"
                             : "+f"(c[k]) : "f"(a[ai]));
            else
                asm volatile("{ .reg .b32 t; shr.b32 t, %0, 5; xor.b32 %0, %0, t; }"
                             : "+r"(vi));
        }
    }
    uint32_t t1 = clock();
    float s = 0;
    _Pragma("unroll")
    for (int k = 0; k < 8; k++) s += c[k];
    out[tid * 4] = s + (float)vi;
    ts[tid * 4] = __uint_as_float(t0);
    ts[tid * 4 + 1] = __uint_as_float(t1);
}


#define CHAIN_N8                                                   \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[4] = {0, 0, 0, 0};                                             \
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");         \
    uint32_t t0 = clock();                                          \
    _Pragma("unroll")                                               \
    for (int i = 0; i < KH; i++)                                    \
        asm volatile(                                               \
            "wgmma.mma_async.sync.aligned.m64n8k16.f32.bf16.bf16 " \
            "{%0,%1,%2,%3}, %4, %5, 1, 1, 1, 0, 0;"                      \
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3])                                                    \
            : "l"(da), "l"(db));                                    \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");  \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");  \
    uint32_t t1 = clock();                                          \
    int tid = threadIdx.x;                                          \
    float s = 0;                                                    \
    _Pragma("unroll")                                               \
    for (int i = 0; i < 4; i++) s += d[i];                         \
    out[tid * 4] = s;                                               \
    ts[tid * 4] = __uint_as_float(t0);                              \
    ts[tid * 4 + 1] = __uint_as_float(t1);


#define CHAIN_N16                                                   \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};                                             \
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");         \
    uint32_t t0 = clock();                                          \
    _Pragma("unroll")                                               \
    for (int i = 0; i < KH; i++)                                    \
        asm volatile(                                               \
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 " \
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"                      \
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]), "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])                                                    \
            : "l"(da), "l"(db));                                    \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");  \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");  \
    uint32_t t1 = clock();                                          \
    int tid = threadIdx.x;                                          \
    float s = 0;                                                    \
    _Pragma("unroll")                                               \
    for (int i = 0; i < 8; i++) s += d[i];                         \
    out[tid * 4] = s;                                               \
    ts[tid * 4] = __uint_as_float(t0);                              \
    ts[tid * 4 + 1] = __uint_as_float(t1);


#define CHAIN_N64                                                   \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[32] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};                                             \
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");         \
    uint32_t t0 = clock();                                          \
    _Pragma("unroll")                                               \
    for (int i = 0; i < KH; i++)                                    \
        asm volatile(                                               \
            "wgmma.mma_async.sync.aligned.m64n64k16.f32.bf16.bf16 " \
            "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15,%16,%17,%18,%19,%20,%21,%22,%23,%24,%25,%26,%27,%28,%29,%30,%31}, %32, %33, 1, 1, 1, 0, 0;"                      \
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]), "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7]), "+f"(d[8]), "+f"(d[9]), "+f"(d[10]), "+f"(d[11]), "+f"(d[12]), "+f"(d[13]), "+f"(d[14]), "+f"(d[15]), "+f"(d[16]), "+f"(d[17]), "+f"(d[18]), "+f"(d[19]), "+f"(d[20]), "+f"(d[21]), "+f"(d[22]), "+f"(d[23]), "+f"(d[24]), "+f"(d[25]), "+f"(d[26]), "+f"(d[27]), "+f"(d[28]), "+f"(d[29]), "+f"(d[30]), "+f"(d[31])                                                    \
            : "l"(da), "l"(db));                                    \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");  \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");  \
    uint32_t t1 = clock();                                          \
    int tid = threadIdx.x;                                          \
    float s = 0;                                                    \
    _Pragma("unroll")                                               \
    for (int i = 0; i < 32; i++) s += d[i];                         \
    out[tid * 4] = s;                                               \
    ts[tid * 4] = __uint_as_float(t0);                              \
    ts[tid * 4 + 1] = __uint_as_float(t1);


extern "C" __global__ void __launch_bounds__(128) storm3_flex(float* out, float* ts) { storm<0>(out, ts); }
extern "C" __global__ void __launch_bounds__(128) storm2_flex(float* out, float* ts) { storm<1>(out, ts); }
extern "C" __global__ void __launch_bounds__(128) storm1_flex(float* out, float* ts) { storm<2>(out, ts); }
#define OVERLAY(NAME, N, SOP)                                         \
extern "C" __global__ void __launch_bounds__(256)                     \
NAME(float* out, float* ts) {                                         \
    __shared__ __align__(1024) uint8_t smem[16384];                   \
    fill_ones(smem);                                                  \
    if (threadIdx.x < 128) { CHAIN_N##N }                             \
    else { storm<SOP>(out, ts); }                                     \
}
OVERLAY(ov_n16_ffma3, 16, 0)
OVERLAY(ov_n16_ffma2, 16, 1)
OVERLAY(ov_n16_fadd1, 16, 2)
OVERLAY(ov_n8_ffma3, 8, 0)
OVERLAY(ov_n64_ffma3, 64, 0)
extern "C" __global__ void __launch_bounds__(128)
solo_n8(float* out, float* ts) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    CHAIN_N8
}
extern "C" __global__ void __launch_bounds__(128)
solo_n64(float* out, float* ts) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    CHAIN_N64
}
extern "C" __global__ void __launch_bounds__(128)
solo_n16(float* out, float* ts) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    CHAIN_N16
}
