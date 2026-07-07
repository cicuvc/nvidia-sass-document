#include <cstdint>

__global__ void many_u32(unsigned *o, int *v){
    int lane = threadIdx.x & 31;
    o[lane] = __match_any_sync(0xffffffff, v[lane]);
}
__global__ void many_u64(unsigned *o, unsigned long long *v){
    int lane = threadIdx.x & 31;
    o[lane] = __match_any_sync(0xffffffff, v[lane]);
}
__global__ void mall_u32(unsigned *o, int *v){
    int lane = threadIdx.x & 31;
    int pred;
    o[lane] = __match_all_sync(0xffffffff, v[lane], &pred);
    if(pred) o[lane] |= 0x80000000u;
}
__global__ void mall_u64(unsigned *o, unsigned long long *v){
    int lane = threadIdx.x & 31;
    int pred;
    o[lane] = __match_all_sync(0xffffffff, v[lane], &pred);
    if(pred) o[lane] |= 0x80000000u;
}
__global__ void many_mask(unsigned *o, int *v, unsigned m){
    int lane = threadIdx.x & 31;
    o[lane] = __match_any_sync(m, v[lane]);
}
