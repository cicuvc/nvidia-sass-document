#include <cstdint>
#include <random>

__device__ void sync(){
asm volatile("barrier.cluster.arrive.release;\n");
    asm volatile("barrier.cluster.wait.acquire;\n");
    
}

__global__ __cluster_dims__(2,1,1) void tma_load(uint32_t* gmem, uint32_t *gmem_out) {

    __shared__ alignas(128) uint32_t smem[128];
    __shared__ alignas(8)   uint64_t mbar;

    uint32_t pred;
    asm volatile("{.reg .pred p0; elect.sync _|p0, 0xffffffff;selp.u32 %0, 1, 0, p0;}":"=r"(pred)::);

    uint32_t ccta;
    asm volatile("mov.b32 %0, %%cluster_ctarank;":"=r"(ccta)::);

    uint32_t smem_addr = __cvta_generic_to_shared(&smem[0]);
    uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);

    if (pred) {
        asm volatile("mbarrier.init.shared.b64 [%1], %0;\n"
                :: "r"(1), "r"(mbar_addr) : "memory");
        asm volatile("fence.proxy.async.shared::cluster;\n");
    }

    sync();

    if(ccta==0&&pred){
        asm volatile(
                "cp.async.bulk.shared::cluster.global.mbarrier::complete_tx::bytes.multicast::cluster"
                " [%0], [%1], %2, [%3], 0x3;\n"
                :: "r"(smem_addr), "l"(gmem), "n"(sizeof(smem)), "r"(mbar_addr)
                : "memory");

    }

    if(pred){
        asm volatile("mbarrier.arrive.expect_tx.shared::cluster.b64 _, [%0], %1;\n"
                     :: "r"(mbar_addr), "r"((uint32_t)sizeof(smem)));
    }

    // mbarrier wait — all threads participate
    {  
        asm("{ .reg .pred P1; WAIT: "
            "mbarrier.try_wait.parity.acquire.cluster.shared.b64 P1, [%0], %1;\n"
            "@P1 bra DONE; bra WAIT; DONE: }"
            :: "r"(mbar_addr), "r"(0));
    }

    if(ccta == 1){
        // Copy first row to global output for verification
        for(int i = 0; i < 128; i+=32) gmem_out[threadIdx.x + i] = smem[threadIdx.x + i];
    }
}

int main(){
    std::mt19937 rng;
    uint32_t *in_buf, *out_buf;
    cudaMallocManaged(&in_buf, 4096);
    cudaMallocManaged(&out_buf, 4096);

    for(int i = 0; i < 128; i++) in_buf[i] = rng();
    tma_load<<<2,32>>>(in_buf, out_buf);

    cudaDeviceSynchronize();
    for(int i = 0; i < 128; i++) if(in_buf[i]!=out_buf[i]) printf("Mismatch at %d, %u, %u\n", i, in_buf[i], out_buf[i]);

    return 0;
}
