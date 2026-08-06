// Is the slowdown pure code layout? Dead-branch-over-NOPs of varying size.
#include <cuda.h>
#include <cstdint>

#define KCHAIN 64

static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}

#define CHAIN64                                                     \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};                          \
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");         \
    uint32_t t0 = clock();                                          \
    _Pragma("unroll")                                               \
    for (int i = 0; i < KCHAIN; i++)                                \
        asm volatile(                                               \
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 " \
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"     \
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]),       \
              "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])        \
            : "l"(da), "l"(db));                                    \
    uint32_t t1 = clock();                                          \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");  \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");  \
    uint32_t t2 = clock();                                          \
    int tid = threadIdx.x;                                          \
    _Pragma("unroll")                                               \
    for (int i = 0; i < 8; i++) out[tid * 16 + i] = d[i];           \
    out[tid * 16 + 8] = __uint_as_float(t0);                        \
    out[tid * 16 + 9] = __uint_as_float(t1);                        \
    out[tid * 16 + 10] = __uint_as_float(t2);

#define NOPK(x) asm volatile("mov.u32 %0, %0;" : "+r"(x))

#define KERNEL_PAD(NAME, N)                                          \
extern "C" __global__ void __launch_bounds__(128)                    \
NAME(float* out, uint32_t do_fill) {                                 \
    __shared__ __align__(1024) uint8_t smem[16384];                  \
    if (do_fill) { _Pragma("unroll") for (int i = 0; i < N; i++) NOPK(i); } \
    CHAIN64                                                          \
}

KERNEL_PAD(chain_pad0, 0)
KERNEL_PAD(chain_pad16, 16)
KERNEL_PAD(chain_pad64, 64)
KERNEL_PAD(chain_pad128, 128)
