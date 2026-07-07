// UTMACCTL coverage: tensormap fence (fence.proxy.tensormap) + cp_fenceproxy + prefetch.
#include <cstdint>

// fence.proxy.tensormap::generic.release/acquire -> UTMACCTL.IV / IVALL
extern "C" __global__ void tmap_fence_release() {
    asm volatile("fence.proxy.tensormap::generic.release.gpu;" ::: "memory");
}
extern "C" __global__ void tmap_fence_acquire(const void* p) {
    asm volatile("fence.proxy.tensormap::generic.acquire.gpu [%0], 128;" :: "l"(p) : "memory");
}
extern "C" __global__ void tmap_fence_acquire_cta(const void* p) {
    asm volatile("fence.proxy.tensormap::generic.acquire.cta [%0], 128;" :: "l"(p) : "memory");
}
extern "C" __global__ void tmap_fence_acquire_sys(const void* p) {
    asm volatile("fence.proxy.tensormap::generic.acquire.sys [%0], 128;" :: "l"(p) : "memory");
}

// tensormap.cp_fenceproxy: fused copy shared->global + release fence
extern "C" __global__ void tmap_cp_fence(void* dst, const void* src) {
    unsigned s = __cvta_generic_to_shared(src);
    asm volatile(
        "tensormap.cp_fenceproxy.global.shared::cta.tensormap::generic.release.gpu.sync.aligned"
        " [%0], [%1], 128;" :: "l"(dst), "r"(s) : "memory");
}

// tensormap prefetch (cp.async.bulk.prefetch.tensor? or prefetch tensormap)
extern "C" __global__ void tmap_prefetch(const void* p) {
    asm volatile("prefetch.tensormap [%0];" :: "l"(p) : "memory");
}
