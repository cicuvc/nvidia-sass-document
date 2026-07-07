#include <cstdint>

__global__ void clo(unsigned long long *o, unsigned long long *a, unsigned long long *b, unsigned long long *c){
    unsigned long long d;
    asm volatile("clmad.lo.u64 %0, %1, %2, %3;" : "=l"(d) : "l"(a[0]), "l"(b[0]), "l"(c[0]));
    o[0] = d;
}
__global__ void chi(unsigned long long *o, unsigned long long *a, unsigned long long *b, unsigned long long *c){
    unsigned long long d;
    asm volatile("clmad.hi.u64 %0, %1, %2, %3;" : "=l"(d) : "l"(a[0]), "l"(b[0]), "l"(c[0]));
    o[0] = d;
}
// force a constant-bank / uniform operand (kernel params are often uniform)
__global__ void clo_param(unsigned long long *o, unsigned long long a, unsigned long long b, unsigned long long c){
    unsigned long long d;
    asm volatile("clmad.lo.u64 %0, %1, %2, %3;" : "=l"(d) : "l"(a), "l"(b), "l"(c));
    o[0] = d;
}
