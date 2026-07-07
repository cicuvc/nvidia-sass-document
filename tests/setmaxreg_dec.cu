#include <cstdint>
__global__ void dec_24(int *a){ asm volatile("setmaxnreg.dec.sync.aligned.u32 24;"); a[threadIdx.x]=1; }
__global__ void dec_64(int *a){ asm volatile("setmaxnreg.dec.sync.aligned.u32 64;"); a[threadIdx.x]=1; }
__global__ void dec_96(int *a){ asm volatile("setmaxnreg.dec.sync.aligned.u32 96;"); a[threadIdx.x]=1; }
__global__ void dec_128(int *a){ asm volatile("setmaxnreg.dec.sync.aligned.u32 128;"); a[threadIdx.x]=1; }
