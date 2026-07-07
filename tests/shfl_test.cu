#include <cstdint>

__global__ void idx_i(int *o, int *v){        // IDX, imm lane
    int lane = threadIdx.x & 31;
    o[lane] = __shfl_sync(0xffffffff, v[lane], 3);
}
__global__ void idx_r(int *o, int *v, int s){  // IDX, reg lane
    int lane = threadIdx.x & 31;
    o[lane] = __shfl_sync(0xffffffff, v[lane], s);
}
__global__ void up_i(int *o, int *v){          // UP, imm delta
    int lane = threadIdx.x & 31;
    o[lane] = __shfl_up_sync(0xffffffff, v[lane], 1);
}
__global__ void down_i(int *o, int *v){        // DOWN, imm delta
    int lane = threadIdx.x & 31;
    o[lane] = __shfl_down_sync(0xffffffff, v[lane], 2);
}
__global__ void bfly_i(int *o, int *v){        // BFLY (xor), imm mask
    int lane = threadIdx.x & 31;
    o[lane] = __shfl_xor_sync(0xffffffff, v[lane], 16);
}
__global__ void idx_i_w8(int *o, int *v){      // IDX, imm lane, width=8 (segmask)
    int lane = threadIdx.x & 31;
    o[lane] = __shfl_sync(0xffffffff, v[lane], 3, 8);
}
__global__ void down_r(int *o, int *v, int d){ // DOWN, reg delta
    int lane = threadIdx.x & 31;
    o[lane] = __shfl_down_sync(0xffffffff, v[lane], d);
}
