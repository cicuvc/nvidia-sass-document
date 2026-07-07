// UTMAPF coverage: cp.async.bulk.prefetch.tensor (global -> L2), dims + im2col.
#include <cstdint>
struct TMap { char x[128]; };

extern "C" __global__ void pf1d(const __grid_constant__ TMap tm, int c0) {
    const void* t = &tm;
    asm volatile("cp.async.bulk.prefetch.tensor.1d.L2.global.tile [%0, {%1}];"
        :: "l"(t), "r"(c0) : "memory");
}
extern "C" __global__ void pf2d(const __grid_constant__ TMap tm, int c0, int c1) {
    const void* t = &tm;
    asm volatile("cp.async.bulk.prefetch.tensor.2d.L2.global.tile [%0, {%1,%2}];"
        :: "l"(t), "r"(c0), "r"(c1) : "memory");
}
extern "C" __global__ void pf3d(const __grid_constant__ TMap tm, int c0, int c1, int c2) {
    const void* t = &tm;
    asm volatile("cp.async.bulk.prefetch.tensor.3d.L2.global.tile [%0, {%1,%2,%3}];"
        :: "l"(t), "r"(c0), "r"(c1), "r"(c2) : "memory");
}
extern "C" __global__ void pf4d(const __grid_constant__ TMap tm, int c0, int c1, int c2, int c3) {
    const void* t = &tm;
    asm volatile("cp.async.bulk.prefetch.tensor.4d.L2.global.tile [%0, {%1,%2,%3,%4}];"
        :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(c3) : "memory");
}
extern "C" __global__ void pf5d(const __grid_constant__ TMap tm, int c0, int c1, int c2, int c3, int c4) {
    const void* t = &tm;
    asm volatile("cp.async.bulk.prefetch.tensor.5d.L2.global.tile [%0, {%1,%2,%3,%4,%5}];"
        :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "r"(c3), "r"(c4) : "memory");
}
// im2col prefetch (3d): coords + im2col offsets
extern "C" __global__ void pf3d_im2col(const __grid_constant__ TMap tm, int c0, int c1, int c2, short o0) {
    const void* t = &tm;
    asm volatile("cp.async.bulk.prefetch.tensor.3d.L2.global.im2col [%0, {%1,%2,%3}], {%4};"
        :: "l"(t), "r"(c0), "r"(c1), "r"(c2), "h"(o0) : "memory");
}
