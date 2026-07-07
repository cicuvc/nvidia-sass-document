// Non-inlined / recursive device functions force real CALL / RET on sm_90.
__device__ __noinline__ int leaf(int x, int y) { return x * y + (x ^ y); }

__device__ __noinline__ int fib(int n) {          // recursion -> CALL cannot inline
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

__global__ void k(const int *in, int *out, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    int v = in[i];
    out[i] = leaf(v, n) + fib(v & 7);
}
