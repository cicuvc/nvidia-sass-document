// Test the "accumulator lives inside the tensor core" hypothesis.
// If chained same-accumulator wgmma keep the running sum internal (no RF
// round-trip), then a NON-tensor read of the accumulator mid-chain must force a
// drain: expect an injected wgmma.wait_group before the read and a re-fence
// before resuming accumulation.
#include <cstdint>
#include <cuda_fp16.h>

__device__ __forceinline__ uint64_t md(uint32_t s){uint64_t d=0;d|=((uint64_t)(s&0x3FFFF)>>4);d|=((uint64_t)1)<<16;d|=((uint64_t)1)<<32;return d;}
#define MMA(D,DA,DB) asm volatile("wgmma.mma_async.sync.aligned.m64n16k16.f32.f16.f16 {%0,%1,%2,%3,%4,%5,%6,%7},%8,%9,1,1,1,0,0;\n":"+f"(D[0]),"+f"(D[1]),"+f"(D[2]),"+f"(D[3]),"+f"(D[4]),"+f"(D[5]),"+f"(D[6]),"+f"(D[7]):"l"(DA),"l"(DB))

// (A) baseline: 3 chained MMAs, read only at the end
extern "C" __global__ void chain_endread(float* o, const __half* gA, const __half* gB) {
    __shared__ __half sA[1024], sB[256]; int t=threadIdx.x;
    for(int i=t;i<1024;i+=blockDim.x)sA[i]=gA[i]; for(int i=t;i<256;i+=blockDim.x)sB[i]=gB[i]; __syncthreads();
    uint64_t dA=md(__cvta_generic_to_shared(sA)),dB=md(__cvta_generic_to_shared(sB));
    float d[8]; for(int i=0;i<8;i++)d[i]=0.f;
    float e[8]; for(int i=0;i<8;i++)e[i]=0.f;

    #pragma unroll
    for(int i=0;i<8;i++) asm volatile("":"+f"(d[i])::"memory");
    #pragma unroll
    for(int i=0;i<8;i++) asm volatile("":"+f"(e[i])::"memory");

    asm volatile("wgmma.fence.sync.aligned;\n");
    MMA(d,dA,dB); MMA(e,dA,dB); MMA(d,dA + 4,dB + 4); MMA(e,dA + 4 ,dB + 4); 
    asm volatile("wgmma.commit_group.sync.aligned;\n");
    asm volatile("wgmma.wait_group.sync.aligned 0;\n");
    for(int i=0;i<8;i++)o[t*8+i]=d[i]-e[i];
}

