#include <cstdint>

__global__ void clk32(unsigned *o){ o[threadIdx.x] = clock(); }          // 32-bit SR_CLOCKLO
__global__ void clk64(unsigned long long *o){ o[threadIdx.x] = clock64(); } // 64-bit clock pair
__global__ void gtimer(unsigned long long *o){
    unsigned long long t; asm volatile("mov.u64 %0, %%globaltimer;" : "=l"(t)); o[threadIdx.x]=t;
}
