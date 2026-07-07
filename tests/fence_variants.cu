__global__ void f_block(int*a,int*o){int i=threadIdx.x;a[i]+=1;__threadfence_block();o[i]=a[i];}
__global__ void f_gpu(int*a,int*o){int i=threadIdx.x;a[i]+=1;__threadfence();o[i]=a[i];}
__global__ void f_sys(int*a,int*o){int i=threadIdx.x;a[i]+=1;__threadfence_system();o[i]=a[i];}
__global__ void plain(int*a,int*o){int i=threadIdx.x;o[i]=a[i]+1;}
