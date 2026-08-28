// M2 pipeline smoke kernel: a minimal nvcc-built cubin that sassdbg lifts
// (cuobjdump text -> assembler dialect), instruments, and re-runs on the GPU.
// Rebuild: nvcc -arch=sm_120 -O3 -cubin -o tests/m2_smoke.cubin tests/m2_smoke.cu
extern "C" __global__ void k(const float* a, float* b, int n) {
    int i = threadIdx.x;
    if (i < n) {
        float x = a[i];
        b[i] = x * 2.0f + 1.0f;
    }
}
