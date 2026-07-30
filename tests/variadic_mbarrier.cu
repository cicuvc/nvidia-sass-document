#include <cstdint>

__global__ void h(int n){
    extern __shared__ int shm[];
    uint32_t base = (uint32_t)(__cvta_generic_to_shared(&shm[0]));

    if(threadIdx.x == 0){
        #pragma unroll 1
        for(int i = 0; i < n; i++){
            asm volatile("mbarrier.init.shared.b64 [%0], 1;\n"::"r"(base + 8 * i):"memory");
        }
    }
}