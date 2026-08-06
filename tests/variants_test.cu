// wgmma variant throughput probes (H20, sm_90a).
// Each kernel: 64-deep same-acc wgmma chain, clocked at issue-end and after wait.
// out layout per thread (16 floats): d[0..7], t0,t1,t2, pad...
#include <cuda.h>
#include <cstdint>

#define KCHAIN 64

static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}

static __device__ __forceinline__ void wg_fence() {
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
}
static __device__ __forceinline__ void wg_commit_wait() {
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");
}

extern "C" __global__ void __launch_bounds__(128)
chain_bf16_f32_n16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    wg_fence();
    uint32_t t0 = clock();
#pragma unroll
    for (int i = 0; i < KCHAIN; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "l"(da), "l"(db));
    uint32_t t1 = clock();
    wg_commit_wait();
    uint32_t t2 = clock();
    int tid = threadIdx.x;
#pragma unroll
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d[i];
    out[tid * 16 + 8] = __uint_as_float(t0); out[tid * 16 + 9] = __uint_as_float(t1); out[tid * 16 + 10] = __uint_as_float(t2);
}

extern "C" __global__ void __launch_bounds__(128)
chain_f16_f16_n16(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    uint32_t d[4] = {0, 0, 0, 0};  // 4 x f16x2
    wg_fence();
    uint32_t t0 = clock();
#pragma unroll
    for (int i = 0; i < KCHAIN; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f16.f16.f16 "
            "{%0,%1,%2,%3}, %4, %5, 1, 1, 1, 0, 0;"
            : "+r"(d[0]), "+r"(d[1]), "+r"(d[2]), "+r"(d[3])
            : "l"(da), "l"(db));
    uint32_t t1 = clock();
    wg_commit_wait();
    uint32_t t2 = clock();
    int tid = threadIdx.x;
#pragma unroll
    for (int i = 0; i < 4; i++) out[tid * 16 + i] = (float)d[i];
    out[tid * 16 + 8] = __uint_as_float(t0); out[tid * 16 + 9] = __uint_as_float(t1); out[tid * 16 + 10] = __uint_as_float(t2);
}

extern "C" __global__ void __launch_bounds__(128)
chain_fp8_f32_n16k32(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    wg_fence();
    uint32_t t0 = clock();
#pragma unroll
    for (int i = 0; i < KCHAIN; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k32.f32.e4m3.e4m3 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "l"(da), "l"(db));
    uint32_t t1 = clock();
    wg_commit_wait();
    uint32_t t2 = clock();
    int tid = threadIdx.x;
#pragma unroll
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d[i];
    out[tid * 16 + 8] = __uint_as_float(t0); out[tid * 16 + 9] = __uint_as_float(t1); out[tid * 16 + 10] = __uint_as_float(t2);
}

extern "C" __global__ void __launch_bounds__(128)
chain_bf16_f32_n16_areg(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    uint64_t db = make_desc(smem + 0xC00);
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    uint32_t a[4] = {0x3f803f80u, 0x3f803f80u, 0x3f803f80u, 0x3f803f80u};
    wg_fence();
    uint32_t t0 = clock();
#pragma unroll
    for (int i = 0; i < KCHAIN; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, {%8,%9,%10,%11}, %12, 1, 1, 1, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "r"(a[0]), "r"(a[1]), "r"(a[2]), "r"(a[3]), "l"(db));
    uint32_t t1 = clock();
    wg_commit_wait();
    uint32_t t2 = clock();
    int tid = threadIdx.x;
#pragma unroll
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d[i];
    out[tid * 16 + 8] = __uint_as_float(t0); out[tid * 16 + 9] = __uint_as_float(t1); out[tid * 16 + 10] = __uint_as_float(t2);
}
