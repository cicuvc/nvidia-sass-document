__global__ void frn(double *o,double *a,double *b,double *c){ o[threadIdx.x]=__fma_rn(a[0],b[0],c[0]); }
__global__ void frm(double *o,double *a,double *b,double *c){ o[threadIdx.x]=__fma_rd(a[0],b[0],c[0]); }
__global__ void frp(double *o,double *a,double *b,double *c){ o[threadIdx.x]=__fma_ru(a[0],b[0],c[0]); }
__global__ void frz(double *o,double *a,double *b,double *c){ o[threadIdx.x]=__fma_rz(a[0],b[0],c[0]); }
__global__ void fneg(double *o,double *a,double *b,double *c){ o[threadIdx.x]=__fma_rn(-a[0],b[0],-c[0]); }
