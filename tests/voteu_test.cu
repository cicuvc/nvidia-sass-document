#include <cstdint>
#include <cooperative_groups.h>

// Try to make the ballot/vote result warp-uniform so ptxas uses the uniform datapath.
__global__ void popc_ballot(int *o, int *v){
    int lane = threadIdx.x & 31;
    unsigned b = __ballot_sync(0xffffffff, v[lane] > 0);
    o[blockIdx.x] = __popc(b);              // uniform use of ballot
}
__global__ void all_branch(int *o, int *v){
    int lane = threadIdx.x & 31;
    if (__all_sync(0xffffffff, v[lane] > 0)) {   // uniform branch
        o[blockIdx.x] = 1;
    }
}
__global__ void any_branch(int *o, int *v){
    int lane = threadIdx.x & 31;
    if (__any_sync(0xffffffff, v[lane] > 5)) {
        o[blockIdx.x] = 2;
    }
}
__global__ void activemask_popc(int *o){
    unsigned m = __activemask();
    o[blockIdx.x] = __popc(m);
}
__global__ void ballot_uniform_idx(int *o, int *v, int *t){
    int lane = threadIdx.x & 31;
    unsigned b = __ballot_sync(0xffffffff, v[lane] > 0);
    o[lane] = t[b & 31];                    // ballot as uniform index base
}
