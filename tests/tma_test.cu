// TMA 2D load — verified working on SM120 (RTX 5090), CUDA 12.8
// Build: nvcc -arch=sm_120 -O3 -o tests/tma_test tests/tma_test.cu -lcuda
// Disasm: nvcc -arch=sm_120 -O3 -cubin -o tests/tma_test.cubin tests/tma_test.cu
//         cuobjdump -arch sm_120 -sass tests/tma_test.cubin
#include <cstdint>
#include <cstdio>
#include <cuda.h>
#include <cuda_fp16.h>

__global__ void tma_load(const __grid_constant__ CUtensorMap tma_desc,
                         void* gmem_out) {

    __shared__ alignas(128) half shmem[8][16];
    __shared__ alignas(8) uint64_t mbar;

    uint64_t desc = reinterpret_cast<uint64_t>(&tma_desc);

    if (threadIdx.x == 0) {
        uint32_t smem_addr = __cvta_generic_to_shared(shmem);
        uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);

        asm volatile(
            "mbarrier.init.shared::cta.b64 [%1], %0;\n"
            :: "r"(32), "r"(mbar_addr) : "memory");

        asm volatile("fence.proxy.async.shared::cta;\n");

        asm volatile(
            "cp.async.bulk.tensor.2d.shared::cta.global.tile"
            ".mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2, %3}], [%4];\n"
            :: "r"(smem_addr), "l"(desc), "r"(0), "r"(0), "r"(mbar_addr)
            : "memory");
    }

    // mbarrier arrive + try_wait (all threads participate)
    {
        uint64_t token;
        uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);
        if (threadIdx.x == 0) {
            asm volatile(
                "mbarrier.arrive.expect_tx.shared::cta.b64 %0, [%1], %2;\n"
                : "=l"(token) : "r"(mbar_addr), "r"(256));
        } else {
            asm volatile(
                "mbarrier.arrive.shared::cta.b64 %0, [%1];\n"
                : "=l"(token) : "r"(mbar_addr));
        }
        asm("{ .reg .pred P1; WAIT: "
            "mbarrier.try_wait.parity.acquire.cta.shared::cta.b64 P1, [%0], %1;\n"
            "@P1 bra DONE; bra WAIT; DONE: }"
            :: "r"(mbar_addr), "r"(0));
    }

    __syncthreads();

    // --- Read TMA descriptor via PTX generic load ---
    if (threadIdx.x == 0) {
        uint64_t desc_addr = reinterpret_cast<uint64_t>(&tma_desc);
        uint32_t* out32 = (uint32_t*)gmem_out;
        out32[62] = (uint32_t)(desc_addr);
        out32[63] = (uint32_t)(desc_addr >> 32);
        
        // Try PTX generic load to read descriptor contents
        // Use split 64-bit address: hi32 in tmp2, lo32 in tmp1
        uint32_t addr_lo = (uint32_t)desc_addr;
        uint32_t addr_hi = (uint32_t)(desc_addr >> 32);
        uint32_t d[32];
        asm("cvta.to.global.u64 %0, %1;" : "=l"(desc_addr) : "l"(desc_addr));
        for (int i = 0; i < 32; i++) {
            asm("ld.b32 %0, [%1];" : "=r"(d[i]) : "l"(desc_addr + i*4));
        }
        for (int i = 0; i < 32; i++) out32[64 + i] = d[i];
    }

    // Verify by copying first two rows to global output
    half* out = (half*)gmem_out;
    if (threadIdx.x < 16) {
        out[threadIdx.x]      = shmem[0][threadIdx.x];
        out[threadIdx.x + 16] = shmem[1][threadIdx.x];
    }
}

int main() {
    cuInit(0); CUdevice dev; CUcontext ctx;
    cuDeviceGet(&dev, 0); cuCtxCreate(&ctx, 0, dev);

    // Prepare source data — 16×16 half values
    half h_src[16][16];
    for (int r = 0; r < 16; r++)
        for (int c = 0; c < 16; c++)
            h_src[r][c] = __float2half((float)(r * 100 + c) / 100.0f);

    half* d_src;
    cudaMalloc(&d_src, sizeof(h_src));
    cudaMemcpy(d_src, h_src, sizeof(h_src), cudaMemcpyHostToDevice);
    printf("d_src = %p  (TMA source data buffer)\n", (void*)d_src);

    // Create TMA descriptor
    CUtensorMap tma;
    cuuint64_t shape[]         = {16, 16};
    cuuint64_t stride[]        = {16 * 2};
    cuuint32_t box[]           = {16, 8};
    cuuint32_t elem[]          = {1, 1};

    CUresult r = cuTensorMapEncodeTiled(
        &tma, CUtensorMapDataType::CU_TENSOR_MAP_DATA_TYPE_FLOAT16, 2,
        d_src, shape, stride, box, elem,
        CUtensorMapInterleave::CU_TENSOR_MAP_INTERLEAVE_NONE,
        CUtensorMapSwizzle::CU_TENSOR_MAP_SWIZZLE_NONE,
        CUtensorMapL2promotion::CU_TENSOR_MAP_L2_PROMOTION_NONE,
        CUtensorMapFloatOOBfill::CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE);
    if (r) {
        const char* s; cuGetErrorString(r, &s);
        printf("cuTensorMapEncodeTiled failed: %s\n", s);
        cudaFree(d_src); cuCtxDestroy(ctx); return 1;
    }

    // Dump host-side CUtensorMap raw bytes
    printf("\n=== Host-side CUtensorMap (128 bytes) ===\n");
    uint32_t* tma_raw = (uint32_t*)&tma;
    for (int i = 0; i < 32; i++) {
        printf("  tma[%2d] = 0x%08x", i, tma_raw[i]);
        if (i % 4 == 3) printf("\n");
    }

    // Output buffer — large enough for tile data + probe values
        // Increase output buffer to hold probe data
    // Output buffer — large enough for tile (64B) + desc addr (at offset 256B)
    half* d_out;
    cudaMalloc(&d_out, 1024);

    // Launch (1 CTA × 32 threads)
    tma_load<<<1, 32>>>(tma, d_out);
    cudaError_t e = cudaDeviceSynchronize();
    printf("TMA kernel: %s\n", cudaGetErrorString(e));

    if (e == cudaSuccess) {
        half h_out[512];
        cudaMemcpy(h_out, d_out, 1024, cudaMemcpyDeviceToHost);
        printf("Loaded 8x8 tile from 16x16 tensor (first 2 rows):\n");
        int ok = 1;
        for (int r = 0; r < 2; r++) {
            printf("  row %d: ", r);
            for (int c = 0; c < 16; c++) {
                float val = __half2float(h_out[r * 16 + c]);
                float exp = __half2float(h_src[r][c]);
                printf("%6.2f", val);
                if (c < 8 && fabsf(val - exp) > 0.01f) ok = 0;
            }
            printf("\n");
        }
        printf("%s\n", ok ? "TILE LOAD: ALL CORRECT" : "MISMATCHES FOUND");

        // Read probe values
        // Read desc_addr and descriptor first 32 bytes
        uint32_t* pv = (uint32_t*)((char*)h_out + 248);
        uint64_t desc_addr = pv[0] | ((uint64_t)pv[1] << 32);
        printf("\n=== Device-side descriptor (via cvta + ld.b32) at 0x%016lx ===\n", desc_addr);
        printf("  d_src = 0x%016lx\n", (uint64_t)(uintptr_t)d_src);
        int match = 1;
        for (int i = 0; i < 32; i++) {
            printf("  desc[%2d] = 0x%08x  %s%s\n", i, pv[2 + i],
                   pv[2 + i] == tma_raw[i] ? "HOST" : "DIFF",
                   pv[2 + i] != tma_raw[i] ? "" : "");
            if (pv[2 + i] != tma_raw[i]) match = 0;
        }
        printf("  %s\n", match ? "ALL 32 WORDS MATCH HOST" : "MISMATCHES FOUND");
    }

    cudaFree(d_src); cudaFree(d_out);
    cuCtxDestroy(ctx);
    return 0;
}
