#include <algorithm>
#include <cuda_runtime.h>
#include <cstdint>
#include <cstdio>
#include <cuda.h>

// Two-phase canonical pattern, all compiled by ptxas:
//   phase1: cp.async.bulk.tensor.2d with descriptor (points to A)
//   modify descriptor global_address -> B via tensormap.replace + fences
//   phase2: cp.async.bulk.tensor.2d again, same descriptor address
template<bool fence=true> __global__ void __launch_bounds__(32)
k_canonical(uint64_t* dmap, uint64_t new_addr) {
    __shared__ __align__(128) unsigned char tile[512];
    __shared__ __align__(8) uint64_t mbar[2];
    unsigned s0 = (unsigned)__cvta_generic_to_shared(&tile[0]);
    unsigned s1 = (unsigned)__cvta_generic_to_shared(&tile[256]);
    unsigned m0 = (unsigned)__cvta_generic_to_shared(&mbar[0]);
    unsigned m1 = (unsigned)__cvta_generic_to_shared(&mbar[1]);

    if (threadIdx.x == 0) {
        asm volatile("mbarrier.init.shared.b64 [%0], 1;" :: "r"(m0));
        asm volatile("mbarrier.init.shared.b64 [%0], 1;" :: "r"(m1));
        asm volatile("fence.proxy.async.shared::cta;" ::: "memory");
        // phase 1 load (descriptor -> A)

        asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 _, [%0], %1;\n"
                     :: "r"(m0), "r"(256));
        asm volatile(
            "cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2, %3}], [%4];"
            :: "r"(s0), "l"(dmap), "r"(0), "r"(0), "r"(m0) : "memory");
    }
    __syncthreads();
    // wait phase 1
    {
        asm("{ .reg .pred P1; WAIT: "
            "mbarrier.try_wait.parity.acquire.cta.shared::cta.b64 P1, [%0], %1;\n"
            "@P1 bra DONE; bra WAIT; DONE: }"
            :: "r"(m0), "r"(0));
    }
   if(threadIdx.x == 0){
    printf("Phase1 => %u\n", (uint32_t)tile[0]);
   }

   __syncthreads();
    if (threadIdx.x == 0) {
        // modify the descriptor (global copy) and fence
        asm volatile(
            "tensormap.replace.tile.global_address.global.b1024.b64 [%0], %1;"
            :: "l"(dmap), "l"(new_addr) : "memory");
        if constexpr(fence){
            asm volatile("fence.proxy.tensormap::generic.release.gpu;" ::: "memory");
            asm volatile("fence.proxy.tensormap::generic.acquire.gpu [%0], 128;"
                     :: "l"(dmap) : "memory");
        }
        // phase 2 load (same descriptor address)

        asm volatile("mbarrier.arrive.expect_tx.shared::cta.b64 _, [%0], %1;\n"
                     :: "r"(m1), "r"(256));
        asm volatile(
            "cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes"
            " [%0], [%1, {%2, %3}], [%4];"
            :: "r"(s1), "l"(dmap), "r"(0), "r"(0), "r"(m1) : "memory");
    }

     __syncthreads();
    // wait phase 1
    {
        asm("{ .reg .pred P1; WAIT: "
            "mbarrier.try_wait.parity.acquire.cta.shared::cta.b64 P1, [%0], %1;\n"
            "@P1 bra DONE; bra WAIT; DONE: }"
            :: "r"(m1), "r"(0));
    }
   if(threadIdx.x == 0){
    printf("Phase1 => %u\n", (uint32_t)tile[256]);
   }
}


int main(){
    cuInit(0); CUdevice dev; CUcontext ctx;
    cuDeviceGet(&dev, 0); cuCtxCreate(&ctx, 0, dev);

    uint8_t* devPtr;
    cudaMallocManaged(&devPtr, 4096);

    std::fill(devPtr + 0, devPtr + 256, 1);
    std::fill(devPtr + 256, devPtr + 512, 3);


    // Create TMA descriptor
    CUtensorMap *tma;
    cudaMallocManaged(&tma, sizeof(CUtensorMap));

    cuuint64_t shape[]         = {16, 16};
    cuuint64_t stride[]        = {16 };
    cuuint32_t box[]           = {16, 16};
    cuuint32_t elem[]          = {1, 1};

    CUresult r = cuTensorMapEncodeTiled(
        tma, CUtensorMapDataType::CU_TENSOR_MAP_DATA_TYPE_UINT8, 2,
        devPtr, shape, stride, box, elem,
        CUtensorMapInterleave::CU_TENSOR_MAP_INTERLEAVE_NONE,
        CUtensorMapSwizzle::CU_TENSOR_MAP_SWIZZLE_NONE,
        CUtensorMapL2promotion::CU_TENSOR_MAP_L2_PROMOTION_NONE,
        CUtensorMapFloatOOBfill::CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE);
    if (r) {
        const char* s; cuGetErrorString(r, &s);
        printf("cuTensorMapEncodeTiled failed: %s\n", s);
        cudaFree(devPtr); cuCtxDestroy(ctx); return 1;
    }

    printf("=======With fence=======\n");
    k_canonical<<<1, 32>>>((uint64_t*)tma, uint64_t(devPtr + 256));
    cudaDeviceSynchronize();

    // reset descriptor
    r = cuTensorMapEncodeTiled(
        tma, CUtensorMapDataType::CU_TENSOR_MAP_DATA_TYPE_UINT8, 2,
        devPtr, shape, stride, box, elem,
        CUtensorMapInterleave::CU_TENSOR_MAP_INTERLEAVE_NONE,
        CUtensorMapSwizzle::CU_TENSOR_MAP_SWIZZLE_NONE,
        CUtensorMapL2promotion::CU_TENSOR_MAP_L2_PROMOTION_NONE,
        CUtensorMapFloatOOBfill::CU_TENSOR_MAP_FLOAT_OOB_FILL_NONE);
    if (r) {
        const char* s; cuGetErrorString(r, &s);
        printf("cuTensorMapEncodeTiled failed: %s\n", s);
        cudaFree(devPtr); cuCtxDestroy(ctx); return 1;
    }

    printf("=======Without fence=======\n");
    k_canonical<false><<<1, 32>>>((uint64_t*)tma, uint64_t(devPtr + 256));
    cudaDeviceSynchronize();
    return 0;
}