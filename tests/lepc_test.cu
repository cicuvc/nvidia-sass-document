#include <cstdio>
__global__ void k(int *o){
    int t = threadIdx.x;
    printf("val %d %d\n", t, o[t]);
}
__global__ void k2(int *o){
    printf("hello %d\n", o[0]);
    printf("world %d %d\n", o[1], o[2]);
}
