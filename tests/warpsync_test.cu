#include <cooperative_groups.h>
namespace cg = cooperative_groups;
__global__ void sw_all(int *a){ int i=threadIdx.x; a[i]+=a[i^1]; __syncwarp(); a[i]*=2; }
__global__ void sw_mask(int *a,unsigned m){ int i=threadIdx.x; a[i]+=a[i^1]; __syncwarp(m); a[i]*=2; }
__global__ void sw_active(int *a){
    int i=threadIdx.x;
    if(a[i]>0){ a[i]=__shfl_down_sync(0xffffffff,a[i],1); __syncwarp(); }
}
