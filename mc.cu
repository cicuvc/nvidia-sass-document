// nvcc -rdc true mc.cu -o /tmp/mc -gencode arch=compute_120a,code=sm_120a -O3

#include <cstdint>
#include <cstdio>

__device__ void f(){
    // /*0010*/ HFMA2 R0, -RZ, RZ, 0, 7.152557373046875e-07 ;  /* 0x0000000cff007431 */
                                                               /* 0x000fe200000001ff */
    // 7.152557373046875e-07 bitcast to u32 = 0xc = 12
    printf("%d\n", 12);
}

__global__ void vp(void **out){
    void *p = (void*)&f;
    *out = p;
}

__global__ void call(void *fp){
    ((uint64_t*)fp)[2] = 0xff007431 + (114514ull << 32); // patch the operand
    ((void(*)())fp)();
}

__global__ void call2(void *fp){
    ((void(*)())fp)(); // effect lasts
}

int main(){
    uint32_t *vptr;
    cudaMallocManaged(&vptr, 4096);
    vp<<<1,1>>>((void**)vptr);
    cudaDeviceSynchronize();
    call<<<1,1>>>(*(void**)vptr);
    call2<<<1,1>>>(*(void**)vptr);
    cudaDeviceSynchronize();
}