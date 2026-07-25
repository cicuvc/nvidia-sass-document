// TMA 2D load + bank0 probe around 0x348 — all in one kernel
// Build: nvcc -arch=sm_120 -O3 -cubin -o tests/tma_probe.cubin tests/tma_probe.cu
// Disasm: cuobjdump -arch sm_120 -sass tests/tma_probe.cubin

#include <cstdint>

struct CUtensorMap { uint64_t opaque[16]; };

// First param: probe output buffer (before TMA descend, so output[0..N] = probed values)
// Second param: TMA descriptor (__grid_constant__)
// Third param: TMA output buffer
__global__ void tma_probe(uint32_t* probe_out,
                          const __grid_constant__ CUtensorMap tma_desc,
                          uint16_t* gmem_out) {

    __shared__ alignas(128) uint16_t smem[16][16];
    __shared__ alignas(8)   uint64_t mbar;

    // ---- Phase 0: probe constant bank 0 at offsets around 0x348 ----
    if (threadIdx.x == 0) {
        // Read specific offsets via LDC (each requires its own asm)
        uint32_t v;
        asm("ldc.u32 %0, c[0x0][0x340];" : "=r"(v)); probe_out[0x340 / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x344];" : "=r"(v)); probe_out[0x344 / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x348];" : "=r"(v)); probe_out[0x348 / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x34c];" : "=r"(v)); probe_out[0x34c / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x350];" : "=r"(v)); probe_out[0x350 / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x354];" : "=r"(v)); probe_out[0x354 / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x358];" : "=r"(v)); probe_out[0x358 / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x35c];" : "=r"(v)); probe_out[0x35c / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x360];" : "=r"(v)); probe_out[0x360 / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x37c];" : "=r"(v)); probe_out[0x37c / 4] = v;
        asm("ldc.u32 %0, c[0x0][0x380];" : "=r"(v)); probe_out[0x380 / 4] = v;
    }

    // ---- Phase 1: TMA load (same as before) ----
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
