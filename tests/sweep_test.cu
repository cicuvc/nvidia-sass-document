#include <cuda.h>
#include <cstdint>

static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}
static __device__ __forceinline__ void fill_ones(uint8_t* smem, uint32_t pat) {
    uint32_t* s = (uint32_t*)smem;
    for (int i = threadIdx.x; i < 16384 / 4; i += 128) s[i] = pat;
    __syncthreads();
}
#define STORE_RESULTS(ND)                                       \
    uint32_t t1 = clock();                                      \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory"); \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory"); \
    uint32_t t2 = clock();                                      \
    int tid = threadIdx.x;                                      \
    _Pragma("unroll")                                           \
    for (int i = 0; i < ND; i++) out[tid * 16 + i] = d[i];      \
    out[tid * 16 + 8] = __uint_as_float(t0);                    \
    out[tid * 16 + 9] = __uint_as_float(t1);                    \
    out[tid * 16 + 10] = __uint_as_float(t2);

template <int K>
__device__ __forceinline__ void run_bf16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem, 0x3f803f80u);
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    uint32_t t0 = clock();
    _Pragma("unroll")
    for (int i = 0; i < K; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "l"(da), "l"(db));
    STORE_RESULTS(8)
}
template <int K>
__device__ __forceinline__ void run_f16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem, 0x3c003c00u);
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    uint32_t d[4] = {0, 0, 0, 0};
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    uint32_t t0 = clock();
    _Pragma("unroll")
    for (int i = 0; i < K; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f16.f16.f16 "
            "{%0,%1,%2,%3}, %4, %5, 1, 1, 1, 0, 0;"
            : "+r"(d[0]), "+r"(d[1]), "+r"(d[2]), "+r"(d[3])
            : "l"(da), "l"(db));
    STORE_RESULTS(4)
}
template <int K>
__device__ __forceinline__ void run_fp8(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem, 0x38383838u);
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    uint32_t t0 = clock();
    _Pragma("unroll")
    for (int i = 0; i < K; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k32.f32.e4m3.e4m3 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "l"(da), "l"(db));
    STORE_RESULTS(8)
}
template <int K>
__device__ __forceinline__ void run_areg(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    fill_ones(smem, 0x3f803f80u);
    uint64_t db = make_desc(smem + 0xC00);
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    uint32_t a[4] = {0x3f803f80u, 0x3f803f80u, 0x3f803f80u, 0x3f803f80u};
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    uint32_t t0 = clock();
    _Pragma("unroll")
    for (int i = 0; i < K; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, {%8,%9,%10,%11}, %12, 1, 1, 1, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "l"(db));
    STORE_RESULTS(8)
}

#define K4(NAME, FN)                                        \
extern "C" __global__ void __launch_bounds__(128) NAME##_##16(float* out) { FN<16>(out); } \
extern "C" __global__ void __launch_bounds__(128) NAME##_##32(float* out) { FN<32>(out); } \
extern "C" __global__ void __launch_bounds__(128) NAME##_##64(float* out) { FN<64>(out); } \
extern "C" __global__ void __launch_bounds__(128) NAME##_##128(float* out) { FN<128>(out); }

K4(k_bf16, run_bf16)
K4(k_f16, run_f16)
K4(k_fp8, run_fp8)
K4(k_areg, run_areg)
