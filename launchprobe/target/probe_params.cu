// probe_params.cu — driver-launch a kernel that reads c[0x0][0x380..0x3a0]
// (the param area) and dumps raw words to a UVM buffer, so we can see exactly
// what the SM's constant path returns for the current launch's params.
#include <cstdio>
#include <cstdint>
#include <cuda_runtime.h>

struct Big { uint32_t a[64]; };
__global__ void dumpc(__grid_constant__ const Big b, int base_word, int count, uint32_t *out)
{
    #pragma unroll 1
    for (int i = 0; i < count; ++i)
        out[i] = b.a[base_word + i];
}

// reference kernel: also do the real work
__global__ void probe(int tag, int a, int b, int *out)
{
    out[threadIdx.x] = a * b + tag + threadIdx.x;
}

int main(int argc, char **argv)
{
    int N = argc > 1 ? atoi(argv[1]) : 2;
    cudaFree(0);
    probe<<<1,4>>>(0,1,1,(int*)0);
    cudaDeviceSynchronize();

    int *dout; cudaMalloc(&dout, N*64);
    uint32_t *cdump; cudaMalloc(&cdump, N*256);
    cudaMemset(cdump, 0, N*256);
    cudaMemset(dout, 0, N*64);

    for (int i = 0; i < N; i++) {
        probe<<<1,4>>>(i, i+1, i+2, dout + i*16);
        // dump c[0x0][0x380..0x3a0] right after each launch (same stream -> ordered)
        { Big d{}; dumpc<<<1,1>>>(d, (0x380-0x380)/4, 8, cdump + i*8); }
    }
    cudaError_t e = cudaDeviceSynchronize();
    printf("sync: %s\n", cudaGetErrorString(e));

    int h[256]={}; cudaMemcpy(h, dout, N*16, cudaMemcpyDeviceToHost);
    uint32_t ch[256]={}; cudaMemcpy(ch, cdump, N*32, cudaMemcpyDeviceToHost);
    for (int i = 0; i < N; i++) {
        printf("launch %d: out=%d %d %d %d  | c[0x0][0x380..] =", i, h[i*4],h[i*4+1],h[i*4+2],h[i*4+3]);
        for (int k=0;k<8;k++) printf(" %08x", ch[i*8+k]);
        printf("\n");
    }
    return 0;
}
