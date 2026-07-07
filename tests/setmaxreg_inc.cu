#include <cstdint>
__global__ void inc_64(int *a){ asm volatile("setmaxnreg.inc.sync.aligned.u32 64;"); a[threadIdx.x]=1; }
__global__ void inc_128(int *a){ asm volatile("setmaxnreg.inc.sync.aligned.u32 128;"); a[threadIdx.x]=1; }
__global__ void inc_192(int *a){ asm volatile("setmaxnreg.inc.sync.aligned.u32 192;"); a[threadIdx.x]=1; }
__global__ void inc_240(int *a){ asm volatile("setmaxnreg.inc.sync.aligned.u32 240;"); a[threadIdx.x]=1; }
