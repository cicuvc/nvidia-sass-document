#include <cuda.h>
#include <cstdint>

static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}
#define KH 32

// A: interleave two INDEPENDENT accumulator groups, no re-init.
extern "C" __global__ void __launch_bounds__(128)
interleave_pure(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    uint32_t* s = (uint32_t*)smem;
    for (int i = threadIdx.x; i < 16384 / 4; i += 128) s[i] = 0x3f803f80u;
    __syncthreads();
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d0[8] = {0}, d1[8] = {0};
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    _Pragma("unroll")
    for (int i = 0; i < KH; i++) {
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d0[0]), "+f"(d0[1]), "+f"(d0[2]), "+f"(d0[3]),
              "+f"(d0[4]), "+f"(d0[5]), "+f"(d0[6]), "+f"(d0[7])
            : "l"(da), "l"(db));
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d1[0]), "+f"(d1[1]), "+f"(d1[2]), "+f"(d1[3]),
              "+f"(d1[4]), "+f"(d1[5]), "+f"(d1[6]), "+f"(d1[7])
            : "l"(da), "l"(db));
    }
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");
    int tid = threadIdx.x;
    _Pragma("unroll")
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d0[i] + d1[i];
}

// B: two sequential tiles — chain on d0, then RE-INIT d0 in C++ and chain again
//    (the "switch accumulator group" pattern with register reuse).
extern "C" __global__ void __launch_bounds__(128)
switch_reinit(float* out) {
    __shared__ __align__(1024) uint8_t smem[16384];
    uint32_t* s = (uint32_t*)smem;
    for (int i = threadIdx.x; i < 16384 / 4; i += 128) s[i] = 0x3f803f80u;
    __syncthreads();
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
    float d0[8] = {0};
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    _Pragma("unroll")
    for (int i = 0; i < KH; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d0[0]), "+f"(d0[1]), "+f"(d0[2]), "+f"(d0[3]),
              "+f"(d0[4]), "+f"(d0[5]), "+f"(d0[6]), "+f"(d0[7])
            : "l"(da), "l"(db));
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");
    int tid = threadIdx.x;
    _Pragma("unroll")
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d0[i];
    // second tile: re-init and chain again (same registers)
    _Pragma("unroll")
    for (int i = 0; i < 8; i++) d0[i] = 0.0f;
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
    _Pragma("unroll")
    for (int i = 0; i < KH; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d0[0]), "+f"(d0[1]), "+f"(d0[2]), "+f"(d0[3]),
              "+f"(d0[4]), "+f"(d0[5]), "+f"(d0[6]), "+f"(d0[7])
            : "l"(da), "l"(db));
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");
    _Pragma("unroll")
    for (int i = 0; i < 8; i++) out[tid * 16 + 8 + i] = d0[i];
}
