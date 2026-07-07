#include <cooperative_groups.h>
namespace cg = cooperative_groups;
__global__ void k(int *a,int *out,int *ctr){
    int i=blockIdx.x*blockDim.x+threadIdx.x;
    // PTX elect.sync: leader election over a membermask
    unsigned m=__activemask(); unsigned leader; int pred;
    asm volatile("{ .reg .pred p; elect.sync %0|p, %2; selp.u32 %1,1,0,p; }"
                 : "=r"(leader),"=r"(pred) : "r"(m));
    if(pred) atomicAdd(ctr,1);
    // cg::invoke_one style: coalesced leader does the atomic
    if(a[i]>0){
        cg::coalesced_group g=cg::coalesced_threads();
        if(g.thread_rank()==0) out[i]=atomicAdd(ctr,g.size());
    }
}
