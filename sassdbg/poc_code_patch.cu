// sassdbg M3 proof-of-concept: device-side patching of SASS code memory.
//
// Demonstrates the three findings the runtime-breakpoint design rests on:
//   1. a __device__ function's SASS lives in writable device memory — its
//      address is obtainable via &f (needs -rdc) and a plain 128-bit store
//      to that VA changes the instruction;
//   2. the SM icache is NOT coherent with such stores: a re-executed kernel
//      keeps running the stale line unless the patcher executes
//      CCTL.I.IVALL (icache invalidate-all) after the store;
//   3. the patch persists across kernel launches (call2 sees it).
//
// Build & run:
//   nvcc -rdc true sassdbg/poc_code_patch.cu -o /tmp/poc_code_patch \
//        -gencode arch=compute_120a,code=sm_120a -O3 && /tmp/poc_code_patch
// Expected output: "114514" twice — the first kernel patches the immediate
// to 114514 *before* calling f (so the original "12" never prints), and the
// second kernel proves the patch persists across launches.

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