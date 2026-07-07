__global__ void mrn(double *o,double *a,double *b){ o[threadIdx.x]=__dmul_rn(a[0],b[0]); }
__global__ void mrm(double *o,double *a,double *b){ o[threadIdx.x]=__dmul_rd(a[0],b[0]); }
__global__ void mrp(double *o,double *a,double *b){ o[threadIdx.x]=__dmul_ru(a[0],b[0]); }
__global__ void mrz(double *o,double *a,double *b){ o[threadIdx.x]=__dmul_rz(a[0],b[0]); }
__global__ void mneg(double *o,double *a,double *b){ o[threadIdx.x]=(-a[0])*b[0]; }
__global__ void mimm(double *o,double *a){ o[threadIdx.x]=a[0]*2.5; }
