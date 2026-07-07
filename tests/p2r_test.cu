#include <cstdint>

// pack several comparison predicates into an int -> P2R
__global__ void pack(unsigned *o, int *v){
    int i = threadIdx.x;
    unsigned m = 0;
    m |= (v[i] > 0)  << 0;
    m |= (v[i] > 1)  << 1;
    m |= (v[i] > 2)  << 2;
    m |= (v[i] > 3)  << 3;
    m |= (v[i] > 4)  << 4;
    m |= (v[i] > 5)  << 5;
    m |= (v[i] > 6)  << 6;
    o[i] = m;
}
// unpack an int's bits into predicates used as conditions -> R2P
__global__ void unpack(int *o, unsigned *mask, int *v){
    int i = threadIdx.x;
    unsigned m = mask[0];
    int r = 0;
    if (m & 1) r += v[i];
    if (m & 2) r -= v[i];
    if (m & 4) r *= 2;
    if (m & 8) r ^= 7;
    o[i] = r;
}
// store predicate mask directly
__global__ void tomask(unsigned *o, int *v){
    int i = threadIdx.x;
    bool p0=v[i]>0, p1=v[i]>10, p2=v[i]>20;
    o[i] = (unsigned)p0 | ((unsigned)p1<<8) | ((unsigned)p2<<16);
}
