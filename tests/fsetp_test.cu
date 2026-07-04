// FSETP encoding verification — sm_90
// Output to predicates; use standard C comparisons + existing FSET data

__device__ __noinline__ bool fsetp_lt(float a, float b) { return a < b; }
__device__ __noinline__ bool fsetp_gt(float a, float b) { return a > b; }
__device__ __noinline__ bool fsetp_eq(float a, float b) { return a == b; }
__device__ __noinline__ bool fsetp_ne(float a, float b) { return a != b; }

__device__ __noinline__ bool fsetp_lt_and(float a, float b, bool c) {
    return (a < b) && c;  // -> FSETP.LT.AND
}

extern "C" __global__ void fsetp_kernel(int *out, float a, float b, bool c) {
    out[0] = fsetp_lt(a, b) ? 1 : 0;
    out[1] = fsetp_gt(a, b) ? 1 : 0;
    out[2] = fsetp_eq(a, b) ? 1 : 0;
    out[3] = fsetp_ne(a, b) ? 1 : 0;
    out[4] = fsetp_lt_and(a, b, c) ? 1 : 0;
}
