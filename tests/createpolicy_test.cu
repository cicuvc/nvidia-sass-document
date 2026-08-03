#include <cuda.h>

__global__ void test_fractional_last(char* ptr) {
    asm volatile(".reg .b64 policy; "
                 "createpolicy.fractional.L2::evict_last.b64 policy, 1.0; "
                 "ld.global.L2::cache_hint.u32 %0, [%1], policy;"
                 : "=r"(*(int*)ptr) : "l"(ptr));
}

__global__ void test_fractional_first(char* ptr) {
    asm volatile(".reg .b64 policy; "
                 "createpolicy.fractional.L2::evict_first.b64 policy, 1.0; "
                 "ld.global.L2::cache_hint.u32 %0, [%1], policy;"
                 : "=r"(*(int*)ptr) : "l"(ptr));
}

__global__ void test_fractional_unchanged(char* ptr) {
    asm volatile(".reg .b64 policy; "
                 "createpolicy.fractional.L2::evict_unchanged.b64 policy, 1.0; "
                 "ld.global.L2::cache_hint.u32 %0, [%1], policy;"
                 : "=r"(*(int*)ptr) : "l"(ptr));
}

__global__ void test_fractional_last_05(char* ptr) {
    asm volatile(".reg .b64 policy; "
                 "createpolicy.fractional.L2::evict_last.b64 policy, 0.5; "
                 "ld.global.L2::cache_hint.u32 %0, [%1], policy;"
                 : "=r"(*(int*)ptr) : "l"(ptr));
}

__global__ void test_fractional_last_025(char* ptr) {
    asm volatile(".reg .b64 policy; "
                 "createpolicy.fractional.L2::evict_last.b64 policy, 0.25; "
                 "ld.global.L2::cache_hint.u32 %0, [%1], policy;"
                 : "=r"(*(int*)ptr) : "l"(ptr));
}

__global__ void test_fractional_last_075(char* ptr) {
    asm volatile(".reg .b64 policy; "
                 "createpolicy.fractional.L2::evict_last.b64 policy, 0.75; "
                 "ld.global.L2::cache_hint.u32 %0, [%1], policy;"
                 : "=r"(*(int*)ptr) : "l"(ptr));
}

__global__ void test_fractional_evict_normal(char* ptr) {
    asm volatile(".reg .b64 policy; "
                 "createpolicy.fractional.L2::evict_normal.b64 policy, 1.0; "
                 "ld.global.L2::cache_hint.u32 %0, [%1], policy;"
                 : "=r"(*(int*)ptr) : "l"(ptr));
}
