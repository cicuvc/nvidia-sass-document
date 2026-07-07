#include <cstdint>

// warp-uniform SR (ctaid) feeding uniform datapath -> S2UR
__global__ void uctaid(int *o){
    int s = 0;
    for (unsigned i = 0; i < (unsigned)blockIdx.x; i++) s += i;   // uniform trip count
    o[0] = s;
}
__global__ void unsmid(int *o){
    unsigned s;
    asm volatile("mov.u32 %0, %%smid;" : "=r"(s));
    int acc = 0;
    for (unsigned i = 0; i < s; i++) acc += i;                    // uniform trip count from smid
    o[0] = acc;
}
__global__ void uctaid_addr(int *o, int *base){
    // ctaid used as uniform base offset for all lanes
    int *p = base + blockIdx.x * 256;
    o[threadIdx.x] = p[threadIdx.x];
}
