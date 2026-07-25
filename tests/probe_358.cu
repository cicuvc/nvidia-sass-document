#include <cstdint>
#include <cstdio>
#include <cuda.h>

struct Big{
    uint32_t data[64];
};
__global__ void probe358(const __grid_constant__ Big b, uint32_t* out, int rng) {
    // b.data[0] at 0x380, 
    out[0] = 0x2233;
    out[1] = (uint32_t)(b.data[0]);

    #pragma unroll 0
    for(int i = 0; i < rng; i++){
        printf("%0x: %0x\n", int(0x380 - sizeof(uint32_t) * i), b.data[-i]);
    }
}

int main() {
    setbuf(stdout, NULL);
    CUdevice dev; CUcontext ctx;
    cuInit(0); cuDeviceGet(&dev, 0); cuCtxCreate(&ctx, 0, dev);

    cudaStream_t stream;
    cudaStreamCreate(&stream);
    char* data1; cudaMalloc(&data1, 16*1024*1024);
    cudaStreamAttrValue attr = {};
    attr.accessPolicyWindow.base_ptr = data1;
    attr.accessPolicyWindow.num_bytes = 16384;
    attr.accessPolicyWindow.hitRatio = 0.5f;
    attr.accessPolicyWindow.hitProp = cudaAccessPropertyPersisting;
    attr.accessPolicyWindow.missProp = cudaAccessPropertyStreaming;
    cudaStreamSetAttribute(stream, cudaStreamAttributeAccessPolicyWindow, &attr);

    uint32_t *d, h[2];
    cudaMalloc(&d, 8);

    printf("Default stream\n");
    probe358<<<1,1,0>>>({}, d, 12);
    cudaDeviceSynchronize();

    printf("Modified stream\n");
    probe358<<<1,1,0,stream>>>({}, d, 12);
    cudaDeviceSynchronize();

    cudaFree(data1); cudaFree(d); cudaStreamDestroy(stream);
    cuCtxDestroy(ctx);
}
