#include <cstdint>

// QSPC = SASS lowering of PTX isspacep.  Test every PTX space + width to
// capture the real encodings (including which QUERY_SPACE value each maps to).

__global__ void qspc_global_u32(unsigned *o, unsigned a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.global p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "r"(a));
    o[0] = p;
}

__global__ void qspc_global_u64(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.global p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

__global__ void qspc_local_u32(unsigned *o, unsigned a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.local p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "r"(a));
    o[0] = p;
}

__global__ void qspc_local_u64(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.local p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

__global__ void qspc_shared_u32(unsigned *o, unsigned a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.shared p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "r"(a));
    o[0] = p;
}

__global__ void qspc_shared_u64(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.shared p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

__global__ void qspc_shared_cta_u64(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.shared::cta p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

__global__ void qspc_shared_cluster_u64(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.shared::cluster p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

__global__ void qspc_const_u32(unsigned *o, unsigned a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.const p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "r"(a));
    o[0] = p;
}

__global__ void qspc_const_u64(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.const p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

// kernel parameter address -> .param::entry window
__global__ void qspc_param(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.param::entry p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

// Put the query result directly in a predicate used by a branch (Pu-only form)
__global__ void qspc_pred_branch(unsigned *o, unsigned long long a) {
    unsigned p;
    asm volatile(
        "{ .reg .pred p; isspacep.global p, %1;"
        "  @p bra $Lyes%=;"
        "  mov.u32 %0, 0;"
        "  bra $Lend%=;"
        "  $Lyes%=: mov.u32 %0, 1;"
        "  $Lend%=: }"
        : "=r"(p) : "l"(a));
    o[0] = p;
}

// __isGlobal-style intrinsic via cvta + isspacep: generic address of a global
// variable (real-world usage)
__device__ unsigned long long g_arr[16];

__global__ void qspc_real_global(unsigned *o) {
    unsigned long long g = (unsigned long long)(unsigned long long*)&g_arr[0];
    extern __shared__ unsigned long long sm[];
    unsigned long long s = (unsigned long long)(unsigned long long*)&sm[0];
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.global p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(g));
    o[0] = p;
    asm volatile("{ .reg .pred p; isspacep.shared p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(s));
    o[1] = p;
}

// Addresses computed in GPRs (data-dependent) force the non-URB encodings.
__global__ void qspc_gpr_u32(unsigned *o, unsigned *src) {
    unsigned a = src[threadIdx.x] + threadIdx.x;   // non-uniform -> GPR
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.global p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "r"(a));
    o[0] = p;
}

__global__ void qspc_gpr_u64(unsigned *o, unsigned long long *src) {
    unsigned long long a = src[threadIdx.x] + threadIdx.x;
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.global p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

__global__ void qspc_gpr_shared(unsigned *o, unsigned long long *src) {
    unsigned long long a = src[threadIdx.x] + threadIdx.x;
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.shared p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "l"(a));
    o[0] = p;
}

// 32-bit uniform address (no .E on the URB form)
__global__ void qspc_ur_u32(unsigned *o, unsigned a) {
    unsigned p;
    asm volatile("{ .reg .pred p; isspacep.shared p, %1; selp.u32 %0, 1, 0, p; }"
                 : "=r"(p) : "r"(a));
    o[0] = p;
}
