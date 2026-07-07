// MEMBAR coverage: membar/fence at various scopes.
#include <cstdint>

extern "C" __global__ void mb_cta()  { asm volatile("membar.cta;" ::: "memory"); }
extern "C" __global__ void mb_gl()   { asm volatile("membar.gl;"  ::: "memory"); }
extern "C" __global__ void mb_sys()  { asm volatile("membar.sys;" ::: "memory"); }
extern "C" __global__ void fence_cta_ar() { asm volatile("fence.acq_rel.cta;" ::: "memory"); }
extern "C" __global__ void fence_gpu_ar() { asm volatile("fence.acq_rel.gpu;" ::: "memory"); }
extern "C" __global__ void fence_sys_ar() { asm volatile("fence.acq_rel.sys;" ::: "memory"); }
extern "C" __global__ void fence_sc_cta() { asm volatile("fence.sc.cta;" ::: "memory"); }
extern "C" __global__ void fence_sc_gpu() { asm volatile("fence.sc.gpu;" ::: "memory"); }
extern "C" __global__ void fence_sc_sys() { asm volatile("fence.sc.sys;" ::: "memory"); }
extern "C" __global__ void fence_cluster() { asm volatile("fence.acq_rel.cluster;" ::: "memory"); }
extern "C" __global__ void fence_proxy_async() { asm volatile("fence.proxy.async;" ::: "memory"); }
