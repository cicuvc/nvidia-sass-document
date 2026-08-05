// mbarrier PTX op -> SASS capture study (sm_90 + sm_120).
// One kernel per op so the SASS mapping is unambiguous.
#include <cstdint>

__device__ __forceinline__ unsigned smem_addr(const void *p) {
    return (unsigned)__cvta_generic_to_shared(p);
}

// init: writes the arrive-count into the barrier state (atomic exchange)
extern "C" __global__ void mb_init(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], %1;\n"
                     :: "r"(smem_addr(&bar)), "r"(2));
    __syncthreads();
    if (threadIdx.x == 0) g[0] = bar;
}

// arrive (token in GPR)
extern "C" __global__ void mb_arrive(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    uint64_t tok;
    asm volatile("mbarrier.arrive.shared::cta.b64 %0, [%1];\n"
                 : "=l"(tok) : "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = tok;
}

// arrive.expect_tx (token + tx count)
extern "C" __global__ void mb_arrive_expect_tx(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    uint64_t tok;
    asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 %0, [%1], 128;\n"
                 : "=l"(tok) : "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = tok;
}

// expect_tx only (no arrive)
extern "C" __global__ void mb_expect_tx(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    asm volatile("mbarrier.expect_tx.shared::cta.b64 [%0], 64;\n"
                 :: "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = bar;
}

// try_wait.parity (poll loop)
extern "C" __global__ void mb_try_wait(uint64_t *g, int phase) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    unsigned p = smem_addr(&bar);
    unsigned ph = (unsigned)phase;
    asm volatile(
        "{\n"
        ".reg .pred P1;\n"
        "LAB_WAIT:\n"
        "mbarrier.try_wait.parity.acquire.cluster.shared::cta.b64 P1, [%0], %1;\n"
        "@P1 bra.uni DONE;\n"
        "bra.uni LAB_WAIT;\n"
        "DONE:\n"
        "}\n" :: "r"(p), "r"(ph));
    if (threadIdx.x == 0) g[0] = bar;
}

// test_wait.parity (single non-blocking check)
extern "C" __global__ void mb_test_wait(uint64_t *g, int phase) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    unsigned p = smem_addr(&bar);
    unsigned ph = (unsigned)phase;
    unsigned done = 0;
    asm volatile(
        "{.reg .pred P1;\n"
        "mbarrier.test_wait.parity.shared::cta.b64 P1, [%1], %2;\n"
        "selp.u32 %0, 1, 0, P1;}\n"
        : "=r"(done) : "r"(p), "r"(ph));
    if (threadIdx.x == 0) g[0] = done;
}

// inval
extern "C" __global__ void mb_inval(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    asm volatile("mbarrier.inval.shared::cta.b64 [%0];\n" :: "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = bar;
}

// cluster-scope arrive (distributed shared memory): sink destination `_`
extern "C" __global__ void mb_cluster(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    asm volatile("mbarrier.arrive.shared::cluster.b64 _, [%0];\n"
                 :: "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = bar;
}

// arrive with arbitrary count? (PTX mbarrier.arrive has no count; count via
// init only) — additionally test a 2-thread producer pattern used by
// cuda::barrier: init(2), two arrives.
extern "C" __global__ void mb_two_arrive(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 2;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    uint64_t tok;
    asm volatile("mbarrier.arrive.shared::cta.b64 %0, [%1];\n"
                 : "=l"(tok) : "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = tok;
}

// arrive_drop
extern "C" __global__ void mb_arrive_drop(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    uint64_t tok;
    asm volatile("mbarrier.arrive_drop.shared::cta.b64 %0, [%1];\n"
                 : "=l"(tok) : "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = tok;
}

// pending_count
extern "C" __global__ void mb_pending_count(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 2;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    uint64_t state;
    unsigned cnt;
    asm volatile("mbarrier.arrive.noComplete.release.cta.shared::cta.b64 %0, [%1], 1;\n"
                 : "=l"(state) : "r"(smem_addr(&bar)));
    asm volatile("mbarrier.pending_count.b64 %0, %1;\n"
                 : "=r"(cnt) : "l"(state));
    if (threadIdx.x == 0) g[0] = cnt;
}

// complete_tx
extern "C" __global__ void mb_complete_tx(uint64_t *g) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    asm volatile("mbarrier.expect_tx.shared::cta.b64 [%0], 128;\n"
                 :: "r"(smem_addr(&bar)));
    asm volatile("mbarrier.complete_tx.shared::cta.b64 [%0], 64;\n"
                 :: "r"(smem_addr(&bar)));
    if (threadIdx.x == 0) g[0] = bar;
}

// try_wait on a token/state (phase_type::primary form)
extern "C" __global__ void mb_try_wait_state(uint64_t *g, uint64_t state) {
    __shared__ uint64_t bar;
    if (threadIdx.x == 0)
        asm volatile("mbarrier.init.shared::cta.b64 [%0], 1;\n" :: "r"(smem_addr(&bar)));
    __syncthreads();
    unsigned p = smem_addr(&bar);
    unsigned done = 0;
    asm volatile(
        "{.reg .pred P1;\n"
        "mbarrier.try_wait.shared::cta.b64 P1, [%1], %2;\n"
        "selp.u32 %0, 1, 0, P1;}\n"
        : "=r"(done) : "r"(p), "l"(state));
    if (threadIdx.x == 0) g[0] = done;
}
