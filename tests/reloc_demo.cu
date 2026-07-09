#include <cstdio>
__constant__ float cbuf[16];
__device__ int gvar;
__device__ __noinline__ int helper(int x){ return x*x + gvar; }
__global__ void maink(int* out){
    int t = threadIdx.x;
    int v = helper(t) + (int)cbuf[t & 15];
    if (v == 123456) printf("hit %d\n", v);
    out[t] = v;
}
