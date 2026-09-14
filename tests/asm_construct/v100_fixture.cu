#include <stdint.h>

extern "C" __global__ void v100_fixture(uint64_t *out) {
    out[threadIdx.x] = clock64();
}
