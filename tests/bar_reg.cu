__global__ void k(int *a, int *out, int nbar, int cnt) {
    int i = blockIdx.x*blockDim.x+threadIdx.x;
    // runtime barrier index + count -> register forms
    asm volatile("bar.sync %0, %1;" :: "r"(nbar), "r"(cnt));
    asm volatile("bar.arrive %0, %1;" :: "r"(nbar), "r"(cnt));
    asm volatile("bar.sync %0;" :: "r"(nbar));      // reg barrier, no count -> RR?
    out[i] = a[i];
}
