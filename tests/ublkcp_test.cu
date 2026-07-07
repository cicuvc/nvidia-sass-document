#include <cuda_runtime.h>
#include <cstdint>

// cp.async.bulk (non-tensor) global -> shared::cluster with mbarrier tx-count
__global__ void bulk_g2s(const void* __restrict__ gsrc, int nbytes) {
    extern __shared__ __align__(16) char smem[];
    __shared__ __align__(8) uint64_t bar;
    if (threadIdx.x == 0) {
        asm volatile("mbarrier.init.shared.b64 [%0], 1;" :: "r"((uint32_t)__cvta_generic_to_shared(&bar)));
    }
    __syncthreads();
    if (threadIdx.x == 0) {
        uint32_t s = (uint32_t)__cvta_generic_to_shared(smem);
        uint32_t b = (uint32_t)__cvta_generic_to_shared(&bar);
        asm volatile("mbarrier.arrive.expect_tx.shared.b64 _, [%0], %1;" :: "r"(b), "r"(nbytes));
        asm volatile(
            "cp.async.bulk.shared::cluster.global.mbarrier::complete_tx::bytes [%0], [%1], %2, [%3];"
            :: "r"(s), "l"(gsrc), "r"(nbytes), "r"(b) : "memory");
    }
    __syncthreads();
}

// cp.async.bulk store shared::cta -> global (bulk_group)
__global__ void bulk_s2g(void* __restrict__ gdst, int nbytes) {
    extern __shared__ __align__(16) char smem[];
    if (threadIdx.x == 0) {
        uint32_t s = (uint32_t)__cvta_generic_to_shared(smem);
        asm volatile(
            "cp.async.bulk.global.shared::cta.bulk_group [%0], [%1], %2;"
            :: "l"(gdst), "r"(s), "r"(nbytes) : "memory");
        asm volatile("cp.async.bulk.commit_group;");
        asm volatile("cp.async.bulk.wait_group.read 0;");
    }
}

// cp.async.bulk multicast g -> s::cluster
__global__ void bulk_g2s_mc(const void* __restrict__ gsrc, int nbytes, uint16_t mask) {
    extern __shared__ __align__(16) char smem[];
    __shared__ __align__(8) uint64_t bar;
    if (threadIdx.x == 0) {
        uint32_t s = (uint32_t)__cvta_generic_to_shared(smem);
        uint32_t b = (uint32_t)__cvta_generic_to_shared(&bar);
        asm volatile(
            "cp.async.bulk.shared::cluster.global.mbarrier::complete_tx::bytes.multicast::cluster "
            "[%0], [%1], %2, [%3], %4;"
            :: "r"(s), "l"(gsrc), "r"(nbytes), "r"(b), "h"(mask) : "memory");
    }
}
