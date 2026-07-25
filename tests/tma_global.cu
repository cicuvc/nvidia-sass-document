// TMA 2D load with descriptor in GLOBAL memory (not grid_constant)
// Current status: hangs on SM120 — TMA engine may require descriptor in grid-constant space.
// Build: nvcc -arch=sm_120 -O3 -o tests/tma_global tests/tma_global.cu -lcuda
#include <cstdint>
#include <cstdio>
#include <cuda.h>
#include <cuda_fp16.h>

__global__ void tma_global(CUtensorMap* tma_desc_ptr,
                            void* gmem_out) {

    __shared__ alignas(128) half shmem[8][16];
    __shared__ alignas(8) uint64_t mbar;

    uint64_t desc = reinterpret_cast<uint64_t>(tma_desc_ptr);

    if (threadIdx.x == 0) {
        uint32_t smem_addr = __cvta_generic_to_shared(shmem);
        uint32_t mbar_addr = __cvta_generic_to_shared(&mbar);

        asm volatile(
            "mbarrier.init.shared::cta.b64 [%1], %0;\n"
            :: "r"(1), "r"(mbar_addr) : "memory");

        asm volatile("fence.proxy.async.shared::cta;\n");

        asm volatile(
            "mbarrier.arrive.expect_tx.shared::cta.b64 _, [%0], %1;\n"
            :: "r"(mbar_addr), "r"(256));

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
        
        asm("{ .reg .pred P1; WAIT: "
            "mbarrier.try_wait.parity.acquire.cta.shared::cta.b64 P1, [%0], %1;\n"
            "@P1 bra DONE; bra WAIT; DONE: }"
            :: "r"(mbar_addr), "r"(0));
    }

    __syncthreads();

    half* out = (half*)gmem_out;
    if (threadIdx.x < 16) {
        out[threadIdx.x]      = shmem[0][threadIdx.x];
        out[threadIdx.x + 16] = shmem[1][threadIdx.x];
    }
}

int main() {
    setbuf(stdout, NULL);
    printf("TMA global-memory descriptor test\n");

    // Source data: 16×16 half values
    half h_src[16][16];
    for (int r = 0; r < 16; r++)
        for (int c = 0; c < 16; c++)
            h_src[r][c] = __float2half((float)(r * 100 + c) / 100.0f);

    half* d_src;
    cudaMalloc(&d_src, sizeof(h_src));
    cudaMemcpy(d_src, h_src, sizeof(h_src), cudaMemcpyHostToDevice);
    printf("d_src = %p\n", (void*)d_src);

    // Create TMA descriptor via Driver API
    CUtensorMap tma_host = {};
    cuuint64_t shape[]  = {16, 16};
    cuuint64_t stride[] = {16 * 2};
    cuuint32_t box[]    = {16, 8};
    cuuint32_t elem[]   = {1, 1};

    CUresult r = cuTensorMapEncodeTiled(
        &tma_host,
        CUtensorMapDataType::CU_TENSOR_MAP_DATA_TYPE_FLOAT16, 2,
        d_src, shape, stride, box, elem,
        CUtensorMapInterleave::CU_TENSOR_MAP_INTERLEAVE_NONE,
        CUtensorMapSwizzle::CU_TENSOR_MAP_SWIZZLE_NONE,
        CUtensorMapL2promotion::CU_TENSOR_MAP_L2_PROMOTION_NONE,
        CUtensorMapFloatOOBfill::CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE);
    printf("cuTensorMapEncodeTiled: %d\n", (int)r);
    if (r) return 1;

    // Copy descriptor from host to DEVICE global memory
    CUtensorMap* d_tma;
    cudaMalloc(&d_tma, sizeof(CUtensorMap));
    cudaMemcpy(d_tma, &tma_host, sizeof(CUtensorMap), cudaMemcpyHostToDevice);
    printf("d_tma = %p  (descriptor copy in global memory)\n", (void*)d_tma);

    // Verify: read descriptor back from device to confirm copy was correct
    {
        CUtensorMap verify;
        cudaMemcpy(&verify, d_tma, sizeof(CUtensorMap), cudaMemcpyDeviceToHost);
        int ok = (memcmp(&verify, &tma_host, sizeof(CUtensorMap)) == 0);
        printf("descriptor copy verify: %s\n", ok ? "OK" : "MISMATCH");
    }

    half* d_out;
    cudaMalloc(&d_out, 32 * sizeof(half));

    printf("launching kernel...\n");
    tma_global<<<1, 32>>>(d_tma, d_out);
    cudaError_t e = cudaDeviceSynchronize();
    printf("kernel result: %s\n", cudaGetErrorString(e));

    if (e == cudaSuccess) {
        half h_out[32];
        cudaMemcpy(h_out, d_out, sizeof(h_out), cudaMemcpyDeviceToHost);
        printf("Loaded tile (first row):\n  ");
        for (int c = 0; c < 16; c++)
            printf("%6.2f", __half2float(h_out[c]));
        printf("\n");
    }

    cudaFree(d_src);
    cudaFree(d_tma);
    cudaFree(d_out);
    return 0;
}
