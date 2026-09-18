#include <cstdio>
#include <cstdint>

extern "C" __global__ void get_vprintf_addr(std::uint64_t *out) {
    using host_sig_t = int (*)(const char *, ...);
    auto fn = (host_sig_t*)(&printf);
    out[0] = reinterpret_cast<std::uint64_t>(fn);
}

extern "C" __global__ void copy_code(const uint4 *src, uint4 *dst,
                                       unsigned count) {
    unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < count)
        dst[i] = src[i];
}
