__global__ void k(int* o){ int t=threadIdx.x; o[t]=t*t+1; }
