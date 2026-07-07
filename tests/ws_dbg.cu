__global__ void s_all(int *a){ int i=threadIdx.x; a[i]+=a[i^1]; __syncwarp(); a[i]*=2; }
__global__ void s_mask(int *a,unsigned m){ int i=threadIdx.x; __syncwarp(m); a[i]*=2; }
__global__ void plain(int *a){ int i=threadIdx.x; a[i]=a[i]*3+1; }
