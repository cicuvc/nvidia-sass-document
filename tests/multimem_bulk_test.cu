// multimem.cp.async.bulk : shared::cta -> multimem global (bulk copy to all GPUs).
#include <cstdint>

// weak form (no scope), no mask
extern "C" __global__ void mm_bulk_weak(void* __restrict__ dst, const void* __restrict__ src, int n) {
    unsigned s = __cvta_generic_to_shared(src);
    asm volatile("multimem.cp.async.bulk.weak.global.shared::cta.bulk_group [%0], [%1], %2;"
        :: "l"(dst), "r"(s), "r"(n) : "memory");
    asm volatile("cp.async.bulk.commit_group;");
}

// relaxed + scope
extern "C" __global__ void mm_bulk_gpu(void* __restrict__ dst, const void* __restrict__ src, int n) {
    unsigned s = __cvta_generic_to_shared(src);
    asm volatile("multimem.cp.async.bulk.relaxed.gpu.global.shared::cta.bulk_group [%0], [%1], %2;"
        :: "l"(dst), "r"(s), "r"(n) : "memory");
    asm volatile("cp.async.bulk.commit_group;");
}

// cp_mask + byteMask (b128 type)
extern "C" __global__ void mm_bulk_mask(void* __restrict__ dst, const void* __restrict__ src, int n, uint16_t bm) {
    unsigned s = __cvta_generic_to_shared(src);
    asm volatile("multimem.cp.async.bulk.relaxed.gpu.global.shared::cta.bulk_group.cp_mask.b128 [%0], [%1], %2, %3;"
        :: "l"(dst), "r"(s), "r"(n), "h"(bm) : "memory");
    asm volatile("cp.async.bulk.commit_group;");
}
