#include <cstdint>

__global__ void ballot(unsigned *o, int *v){
    int lane = threadIdx.x & 31;
    o[lane] = __ballot_sync(0xffffffff, v[lane] > 0);
}
__global__ void any(int *o, int *v){
    int lane = threadIdx.x & 31;
    o[lane] = __any_sync(0xffffffff, v[lane] > 0);
}
__global__ void all(int *o, int *v){
    int lane = threadIdx.x & 31;
    o[lane] = __all_sync(0xffffffff, v[lane] > 0);
}
__global__ void uni(int *o, int *v){
    int lane = threadIdx.x & 31;
    o[lane] = __uni_sync(0xffffffff, v[lane] > 0);
}
__global__ void ballot_neg(unsigned *o, int *v){
    int lane = threadIdx.x & 31;
    o[lane] = __ballot_sync(0xffffffff, !(v[lane] > 0));
}
