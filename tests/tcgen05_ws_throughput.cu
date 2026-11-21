// CUDA/PTX-only WS throughput and shared-read contention; no SASS patches.
#include <cuda_runtime.h>
#include <cuda_bf16.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

#define CUDA(call) do { cudaError_t e=(call); if(e!=cudaSuccess) { \
 fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,cudaGetErrorString(e)); exit(2); } } while(0)

#include <algorithm>
#ifdef WS_EXPLICIT_ELECT
#define ELECT_PTX "elect.sync _|leader, 0xffffffff; @leader "
#else
#define ELECT_PTX ""
#endif

template<int Buffer,int Op>
__device__ __forceinline__ void ws(uint32_t d,uint64_t a,uint64_t b,uint32_t id,int acc) {
#define DO(B,O) asm volatile("{ .reg .pred p,leader; setp.ne.u32 p,%4,0; " ELECT_PTX \
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

struct Result {
    unsigned long long begin[5], end[5];
    unsigned errors[4], sink[4];
};

__device__ uint64_t descriptor(void *p) {
    return (uint64_t(__cvta_generic_to_shared(p))>>4) |
           (8ull<<16) | (16ull<<32) | (1ull<<46);
}

// Modes: discard, refill, reuse b0, discard rotating b0..3, reuse rotating b0..3.
// Stage 0/1/2 = first four, middle, last four instructions. All modes issue
// exactly 'ops' MMAs and accumulate from explicitly initialized zero.
template<int Mode,int Stage,int J>
__device__ __forceinline__ void issue(uint32_t d,uint64_t a,const uint64_t *b,uint32_t id) {
    constexpr int buffer=Mode>=3 ? J%4 : 0;
    constexpr int op=Mode==1 ? 1 : (Mode==0 || Mode==3) ? 0 :
        Stage==0 && (Mode==4 || J==0) ? 1 :
        Stage==2 && (Mode==4 || J==3) ? 3 : 2;
    ws<buffer,op>(d,a,b[buffer],id,1);
}

template<int Mode,int Unroll>
__global__ void bench(Result *out,int m,int n,int ops,int lds_iters) {
    __shared__ uint32_t base;
    __shared__ __align__(8) uint64_t bar;
    __shared__ __align__(128) uint16_t a[128*16];
    __shared__ __align__(128) uint16_t b[4][256*16];
    __shared__ __align__(128) uint32_t scratch[1024];
    int tid=threadIdx.x, warp=tid/32, lane=tid%32;
    for(int i=tid;i<128*16;i+=blockDim.x) a[i]=0x3f80;
    for(int i=tid;i<4*256*16;i+=blockDim.x) {
        const uint16_t bits[4]={0x3f80,0x4000,0x4040,0x4080};
        b[i/(256*16)][i%(256*16)]=bits[i/(256*16)];
    }
    for(int i=tid;i<1024;i+=blockDim.x) scratch[i]=1;
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
    int width=m*n/128;
    if(warp<4) {
        for(int c=0;c<width;c++) asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0],{%1};"
            ::"r"(d+c),"r"(0):"memory");
        asm volatile("tcgen05.wait::st.sync.aligned;":::"memory");
    }
    asm volatile("fence.proxy.async.shared::cta;":::"memory");
    __syncthreads();
    asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
    uint64_t ad=descriptor(a),bd[4]={descriptor(b[0]),descriptor(b[1]),descriptor(b[2]),descriptor(b[3])};
    uint32_t id=(1u<<4)|(1u<<7)|(1u<<10)|((n/8)<<17)|((m/16)<<24);
    uint32_t sa=uint32_t(__cvta_generic_to_shared(scratch))+lane*16;
    // Equal launch/synchronization for MMA-only, LDS-only, and combined.
    __syncthreads();
#ifdef WS_EXPLICIT_ELECT
    if(warp==0 && ops) {
#else
    if(tid==0 && ops) {
#endif
        unsigned long long start=clock64();
        issue<Mode,0,0>(d,ad,bd,id); issue<Mode,0,1>(d,ad,bd,id);
        issue<Mode,0,2>(d,ad,bd,id); issue<Mode,0,3>(d,ad,bd,id);
        int remaining=ops-8;
        // Dynamic count prevents ptxas replacing the long stream with a fixed body.
        for(int i=0;i<remaining/Unroll;i++) {
#define ONE(J) issue<Mode,1,J>(d,ad,bd,id)
            ONE(0); ONE(1); ONE(2); ONE(3);
            if constexpr(Unroll>=8) { ONE(4); ONE(5); ONE(6); ONE(7); }
            if constexpr(Unroll>=16) { ONE(8); ONE(9); ONE(10); ONE(11); ONE(12); ONE(13); ONE(14); ONE(15); }
            if constexpr(Unroll>=32) {
                ONE(16); ONE(17); ONE(18); ONE(19); ONE(20); ONE(21); ONE(22); ONE(23);
                ONE(24); ONE(25); ONE(26); ONE(27); ONE(28); ONE(29); ONE(30); ONE(31);
            }
#undef ONE
        }
        // A multiple-of-four tail preserves the four-buffer rotation.
        for(int i=0;i<(remaining%Unroll)/4;i++) {
            issue<Mode,1,0>(d,ad,bd,id); issue<Mode,1,1>(d,ad,bd,id);
            issue<Mode,1,2>(d,ad,bd,id); issue<Mode,1,3>(d,ad,bd,id);
        }
        issue<Mode,2,0>(d,ad,bd,id); issue<Mode,2,1>(d,ad,bd,id);
        issue<Mode,2,2>(d,ad,bd,id); issue<Mode,2,3>(d,ad,bd,id);
        if(lane==0) {
        asm volatile("tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"::"r"(ba):"memory");
        asm volatile("{ .reg .pred p; wait_loop: mbarrier.try_wait.parity.shared.b64 p,[%0],0; @!p bra wait_loop; }"::"r"(ba):"memory");
        unsigned long long end=clock64();
        out->begin[0]=start; out->end[0]=end;
        }
    }
    if(warp>=1 && warp<=4 && lds_iters) {
        unsigned sink=0;
        unsigned long long start=clock64();
        for(int i=0;i<lds_iters;i++) {
            unsigned x[4][4];
#pragma unroll
            for(int j=0;j<4;j++) {
                uint32_t addr=sa+j*512+(i&1)*2048;
                // PTX volatile + changing address prohibits invariant-load hoisting.
                asm volatile("ld.volatile.shared.v4.u32 {%0,%1,%2,%3},[%4];"
                  :"=r"(x[j][0]),"=r"(x[j][1]),"=r"(x[j][2]),"=r"(x[j][3]):"r"(addr):"memory");
            }
#pragma unroll
            for(int j=0;j<4;j++) {
                sink+=x[j][0]+x[j][1]+x[j][2]+x[j][3];
            }
        }
        // Data dependency forces all four vector loads to complete before timer.
        asm volatile("{ .reg .pred p; setp.eq.u32 p,%0,0xffffffff; @p trap; }"::"r"(sink):"memory");
        unsigned long long end=clock64();
        if(lane==0) { out->begin[warp]=start; out->end[warp]=end; out->sink[warp-1]=sink; }
    }
    __syncthreads();
    asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
    if(warp<4) {
        unsigned errors=0;
        float expected=ops*(Mode>=3?40.f:16.f);
        for(int c=0;c<width;c++) {
            uint32_t v;
            asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0},[%1];":"=r"(v):"r"(d+c):"memory");
            asm volatile("tcgen05.wait::ld.sync.aligned;":::"memory");
            errors+=(__uint_as_float(v)!=expected);
        }
        for(int shift=16;shift;shift/=2) errors+=__shfl_down_sync(0xffffffff,errors,shift);
        if(lane==0) out->errors[warp]=errors;
    }
    __syncthreads();
    if(warp==0) asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0,256;"::"r"(d):"memory");
}

using Kernel=void(*)(Result*,int,int,int,int);
template<int U> Kernel select(int mode) {
    switch(mode) {
    case 0:return bench<0,U>; case 1:return bench<1,U>; case 2:return bench<2,U>;
    case 3:return bench<3,U>; default:return bench<4,U>;
    }
}
int main(int argc,char **argv) {
    int reps=argc>1?atoi(argv[1]):5;
    if(reps<1) return 2;
    cudaDeviceProp prop; CUDA(cudaGetDeviceProperties(&prop,0));
    printf("DEVICE %s cc=%d.%d reps=%d\n",prop.name,prop.major,prop.minor,reps);
    Result *dev; CUDA(cudaMalloc(&dev,sizeof(Result)));
    int failed=0, launches=0;
    auto run=[&](int m,int n,int mode,int u,int ops,int lds) {
        Kernel k=u==4?select<4>(mode):u==16?select<16>(mode):u==32?select<32>(mode):select<8>(mode);
        for(int rep=-1;rep<reps;rep++) {
            CUDA(cudaMemset(dev,0,sizeof(Result)));
            k<<<1,160>>>(dev,m,n,ops,lds); CUDA(cudaGetLastError()); CUDA(cudaDeviceSynchronize());
            Result h; CUDA(cudaMemcpy(&h,dev,sizeof(h),cudaMemcpyDeviceToHost));
            unsigned errors=0; for(int i=0;i<4;i++) errors+=h.errors[i];
            if(lds) for(int i=0;i<4;i++) errors+=(h.sink[i]!=unsigned(lds*16));
            failed+=errors!=0; launches++;
            if(rep<0 && !errors) continue;
            unsigned long long lo=~0ull,hi=0;
            if(lds) for(int i=1;i<5;i++) {lo=std::min(lo,h.begin[i]);hi=std::max(hi,h.end[i]);}
            printf("SAMPLE m=%d n=%d mode=%d unroll=%d ops=%d lds=%d rep=%d mma=%llu lds_span=%llu errors=%u",
                m,n,mode,u,ops,lds,rep,h.end[0]-h.begin[0],lds?hi-lo:0,errors);
            for(int i=0;i<5;i++) printf(" t%d=%llu:%llu",i,h.begin[i],h.end[i]);
            printf("\n");
        }
        fflush(stdout);
    };
    for(int m:{32,64,128}) for(int n:{64,128,256})
        for(int mode=0;mode<5;mode++) for(int ops:{256,1024,4096}) run(m,n,mode,8,ops,0);
    // Loop overhead controls at representative shapes; no change to MMA count.
    for(int m:{32,64,128}) for(int mode:{0,2}) for(int u:{4,16,32}) run(m,128,mode,u,4096,0);
    // Four shared-read contender warps cover all four subcores.
    for(int m:{32,64,128}) for(int n:{64,128,256}) {
        run(m,n,0,8,0,2048);
        for(int mode:{0,1,2,3,4}) run(m,n,mode,8,1024,2048);
    }
    CUDA(cudaFree(dev)); printf("SUMMARY launches=%d failed=%d\n",launches,failed);
    return failed?1:0;
}
