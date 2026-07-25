// TMA 2D load — minimal working version for SASS analysis
// Build: nvcc -arch=sm_120 -O3 -cubin -o tests/tma_min.cubin tests/tma_min.cu

#include <cstdint>

struct CUtensorMap { uint64_t opaque[16]; };

__global__ void tma_min(const __grid_constant__ CUtensorMap tma_desc,
                        uint16_t* gmem_out) {

    __shared__ alignas(128) uint16_t smem[16][16];
    __shared__ alignas(8)   uint64_t mbar;

    if (threadIdx.x == 0) {
        uint32_t smem_addr = __cvta_generic_to_shared(smem);
        uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);
        uint64_t desc      = reinterpret_cast<uint64_t>(&tma_desc);

        asm volatile(
            "mbarrier.init.shared::cta.b64 [%1], %0;\n"
            :: "r"(16 * 16 * 2), "r"(mbar_addr) : "memory");

        asm volatile("fence.proxy.async.shared::cta;\n");

        asm volatile(
            "cp.async.bulk.tensor.2d.shared::cta.global.tile"
            ".mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2, %3}], [%4];\n"
            :: "r"(smem_addr), "l"(desc), "r"(0), "r"(0), "r"(mbar_addr)
            : "memory");
    }

    // mbarrier wait
    {
        uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);
        uint64_t token;
        asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 %0, [%1], %2;\n"
                     : "=l"(token) : "r"(mbar_addr), "r"(256));
        asm("{ .reg .pred P1; WAIT: "
            "mbarrier.try_wait.parity.acquire.cta.shared::cta.b64 P1, [%0], %1;\n"
            "@P1 bra DONE; bra WAIT; DONE: }"
            :: "r"(mbar_addr), "r"(0));
    }

    __syncthreads();

    if (threadIdx.x < 16) {
        gmem_out[threadIdx.x] = smem[0][threadIdx.x];
    }
}
