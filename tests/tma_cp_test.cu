// TMA 2D tensor load + mbarrier wait — minimal repro for SASS analysis
// Build: nvcc -arch=sm_120 -O3 -cubin -o tests/tma_simple.cubin tests/tma_simple.cu
// Disasm: cuobjdump -arch sm_120 -sass tests/tma_simple.cubin

#include <cstdint>
#include <random>

__global__ void tma_load(uint32_t* gmem, uint32_t *gmem_out) {

    __shared__ alignas(128) uint32_t smem[128];
    __shared__ alignas(8)   uint64_t mbar;

    uint32_t pred;
    asm volatile("{.reg .pred p0; elect.sync _|p0, 0xffffffff;selp.u32 %0, 1, 0, p0;}":"=r"(pred)::);

    if (pred) {
        uint32_t smem_addr = __cvta_generic_to_shared(smem);
        uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);

        asm volatile(
            "mbarrier.init.shared::cta.b64 [%1], %0;\n"
            :: "r"(1), "r"(mbar_addr) : "memory");

        asm volatile("fence.proxy.async.shared::cta;\n");

        asm volatile(
            "cp.async.bulk.shared::cta.global.mbarrier::complete_tx::bytes"
            " [%0], [%1], %2, [%3];\n"
            :: "r"(smem_addr), "l"(gmem), "n"(sizeof(smem)), "r"(mbar_addr)
            : "memory");

        asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 _, [%0], %1;\n"
                     :: "r"(mbar_addr), "r"((uint32_t)sizeof(smem)));
    }

    // mbarrier wait — all threads participate
    {
        uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);
       
        asm("{ .reg .pred P1; WAIT: "
            "mbarrier.try_wait.parity.acquire.cta.shared::cta.b64 P1, [%0], %1;\n"
            "@P1 bra DONE; bra WAIT; DONE: }"
            :: "r"(mbar_addr), "r"(0));
    }

    __syncthreads();

    // Copy first row to global output for verification
    for(int i = 0; i < 128; i+=32) gmem_out[threadIdx.x + i] = smem[threadIdx.x + i];
}

int main(){
    std::mt19937 rng;
    uint32_t *in_buf, *out_buf;
    cudaMallocManaged(&in_buf, 4096);
    cudaMallocManaged(&out_buf, 4096);

    for(int i = 0; i < 128; i++) in_buf[i] = rng();
    tma_load<<<1,32>>>(in_buf, out_buf);

    cudaDeviceSynchronize();
    for(int i = 0; i < 128; i++) if(in_buf[i]!=out_buf[i]) printf("Mismatch at %d\n", i);

    return 0;
}
