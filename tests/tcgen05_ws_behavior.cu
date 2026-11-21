// CUDA/PTX-only B200 WS bring-up. No assembler or cubin patching.
#include <cuda_runtime.h>
#include <cuda_bf16.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

#define CUDA(call) do { cudaError_t e=(call); if(e!=cudaSuccess) { \
 fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,cudaGetErrorString(e)); exit(2); } } while(0)

__host__ __device__ float aval(int m,int k,int pattern) {
    if(pattern==0) return k==0 ? float(m+1) : (k==1 ? 1.f : 0.f);
    return float((m*3+k*5)%7-3);
}
__host__ __device__ float bval(int n,int k,int pattern,int b) {
    if(pattern==0) return (k==0 ? 256.f : (k==1 ? float(n+1) : 0.f))*(b+1);
    return float((n*5+k*3)%9-4)*(b+1);
}
// No-swizzle K-major atoms: 8 MN rows x 8 BF16 K elements = 128 B.
__device__ int offset(int mn,int k) { return (mn/8)*128+(k/8)*64+(mn%8)*8+k%8; }
__device__ uint64_t desc(void *p) {
    return (uint64_t(__cvta_generic_to_shared(p))>>4) |
           (8ull<<16) | (16ull<<32) | (1ull<<46);
}

template<int Buffer,int Op>
__device__ __forceinline__ void ws(uint32_t d,uint64_t a,uint64_t b,uint32_t id,int acc) {
#define DO(B,O) asm volatile("{ .reg .pred p; setp.ne.u32 p,%4,0; " \
 "tcgen05.mma.ws.cta_group::1.kind::f16.collector::b" B "::" O " [%0],%1,%2,%3,p; }" \
 ::"r"(d),"l"(a),"l"(b),"r"(id),"r"(acc):"memory")
#define BUF(B) if constexpr(Op==0) { DO(B,"discard"); } \
 else if constexpr(Op==1) { DO(B,"fill"); } \
 else if constexpr(Op==2) { DO(B,"use"); } else { DO(B,"lastuse"); }
    if constexpr(Buffer==0) { BUF("0") }
    else if constexpr(Buffer==1) { BUF("1") }
    else if constexpr(Buffer==2) { BUF("2") }
    else { BUF("3") }
#undef BUF
#undef DO
}
template<int B>
__device__ void sequence(uint32_t d,uint64_t a,uint64_t b,uint32_t id) {
    ws<B,1>(d,a,b,id,0); ws<B,2>(d,a,b,id,1); ws<B,3>(d,a,b,id,1);
}

__global__ void probe(float *out,int m,int n,int pattern,int mode) {
    __shared__ uint32_t base;
    __shared__ __align__(8) uint64_t bar;
    __shared__ __align__(128) __nv_bfloat16 a[128*16];
    __shared__ __align__(128) __nv_bfloat16 b[4][256*16];
    int tid=threadIdx.x, warp=tid/32;
    for(int i=tid;i<128*16;i+=128) a[offset(i/16,i%16)]=__float2bfloat16(aval(i/16,i%16,pattern));
    for(int i=tid;i<4*256*16;i+=128) {
        int bi=i/(256*16),j=i%(256*16);
        b[bi][offset(j/16,j%16)]=__float2bfloat16(bval(j/16,j%16,pattern,bi));
    }
    uint32_t ba=uint32_t(__cvta_generic_to_shared(&bar));
    if(tid==0) asm volatile("mbarrier.init.shared.b64 [%0],1;"::"r"(ba):"memory");
    __syncthreads();
    if(warp==0) {
        asm volatile("tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0],256;"
          ::"r"(uint32_t(__cvta_generic_to_shared(&base))):"memory");
        asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;":::"memory");
    }
    __syncthreads();
    uint32_t d=base;
    // Initialize the entire allocation, including cells outside the output footprint.
    for(int c=0;c<256;c++) {
        asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0],{%1};"
          ::"r"(d+c),"r"(__float_as_uint(7.f)):"memory");
    }
    asm volatile("tcgen05.wait::st.sync.aligned;":::"memory");
    asm volatile("fence.proxy.async.shared::cta;":::"memory");
    __syncthreads();
    asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
    uint32_t id=(1u<<4)|(1u<<7)|(1u<<10)|((n/8)<<17)|((m/16)<<24);
    if(tid==0) {
        uint64_t ad=desc(a),b0=desc(b[0]),b1=desc(b[1]),b2=desc(b[2]),b3=desc(b[3]);
        if(mode==0 || mode==1) ws<0,0>(d,ad,b0,id,mode);
        if(mode==2) { ws<0,0>(d,ad,b0,id,0); ws<0,0>(d,ad,b0,id,1); }
        if(mode==3) sequence<0>(d,ad,b0,id);
        if(mode==4) sequence<1>(d,ad,b1,id);
        if(mode==5) sequence<2>(d,ad,b2,id);
        if(mode==6) sequence<3>(d,ad,b3,id);
        if(mode==7) {
            ws<0,1>(d,ad,b0,id,0); ws<1,1>(d,ad,b1,id,1);
            ws<2,1>(d,ad,b2,id,1); ws<3,1>(d,ad,b3,id,1);
            ws<0,2>(d,ad,b0,id,1); ws<1,2>(d,ad,b1,id,1);
            ws<2,2>(d,ad,b2,id,1); ws<3,2>(d,ad,b3,id,1);
            ws<3,3>(d,ad,b3,id,1); ws<2,3>(d,ad,b2,id,1);
            ws<1,3>(d,ad,b1,id,1); ws<0,3>(d,ad,b0,id,1);
        }
        asm volatile("tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"::"r"(ba):"memory");
        asm volatile("{ .reg .pred p; wait_loop: mbarrier.try_wait.parity.shared.b64 p,[%0],0; @!p bra wait_loop; }"::"r"(ba):"memory");
    }
    __syncthreads();
    asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
    for(int c=0;c<256;c++) {
        uint32_t v;
        asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0},[%1];":"=r"(v):"r"(d+c):"memory");
        asm volatile("tcgen05.wait::ld.sync.aligned;":::"memory");
        out[tid*256+c]=__uint_as_float(v);
    }
    __syncthreads();
    if(warp==0) asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0,256;"::"r"(d):"memory");
}

int main(int argc,char **argv) {
    int reps=argc>1?atoi(argv[1]):3;
    cudaDeviceProp prop; CUDA(cudaGetDeviceProperties(&prop,0));
    printf("DEVICE %s cc=%d.%d reps=%d\n",prop.name,prop.major,prop.minor,reps);
    float *dev; CUDA(cudaMalloc(&dev,128*256*sizeof(float)));
    std::vector<float> h(128*256); int cases=0,failed=0;
    for(int m: {32,64,128}) for(int n: {64,128,256})
    for(int pattern=0;pattern<2;pattern++) for(int mode=0;mode<8;mode++) {
        int errors=0;
        for(int rep=0;rep<reps;rep++) {
            probe<<<1,128>>>(dev,m,n,pattern,mode); CUDA(cudaGetLastError()); CUDA(cudaDeviceSynchronize());
            CUDA(cudaMemcpy(h.data(),dev,h.size()*sizeof(float),cudaMemcpyDeviceToHost));
            int width=n*m/128;
            for(int tid=0;tid<128;tid++) for(int c=0;c<256;c++) {
                int warp=tid/32,lane=tid%32;
                int row= m==128 ? tid : m==64 ? (warp%2)*32+lane : lane;
                int col=c+(m==128?0:m==64?(warp/2)*width:warp*width);
                float expected=7.f;
                if(c<width) {
                    // Reference the actual BF16 inputs, including rounding of 3*(n+1).
                    float dots[4]={};
                    for(int bi=0;bi<4;bi++) for(int k=0;k<16;k++)
                        dots[bi]+=__bfloat162float(__float2bfloat16(aval(row,k,pattern)))
                                 *__bfloat162float(__float2bfloat16(bval(col,k,pattern,bi)));
                    if(mode<2) expected=dots[0]+(mode==1?7.f:0.f);
                    else if(mode==2) expected=2*dots[0];
                    else if(mode<7) expected=3*dots[mode-3];
                    else expected=3*(dots[0]+dots[1]+dots[2]+dots[3]);
                }
                float got=h[tid*256+c];
                if(got!=expected) {
                    if(errors<6) printf("MISMATCH m=%d n=%d p=%d mode=%d rep=%d warp=%d lane=%d c=%d logical=(%d,%d) got=%g expected=%g\n",m,n,pattern,mode,rep,warp,lane,c,row,col,got,expected);
                    errors++;
                }
            }
        }
        printf("CASE m=%d n=%d pattern=%d mode=%d errors=%d %s\n",m,n,pattern,mode,errors,errors?"FAIL":"PASS"); fflush(stdout);
        cases++; failed+=errors!=0;
    }
    CUDA(cudaFree(dev)); printf("SUMMARY cases=%d repetitions=%d failed=%d\n",cases,reps,failed);
    return failed?1:0;
}
