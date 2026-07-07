#include <cstdint>

__global__ void r_add(unsigned *o, unsigned *v){ o[threadIdx.x] = __reduce_add_sync(0xffffffff, v[threadIdx.x]); }
__global__ void r_min_u(unsigned *o, unsigned *v){ o[threadIdx.x] = __reduce_min_sync(0xffffffff, v[threadIdx.x]); }
__global__ void r_max_u(unsigned *o, unsigned *v){ o[threadIdx.x] = __reduce_max_sync(0xffffffff, v[threadIdx.x]); }
__global__ void r_min_s(int *o, int *v){ o[threadIdx.x] = __reduce_min_sync(0xffffffff, v[threadIdx.x]); }
__global__ void r_max_s(int *o, int *v){ o[threadIdx.x] = __reduce_max_sync(0xffffffff, v[threadIdx.x]); }
__global__ void r_and(unsigned *o, unsigned *v){ o[threadIdx.x] = __reduce_and_sync(0xffffffff, v[threadIdx.x]); }
__global__ void r_or(unsigned *o, unsigned *v){ o[threadIdx.x] = __reduce_or_sync(0xffffffff, v[threadIdx.x]); }
__global__ void r_xor(unsigned *o, unsigned *v){ o[threadIdx.x] = __reduce_xor_sync(0xffffffff, v[threadIdx.x]); }
