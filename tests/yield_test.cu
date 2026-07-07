// Spin-wait on a volatile global flag -> hope for YIELD in the poll loop.
__global__ void spinwait(volatile int *flag, int *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    while (flag[0] == 0) { /* busy-wait */ }
    out[i] = flag[1];
}
__global__ void spin_acq(int *lock, int *data, int *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    while (atomicCAS(lock, 0, 1) != 0) { /* spin */ }
    int v = data[0];
    atomicExch(lock, 0);
    out[i] = v;
}
