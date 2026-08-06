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

// OP: 0=FFMA rot, 1=FFMA reuse, 2=IMAD rot, 3=LDS
template <int OP>
__device__ __forceinline__ void storm(float* out, float* ts, uint8_t* smem) {
    float c[8], a[16], b[16];
    int tid = threadIdx.x;
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
            int ai = (OP == 1) ? 0 : ((i + k) & 15);
            int bi = (OP == 1) ? 0 : ((i * 3 + k * 5 + 7) & 15);
            if (OP == 0 || OP == 1)
                asm volatile("fma.rn.f32 %0, %1, %2, %0;"
                             : "+f"(c[k]) : "f"(a[ai]), "f"(b[bi]));
            else if (OP == 2)
                asm volatile("mad.lo.s32 %0, %1, %2, %0;"
                             : "+r"(reinterpret_cast<int&>(c[k]))
                             : "r"(reinterpret_cast<int&>(a[ai])),
                               "r"(reinterpret_cast<int&>(b[bi])));
            else {
                uint32_t addr = ((i * 8 + k) & 255) * 4;
                asm volatile("{ .reg .f32 t; ld.shared.f32 t, [%1]; add.f32 %0, t, %0; }"
                             : "+f"(c[k]) : "r"(addr) : "memory");
            }
        }
    }
    uint32_t t1 = clock();
    float s = 0;
    _Pragma("unroll")
    for (int k = 0; k < 8; k++) s += c[k];
    out[tid * 4] = s;
    ts[tid * 4] = __uint_as_float(t0);
    ts[tid * 4 + 1] = __uint_as_float(t1);
}

#define CHAIN_BODY                                                    \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};                            \
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");           \
    uint32_t t0 = clock();                                            \
    _Pragma("unroll")                                                 \
    for (int i = 0; i < KH; i++)                                      \
        asm volatile(                                                 \
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "   \
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"       \
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),         \
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])          \
            : "l"(da), "l"(db));                                      \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");    \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");    \
    uint32_t t1 = clock();                                            \
    int tid = threadIdx.x;                                            \
    float s = 0;                                                      \
    _Pragma("unroll")                                                 \
    for (int i = 0; i < 8; i++) s += d[i];                            \
    out[tid * 4] = s;                                                 \
    ts[tid * 4] = __uint_as_float(t0);                                \
    ts[tid * 4 + 1] = __uint_as_float(t1);

extern "C" __global__ void __launch_bounds__(512)
storm_flex(float* out, float* ts) {
    __shared__ __align__(1024) uint8_t smem[16384];
    storm<0>(out, ts, smem);
}
extern "C" __global__ void __launch_bounds__(128)
hgmma_solo(float* out, float* ts) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem);
    CHAIN_BODY
}
#define OVERLAY(NAME, OP)                                             \
extern "C" __global__ void __launch_bounds__(256)                     \
NAME(float* out, float* ts) {                                         \
    __shared__ __align__(1024) uint8_t smem[16384];                   \
    fill_ones(smem);                                                  \
    if (threadIdx.x < 128) { CHAIN_BODY }                             \
    else { storm<OP>(out, ts, smem); }                                \
}
OVERLAY(overlay_ffma_rot, 0)
OVERLAY(overlay_ffma_reuse, 1)
OVERLAY(overlay_imad_rot, 2)
OVERLAY(overlay_lds, 3)
