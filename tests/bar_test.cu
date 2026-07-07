#include <cooperative_groups.h>
namespace cg = cooperative_groups;
__global__ void k(int *a, int *out, int n) {
    __shared__ int s[256];
    int t = threadIdx.x, i = blockIdx.x*blockDim.x+t;
    s[t] = a[i];
    __syncthreads();                                   // BAR.SYNC
    int v = s[(t+1)&255];
    __syncthreads();
    // named barrier via PTX: arrive + sync on barrier 1 with count
    asm volatile("bar.arrive 1, 256;");                // BAR.ARV
    asm volatile("bar.sync 1, 256;");                  // BAR.SYNC named
    // barrier reduction (popc of predicate across block)
    int c = __syncthreads_count(v > 0);                // BAR.RED.POPC
    int aa = __syncthreads_and(v > 0);                 // BAR.RED.AND
    int oo = __syncthreads_or(v > 0);                  // BAR.RED.OR
    out[i] = v + c + aa + oo;
}
