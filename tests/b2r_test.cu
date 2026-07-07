#include <cstdint>

// barrier reductions -> bar.red.{popc,and,or}
__global__ void scount(int *o, int *v){
    o[threadIdx.x] = __syncthreads_count(v[threadIdx.x] > 0);
}
__global__ void sand(int *o, int *v){
    o[threadIdx.x] = __syncthreads_and(v[threadIdx.x] > 0);
}
__global__ void sor(int *o, int *v){
    o[threadIdx.x] = __syncthreads_or(v[threadIdx.x] > 0);
}
// named barrier arrive/sync via cooperative groups / asm
__global__ void named_bar(int *o){
    asm volatile("bar.sync 1, 128;");
    o[threadIdx.x] = 1;
}
__global__ void bar_red_popc(int *o, int *v){
    unsigned r;
    asm volatile("{ .reg .pred %%p; setp.gt.s32 %%p, %1, 0; bar.red.popc.u32 %0, 2, 128, %%p; }"
                 : "=r"(r) : "r"(v[threadIdx.x]));
    o[threadIdx.x] = r;
}
