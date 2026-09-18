#include <cuda_runtime.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

__global__ void printf_target(std::uint64_t *out) {
    printf("sassdbg printf target probe\n");
    out[0] = 0xBAD0BAD0BAD0BAD0ull;
}

__global__ void copy_target_code(const uint4 *src, uint4 *dst,
                                 unsigned count) {
    unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < count)
        dst[i] = src[i];
}

static void check(cudaError_t e, const char *what) {
    if (e != cudaSuccess) {
        std::fprintf(stderr, "%s: %s\n", what, cudaGetErrorString(e));
        std::exit(1);
    }
}

int main(int argc, char **argv) {
    unsigned count = argc > 1 ? std::strtoul(argv[1], nullptr, 0) : 256;
    std::uint64_t *dout;
    check(cudaMalloc(&dout, sizeof(*dout)), "cudaMalloc output");
    printf_target<<<1, 1>>>(dout);
    check(cudaGetLastError(), "printf_target launch");
    std::uint64_t target = 0;
    check(cudaMemcpy(&target, dout, sizeof(target), cudaMemcpyDeviceToHost),
          "copy target");
    std::printf("printf_target_va=0x%llx\n", (unsigned long long)target);

    uint4 *dcode;
    check(cudaMalloc(&dcode, count * sizeof(uint4)), "cudaMalloc code");
    copy_target_code<<<(count + 63) / 64, 64>>>(
        reinterpret_cast<const uint4 *>(target), dcode, count);
    check(cudaGetLastError(), "copy_target_code launch");
    auto *code = static_cast<uint4 *>(std::malloc(count * sizeof(uint4)));
    check(cudaMemcpy(code, dcode, count * sizeof(uint4), cudaMemcpyDeviceToHost),
          "copy code");
    FILE *f = std::fopen("/tmp/printf_device_code.bin", "wb");
    if (!f) return 2;
    std::fwrite(code, sizeof(uint4), count, f);
    std::fclose(f);
    std::printf("copied=%u bytes path=/tmp/printf_device_code.bin\n",
                count * (unsigned)sizeof(uint4));

    // syscall_trampoline_vprintf has its relocated CALL.ABS immediate at
    // +0x1a0.  Decode the 55-bit SCALE-4 target and capture that callee in
    // the same CUDA context (code VAs are context/process specific).
    if (count > 0x1a0 / sizeof(uint4)) {
        auto *q = reinterpret_cast<const std::uint64_t *>(code) + 0x1a0 / 8;
        std::uint64_t lo = q[0], hi = q[1];
        std::uint64_t field = (lo >> 16) & 0xff;
        field |= ((lo >> 34) & ((1ull << 30) - 1)) << 8;
        field |= (hi & ((1ull << 17) - 1)) << 38;
        std::uint64_t callee = field << 2;
        std::printf("trampoline_callee_va=0x%llx\n",
                    (unsigned long long)callee);
        copy_target_code<<<(count + 63) / 64, 64>>>(
            reinterpret_cast<const uint4 *>(callee), dcode, count);
        check(cudaGetLastError(), "copy trampoline callee launch");
        check(cudaMemcpy(code, dcode, count * sizeof(uint4),
                         cudaMemcpyDeviceToHost), "copy trampoline callee");
        f = std::fopen("/tmp/printf_callee_code.bin", "wb");
        if (!f) return 3;
        std::fwrite(code, sizeof(uint4), count, f);
        std::fclose(f);
        std::printf("copied=%u bytes path=/tmp/printf_callee_code.bin\n",
                    count * (unsigned)sizeof(uint4));

        auto follow_abs_call = [&](unsigned call_off, const char *label,
                                   const char *path) {
            if (count <= call_off / sizeof(uint4)) return;
            q = reinterpret_cast<const std::uint64_t *>(code) + call_off / 8;
            lo = q[0]; hi = q[1];
            field = (lo >> 16) & 0xff;
            field |= ((lo >> 34) & ((1ull << 30) - 1)) << 8;
            field |= (hi & ((1ull << 17) - 1)) << 38;
            callee = field << 2;
            std::printf("%s=0x%llx\n", label, (unsigned long long)callee);
            copy_target_code<<<(count + 63) / 64, 64>>>(
                reinterpret_cast<const uint4 *>(callee), dcode, count);
            check(cudaGetLastError(), "follow CALL launch");
            check(cudaMemcpy(code, dcode, count * sizeof(uint4),
                             cudaMemcpyDeviceToHost), "follow CALL copy");
            FILE *next = std::fopen(path, "wb");
            if (!next) std::exit(4);
            std::fwrite(code, sizeof(uint4), count, next);
            std::fclose(next);
        };
        // vprintf+0xa0 -> vfprintf; vfprintf+0x50 -> vfprintf_internal.
        follow_abs_call(0xa0, "vfprintf_va",
                        "/tmp/vfprintf_device_code.bin");
        follow_abs_call(0x50, "vfprintf_internal_va",
                        "/tmp/vfprintf_internal_code.bin");
    }
    return 0;
}
