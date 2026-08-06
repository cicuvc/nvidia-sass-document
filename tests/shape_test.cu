#include <cuda.h>
#include <cstdint>
static __device__ __forceinline__ uint64_t make_desc(const void* p) {
    uint32_t a = (uint32_t)__cvta_generic_to_shared(p);
    return 0x400000ull | ((uint64_t)((a & 0x3FFF0u) >> 4));
}
#define KCH 32
#define PROLOGUE                                                    \
    __shared__ __align__(1024) uint8_t smem[16384];                 \
    uint32_t* s = (uint32_t*)smem;                                  \
    for (int i = threadIdx.x; i < 16384/4; i += blockDim.x) s[i] = 0x3f803f80u; \
    __syncthreads();                                                \
    uint64_t da = make_desc(smem + 0x400), db = make_desc(smem + 0xC00); \
    asm volatile("wgmma.fence.sync.aligned;" ::: "memory");         \
    uint32_t t0 = clock();
#define EPILOGUE(NR)                                                \
    uint32_t t1 = clock();                                          \
    asm volatile("wgmma.commit_group.sync.aligned;" ::: "memory");  \
    asm volatile("wgmma.wait_group.sync.aligned 0;" ::: "memory");  \
    uint32_t t2 = clock();                                          \
    int tid = threadIdx.x;                                          \
    _Pragma("unroll")                                               \
    for (int i = 0; i < NR; i++) out[tid*144+i] = d[i];             \
    out[tid*144+140] = __uint_as_float(t0);                         \
    out[tid*144+141] = __uint_as_float(t1);                         \
    out[tid*144+142] = __uint_as_float(t2);


extern "C" __global__ void __launch_bounds__(128)
shape_n8(float* out) {
    PROLOGUE
    float d[4] = {0, 0, 0, 0};
    _Pragma("unroll")
    for (int i = 0; i < KCH; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n8k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3}, %4, %5, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3])
            : "l"(da), "l"(db));
    EPILOGUE(4)
}

extern "C" __global__ void __launch_bounds__(128)
shape_n16(float* out) {
    PROLOGUE
    float d[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    _Pragma("unroll")
    for (int i = 0; i < KCH; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]), "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7])
            : "l"(da), "l"(db));
    EPILOGUE(8)
}

extern "C" __global__ void __launch_bounds__(128)
shape_n32(float* out) {
    PROLOGUE
    float d[16] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    _Pragma("unroll")
    for (int i = 0; i < KCH; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n32k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15}, %16, %17, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]), "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7]), "+f"(d[8]), "+f"(d[9]), "+f"(d[10]), "+f"(d[11]), "+f"(d[12]), "+f"(d[13]), "+f"(d[14]), "+f"(d[15])
            : "l"(da), "l"(db));
    EPILOGUE(16)
}

extern "C" __global__ void __launch_bounds__(128)
shape_n64(float* out) {
    PROLOGUE
    float d[32] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    _Pragma("unroll")
    for (int i = 0; i < KCH; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n64k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15,%16,%17,%18,%19,%20,%21,%22,%23,%24,%25,%26,%27,%28,%29,%30,%31}, %32, %33, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]), "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7]), "+f"(d[8]), "+f"(d[9]), "+f"(d[10]), "+f"(d[11]), "+f"(d[12]), "+f"(d[13]), "+f"(d[14]), "+f"(d[15]), "+f"(d[16]), "+f"(d[17]), "+f"(d[18]), "+f"(d[19]), "+f"(d[20]), "+f"(d[21]), "+f"(d[22]), "+f"(d[23]), "+f"(d[24]), "+f"(d[25]), "+f"(d[26]), "+f"(d[27]), "+f"(d[28]), "+f"(d[29]), "+f"(d[30]), "+f"(d[31])
            : "l"(da), "l"(db));
    EPILOGUE(32)
}

extern "C" __global__ void __launch_bounds__(128)
shape_n128(float* out) {
    PROLOGUE
    float d[64] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    _Pragma("unroll")
    for (int i = 0; i < KCH; i++)
        asm volatile(
            "wgmma.mma_async.sync.aligned.m64n128k16.f32.bf16.bf16 "
            "{%0,%1,%2,%3,%4,%5,%6,%7,%8,%9,%10,%11,%12,%13,%14,%15,%16,%17,%18,%19,%20,%21,%22,%23,%24,%25,%26,%27,%28,%29,%30,%31,%32,%33,%34,%35,%36,%37,%38,%39,%40,%41,%42,%43,%44,%45,%46,%47,%48,%49,%50,%51,%52,%53,%54,%55,%56,%57,%58,%59,%60,%61,%62,%63}, %64, %65, 1, 1, 1, 0, 0;"
            : "+f"(d[0]), "+f"(d[1]), "+f"(d[2]), "+f"(d[3]), "+f"(d[4]), "+f"(d[5]), "+f"(d[6]), "+f"(d[7]), "+f"(d[8]), "+f"(d[9]), "+f"(d[10]), "+f"(d[11]), "+f"(d[12]), "+f"(d[13]), "+f"(d[14]), "+f"(d[15]), "+f"(d[16]), "+f"(d[17]), "+f"(d[18]), "+f"(d[19]), "+f"(d[20]), "+f"(d[21]), "+f"(d[22]), "+f"(d[23]), "+f"(d[24]), "+f"(d[25]), "+f"(d[26]), "+f"(d[27]), "+f"(d[28]), "+f"(d[29]), "+f"(d[30]), "+f"(d[31]), "+f"(d[32]), "+f"(d[33]), "+f"(d[34]), "+f"(d[35]), "+f"(d[36]), "+f"(d[37]), "+f"(d[38]), "+f"(d[39]), "+f"(d[40]), "+f"(d[41]), "+f"(d[42]), "+f"(d[43]), "+f"(d[44]), "+f"(d[45]), "+f"(d[46]), "+f"(d[47]), "+f"(d[48]), "+f"(d[49]), "+f"(d[50]), "+f"(d[51]), "+f"(d[52]), "+f"(d[53]), "+f"(d[54]), "+f"(d[55]), "+f"(d[56]), "+f"(d[57]), "+f"(d[58]), "+f"(d[59]), "+f"(d[60]), "+f"(d[61]), "+f"(d[62]), "+f"(d[63])
            : "l"(da), "l"(db));
    EPILOGUE(64)
}