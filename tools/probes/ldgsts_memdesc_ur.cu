// Probe for the sm90/sm120 LDGSTS memdesc form:
//   LDGSTS ... [R + UR + imm], desc[UR][R.64 + imm], P
//
// Compile-only kernels show the ptxas selection rule.  probe_run also checks
// the generated instruction on hardware; CUDA 13.1 currently faults because
// ptxas stages the operands in UR4/UR5 but encodes UR0/UR1.

#include <cuda_runtime.h>

#include <cstdint>
#include <cstdio>

static __device__ __forceinline__ uint32_t smem_u32(const void *p) {
    return static_cast<uint32_t>(__cvta_generic_to_shared(p));
}

static __device__ __forceinline__ void cp16_default(uint32_t dst, const void *src,
                                                     uint32_t valid_bytes) {
    asm volatile("cp.async.cg.shared.global.L2::128B [%0], [%1], 16, %2;"
                 :: "r"(dst), "l"(src), "r"(valid_bytes) : "memory");
}

static __device__ __forceinline__ void cp16_policy(uint32_t dst, const void *src,
                                                    uint32_t valid_bytes,
                                                    uint64_t policy) {
    asm volatile("cp.async.cg.shared.global.L2::cache_hint [%0], [%1], 16, %2, %3;"
                 :: "r"(dst), "l"(src), "r"(valid_bytes), "l"(policy) : "memory");
}

extern "C" __global__ void probe_default(const char *__restrict__ src,
                                          uint32_t count) {
    extern __shared__ __align__(1024) char smem[];
    const uint32_t rel = (threadIdx.x & 31) * 16;
    cp16_default(smem_u32(smem) + rel + 0x810, src + rel + 0x120,
                 rel < count ? 16 : 0);
}

extern "C" __global__ void probe_policy(const char *__restrict__ src,
                                         uint32_t count, uint64_t policy) {
    extern __shared__ __align__(1024) char smem[];
    const uint32_t rel = (threadIdx.x & 31) * 16;
    cp16_policy(smem_u32(smem) + rel + 0x810, src + rel + 0x120,
                rel < count ? 16 : 0, policy);
}

// Two simultaneously live {shared base, policy} pairs expose the CUDA 13.1
// table-encoded uniform-register relocation bug particularly clearly.
extern "C" __global__ void probe_two_pairs(const char *__restrict__ src0,
                                            const char *__restrict__ src1,
                                            uint32_t shared_base0,
                                            uint32_t shared_base1,
                                            uint64_t policy0,
                                            uint64_t policy1) {
    const uint32_t rel = (threadIdx.x & 31) * 16;
    cp16_policy(shared_base0 + rel + 0x110, src0 + rel + 0x120, 16, policy0);
    cp16_policy(shared_base1 + rel + 0x210, src1 + rel + 0x220, 16, policy1);
}

extern "C" __global__ void probe_run(const uint32_t *__restrict__ src,
                                      uint32_t *__restrict__ out,
                                      uint32_t count) {
    extern __shared__ __align__(1024) char smem[];
    const uint32_t lane = threadIdx.x & 31;
    const uint32_t rel = lane * 16;
    uint64_t policy;
    asm("createpolicy.fractional.L2::evict_normal.b64 %0, %1;"
        : "=l"(policy) : "f"(1.0f));
    cp16_policy(smem_u32(smem) + rel + 0x810,
                reinterpret_cast<const char *>(src) + rel + 0x120,
                rel < count ? 16 : 0, policy);
    asm volatile("cp.async.commit_group;" ::: "memory");
    asm volatile("cp.async.wait_group 0;" ::: "memory");
    __syncthreads();
    out[lane] = *reinterpret_cast<uint32_t *>(smem + rel + 0x810);
}

int main() {
    uint32_t *src = nullptr;
    uint32_t *out = nullptr;
    cudaMallocManaged(&src, 1024 * sizeof(uint32_t));
    cudaMallocManaged(&out, 32 * sizeof(uint32_t));
    for (int i = 0; i < 1024; ++i) src[i] = 0x12340000u + i;
    for (int i = 0; i < 32; ++i) out[i] = 0;

    constexpr uint32_t count = 16 * 16;
    probe_run<<<1, 32, 4096>>>(src, out, count);
    const cudaError_t error = cudaDeviceSynchronize();
    bool correct = error == cudaSuccess;
    for (int lane = 0; lane < 32 && correct; ++lane)
        correct = out[lane] == (lane * 16 < count ? src[0x120 / 4 + lane * 4] : 0);
    std::printf("cuda=%s result=%s\n", cudaGetErrorString(error),
                correct ? "PASS" : "FAIL");
    return correct ? 0 : 1;
}
