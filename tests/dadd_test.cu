#include <cstdint>

__global__ void add(double *o, double *a, double *b){ o[threadIdx.x] = a[threadIdx.x] + b[threadIdx.x]; }
__global__ void sub(double *o, double *a, double *b){ o[threadIdx.x] = a[threadIdx.x] - b[threadIdx.x]; }
__global__ void addabs(double *o, double *a, double *b){ o[threadIdx.x] = fabs(a[threadIdx.x]) + b[threadIdx.x]; }
__global__ void rn(double *o, double *a, double *b){ o[threadIdx.x] = __dadd_rn(a[threadIdx.x], b[threadIdx.x]); }
__global__ void rz(double *o, double *a, double *b){ o[threadIdx.x] = __dadd_rz(a[threadIdx.x], b[threadIdx.x]); }
__global__ void ru(double *o, double *a, double *b){ o[threadIdx.x] = __dadd_ru(a[threadIdx.x], b[threadIdx.x]); }
__global__ void rd(double *o, double *a, double *b){ o[threadIdx.x] = __dadd_rd(a[threadIdx.x], b[threadIdx.x]); }
__global__ void addimm(double *o, double *a){ o[threadIdx.x] = a[threadIdx.x] + 2.5; }
__global__ void addconst(double *o, double *a, double c){ o[threadIdx.x] = a[threadIdx.x] + c; }
