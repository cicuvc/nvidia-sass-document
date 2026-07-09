// tcgen05.fence::before/after_thread_sync — what do the specialized tcgen05
// fences lower to? Build:
//   nvcc -arch=sm_100a -cubin -o tests/tcgen05_fence_test.cubin tests/tcgen05_fence_test.cu
#include <cstdint>

extern "C" __global__ void fence_before(uint32_t* flag) {
    asm volatile("tcgen05.fence::before_thread_sync;\n" ::: "memory");
    asm volatile("st.relaxed.gpu.b32 [%0], 1;\n" :: "l"(flag) : "memory");
}

extern "C" __global__ void fence_after(uint32_t* flag) {
    uint32_t r;
    asm volatile("ld.relaxed.gpu.b32 %0, [%1];\n" : "=r"(r) : "l"(flag) : "memory");
    asm volatile("tcgen05.fence::after_thread_sync;\n" ::: "memory");
    flag[1] = r;
}

extern "C" __global__ void fence_both(uint32_t* flag) {
    asm volatile("tcgen05.fence::before_thread_sync;\n" ::: "memory");
    asm volatile("tcgen05.fence::after_thread_sync;\n" ::: "memory");
    (void)flag;
}
