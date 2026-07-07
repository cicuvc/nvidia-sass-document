#include <cstdint>
#include <cstdio>

__global__ void tid(int *o){
    o[0] = threadIdx.x; o[1] = threadIdx.y; o[2] = threadIdx.z;
}
__global__ void ctaid(int *o){
    o[0] = blockIdx.x; o[1] = blockIdx.y; o[2] = blockIdx.z;   // warp-uniform -> S2UR likely
}
__global__ void laneid(int *o){
    int l; asm volatile("mov.u32 %0, %%laneid;" : "=r"(l)); o[0] = l;
}
__global__ void lanemask(unsigned *o){
    unsigned e,lt,le,gt,ge;
    asm volatile("mov.u32 %0, %%lanemask_eq;" : "=r"(e));
    asm volatile("mov.u32 %0, %%lanemask_lt;" : "=r"(lt));
    asm volatile("mov.u32 %0, %%lanemask_le;" : "=r"(le));
    asm volatile("mov.u32 %0, %%lanemask_gt;" : "=r"(gt));
    asm volatile("mov.u32 %0, %%lanemask_ge;" : "=r"(ge));
    o[0]=e;o[1]=lt;o[2]=le;o[3]=gt;o[4]=ge;
}
__global__ void clk(unsigned long long *o){
    o[0] = clock64();
    o[1] = clock();
}
__global__ void smid(unsigned *o){
    unsigned s,w,n; 
    asm volatile("mov.u32 %0, %%smid;" : "=r"(s));
    asm volatile("mov.u32 %0, %%warpid;" : "=r"(w));
    asm volatile("mov.u32 %0, %%nsmid;" : "=r"(n));
    o[0]=s;o[1]=w;o[2]=n;
}
