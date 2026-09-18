#include <cuda_runtime.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

extern "C" __global__ void get_vprintf_addr(std::uint64_t *out);
extern "C" __global__ void copy_code(const uint4 *src, uint4 *dst,
                                       unsigned count);

static void check(cudaError_t e, const char *what) {
    if (e != cudaSuccess) {
        std::fprintf(stderr, "%s: %s\n", what, cudaGetErrorString(e));
        std::exit(1);
    }
}
int main(int argc, char **argv) {
    unsigned count = argc > 1 ? std::strtoul(argv[1], nullptr, 0) : 256;
    std::uint64_t *daddr;
    check(cudaMalloc(&daddr, sizeof(*daddr)), "cudaMalloc address");
    get_vprintf_addr<<<1, 1>>>(daddr);
    check(cudaGetLastError(), "get_vprintf_addr launch");
    std::uint64_t addr = 0;
    check(cudaMemcpy(&addr, daddr, sizeof(addr), cudaMemcpyDeviceToHost),
          "copy address");
    std::printf("printf_va=0x%llx\n", (unsigned long long)addr);

    uint4 *dcode;
    check(cudaMalloc(&dcode, count * sizeof(uint4)), "cudaMalloc code");
    copy_code<<<(count + 63) / 64, 64>>>(
        reinterpret_cast<const uint4 *>(addr), dcode, count);
    check(cudaGetLastError(), "copy_code launch");
    auto *code = static_cast<uint4 *>(std::malloc(count * sizeof(uint4)));
    check(cudaMemcpy(code, dcode, count * sizeof(uint4), cudaMemcpyDeviceToHost),
          "copy code");
    FILE *f = std::fopen("/tmp/printf_device_code.bin", "wb");
    if (!f) return 2;
    std::fwrite(code, sizeof(uint4), count, f);
    std::fclose(f);
    std::printf("copied=%u bytes path=/tmp/printf_device_code.bin\n",
                count * (unsigned)sizeof(uint4));
    return 0;
}
