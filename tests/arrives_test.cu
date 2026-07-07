__global__ void k(const int *g, int *out, int n){
    __shared__ int smem[256];
    __shared__ unsigned long long bar;
    int t = threadIdx.x;
    unsigned bs = (unsigned)__cvta_generic_to_shared(&bar);
    unsigned ss = (unsigned)__cvta_generic_to_shared(&smem[t]);
    if(t==0) asm volatile("mbarrier.init.shared.b64 [%0], %1;"::"r"(bs),"r"(blockDim.x));
    __syncthreads();
    // async copy global->shared
    asm volatile("cp.async.ca.shared.global [%0], [%1], 4;"::"r"(ss),"l"(g+t));
    // make the cp.async group's completion arrive on the mbarrier
    asm volatile("cp.async.mbarrier.arrive.shared.b64 [%0];"::"r"(bs));
    // also the noinc variant
    asm volatile("cp.async.mbarrier.arrive.noinc.shared.b64 [%0];"::"r"(bs));
    __syncthreads();
    out[t]=smem[t];
}
