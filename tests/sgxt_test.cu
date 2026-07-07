#include <cstdint>

__global__ void sc_s32(int *o, int *a, int *b){
    int d; asm("szext.clamp.s32 %0, %1, %2;" : "=r"(d) : "r"(a[0]), "r"(b[0])); o[threadIdx.x]=d;
}
__global__ void sw_s32(int *o, int *a, int *b){
    int d; asm("szext.wrap.s32 %0, %1, %2;" : "=r"(d) : "r"(a[0]), "r"(b[0])); o[threadIdx.x]=d;
}
__global__ void sc_u32(unsigned *o, unsigned *a, unsigned *b){
    unsigned d; asm("szext.clamp.u32 %0, %1, %2;" : "=r"(d) : "r"(a[0]), "r"(b[0])); o[threadIdx.x]=d;
}
__global__ void sw_u32(unsigned *o, unsigned *a, unsigned *b){
    unsigned d; asm("szext.wrap.u32 %0, %1, %2;" : "=r"(d) : "r"(a[0]), "r"(b[0])); o[threadIdx.x]=d;
}
__global__ void sc_imm(int *o, int *a){
    int d; asm("szext.clamp.s32 %0, %1, 13;" : "=r"(d) : "r"(a[0])); o[threadIdx.x]=d;
}
