#include <cuda.h>
#include <cstdint>
#define KCHAIN 64
static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}
#define BODY                                                     \
    __shared__ __align__(1024) uint8_t smem[16384];              \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[8] = {0,0,0,0,0,0,0,0};                              \
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");      \
    _Pragma("unroll")                                            \
    for (int i = 0; i < KCHAIN; i++)                             \
        asm volatile(                                            \
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 " \
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"  \
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),    \
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])     \
            : "l"(da), "l"(db));                                 \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory"); \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory"); \
    int tid = threadIdx.x;                                       \
    _Pragma("unroll")                                            \
    for (int i = 0; i < 8; i++) out[tid*16+i] = d[i];

extern "C" __global__ void __launch_bounds__(128)
k_nofill(float* out) { BODY }
extern "C" __global__ void __launch_bounds__(128)
k_write(float* out) {
    ((uint32_t*)((char*)0)) ; 
    __shared__ __align__(1024) uint8_t smem2[1];
    asm volatile("" ::: "memory");
    uint64_t dummy;
    (void)dummy;
    {
      __shared__ __align__(1024) uint8_t smem[16384];
      uint32_t* s = (uint32_t*)smem;
      for (int i = threadIdx.x; i < 16384/4; i += 128) s[i] = 0x3f803f80u;
      __syncthreads();
      uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00);
      float d[8] = {0,0,0,0,0,0,0,0};
      asm volatile("wgmma.fence.sync.aligned;" ::: "memory");
      _Pragma("unroll")
      for (int i = 0; i < KCHAIN; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "l"(da), "l"(db));
      asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");
      asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");
      int tid = threadIdx.x;
      _Pragma("unroll")
      for (int i = 0; i < 8; i++) out[tid*16+i] = d[i];
    }
}
