#include <cstdint>
#include <cstdlib>

__global__ void a_reg(int *o, int *v){ o[threadIdx.x] = abs(v[threadIdx.x]); }
__global__ void a_expr(int *o, int *v){ int x=v[threadIdx.x]; o[threadIdx.x] = x<0 ? -x : x; }
__global__ void a_param(int *o, int p){ o[threadIdx.x] = abs(p); }         // uniform/const source
__global__ void a_use(long long *o, int *v){ int x=v[threadIdx.x]; o[threadIdx.x] = (long long)abs(x) + 1; }
__global__ void a_llabs(long long *o, long long *v){ o[threadIdx.x] = llabs(v[threadIdx.x]); }
