#include <cooperative_groups.h>
#include <cooperative_groups/reduce.h>
namespace cg = cooperative_groups;

// A: __syncwarp in a loop with conditional return (EXIT) of some lanes
__global__ void kA(int *a,int *out,int n){
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    for(int k=0;k<n;k++){
        if(a[i*n+k]<0){ out[i]=-1; return; }
        __syncwarp();
    }
    out[i]=a[i];
}
// B: warp-aggregated atomic (coalesced_threads + elect + atomicAdd) — MATCH.ANY idiom
__global__ void kB(int *ctr,int *a,int *out){
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if(a[i]>0){
        cg::coalesced_group g=cg::coalesced_threads();
        int prev; if(g.thread_rank()==0) prev=atomicAdd(ctr,g.size());
        prev=g.shfl(prev,0);
        out[i]=prev+g.thread_rank();
    }
}
// C: strong system-scope store + __syncwarp after divergence (cusparse-like)
__global__ void kC(int *a,int *out){
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    if((a[i]&1)){ __threadfence_system(); atomicAdd_system(out+ (i&31),a[i]); }
    __syncwarp();
    out[i]=a[i];
}
