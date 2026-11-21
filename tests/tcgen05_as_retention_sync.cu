// Completion-order audit for AS source erasure: sentinel D, pre-erasure readback, delay controls.
#include <cuda_runtime.h>
#include <cuda_bf16.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <vector>
#define CUDA(x) do{cudaError_t e=(x);if(e!=cudaSuccess){fprintf(stderr,"%s: %s\n",#x,cudaGetErrorString(e));exit(2);}}while(0)
__device__ int offset(int n,int k){return(n/8)*128+(k/8)*64+(n%8)*8+k%8;}
__host__ __device__ float bv(int n,int k){return float(1+(n*7+k*3)%31)/16.f;}
__device__ uint64_t desc(void*p){return(uint64_t(__cvta_generic_to_shared(p))>>4)|(8ull<<16)|(16ull<<32)|(1ull<<46);}
template<bool T,int Op>
__device__ __forceinline__ void mma(uint32_t d,uint32_t a,uint64_t ad,uint64_t bd,uint32_t id){
#define DO(O) if constexpr(T) asm volatile("{.reg .pred p;setp.eq.u32 p,0,1;tcgen05.mma.cta_group::1.kind::f16.collector::a::" O " [%0],[%1],%2,%3,p;}"::"r"(d),"r"(a),"l"(bd),"r"(id):"memory");else asm volatile("{.reg .pred p;setp.eq.u32 p,0,1;tcgen05.mma.cta_group::1.kind::f16.collector::a::" O " [%0],%1,%2,%3,p;}"::"r"(d),"l"(ad),"l"(bd),"r"(id):"memory")
 if constexpr(Op==0){DO("discard");}else if constexpr(Op==1){DO("fill");}else if constexpr(Op==2){DO("use");}else{DO("lastuse");}
#undef DO
}
__device__ void done(uint32_t bar,int phase){
 asm volatile("tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [%0];"::"r"(bar):"memory");
 asm volatile("{.reg .pred p;w: mbarrier.try_wait.parity.shared.b64 p,[%0],%1;@!p bra w;}"::"r"(bar),"r"(phase):"memory");
}
template<bool T,bool Poison,int Reuse>
__global__ void probe(float*out,int audit,unsigned long long delay){
 __shared__ uint32_t base;
 __shared__ __align__(8) uint64_t bar;
 __shared__ __align__(128) __nv_bfloat16 aa[128*16],bb[256*16];
 int tid=threadIdx.x;uint32_t ba=__cvta_generic_to_shared(&bar);
 for(int i=tid;i<128*16;i+=128)aa[offset(i/16,i%16)]=__float2bfloat16((i/16)%16==i%16?1.f:0.f);
 for(int i=tid;i<256*16;i+=128)bb[offset(i/16,i%16)]=__float2bfloat16(bv(i/16,i%16));
 if(tid==0)asm volatile("mbarrier.init.shared.b64 [%0],1;"::"r"(ba):"memory");
 __syncthreads();
 if(tid<32){asm volatile("tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [%0],512;"::"r"(uint32_t(__cvta_generic_to_shared(&base))):"memory");asm volatile("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;":::"memory");}
 __syncthreads();uint32_t d=base,a=base+256;
 // Prevent a stale TMEM allocation from impersonating the first MMA result.
 for(int c=0;c<256;c++)asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0],{%1};"::"r"(d+c),"r"(__float_as_uint(-7.f)):"memory");
 asm volatile("tcgen05.wait::st.sync.aligned;":::"memory");
 if constexpr(T){
  for(int c=0;c<8;c++){uint32_t v=(tid%16==2*c?0x3f80u:0)|(tid%16==2*c+1?0x3f800000u:0);asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0],{%1};"::"r"(a+c),"r"(v):"memory");}
  asm volatile("tcgen05.wait::st.sync.aligned;":::"memory");
 }
 asm volatile("fence.proxy.async.shared::cta;":::"memory");__syncthreads();asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
 uint32_t id=(8u<<24)|(32u<<17)|0x490u;uint64_t ad=desc(aa),bd=desc(bb);
 if(tid==0){mma<T,1>(d,a,ad,bd,id);done(ba,0);}
 __syncthreads();asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
 // This readback is before ANY source erasure, and waits each LDTM result.
 if(audit){
  for(int c=0;c<256;c++){uint32_t v;asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0},[%1];":"=r"(v):"r"(d+c):"memory");asm volatile("tcgen05.wait::ld.sync.aligned;":::"memory");out[32768+tid*256+c]=__uint_as_float(v);}
  __syncthreads();
 }
 // Only issuer delays, but all source writers rendezvous after the delay.
 if(delay){if(tid==0){unsigned long long begin=clock64();while(clock64()-begin<delay)asm volatile("":::"memory");}__syncthreads();}
 if constexpr(Poison){
  if constexpr(T){for(int c=0;c<8;c++)asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0],{%1};"::"r"(a+c),"r"(0):"memory");}
  else{for(int i=tid;i<128*16;i+=128)aa[i]=__float2bfloat16(0.f);}
 }
 if constexpr(T)asm volatile("tcgen05.wait::st.sync.aligned;":::"memory");
 asm volatile("fence.proxy.async.shared::cta;":::"memory");__syncthreads();asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
 if(tid==0){if constexpr(Reuse==2)mma<T,3>(d,a,ad,bd,id);else if constexpr(Reuse==1)mma<T,2>(d,a,ad,bd,id);else mma<T,0>(d,a,ad,bd,id);done(ba,1);}
 __syncthreads();asm volatile("tcgen05.fence::after_thread_sync;":::"memory");
 for(int c=0;c<256;c++){uint32_t v;asm volatile("tcgen05.ld.sync.aligned.32x32b.x1.b32 {%0},[%1];":"=r"(v):"r"(d+c):"memory");asm volatile("tcgen05.wait::ld.sync.aligned;":::"memory");out[tid*256+c]=__uint_as_float(v);}
 __syncthreads();if(tid<32)asm volatile("tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0,512;"::"r"(d):"memory");
}
template<bool T,bool P,int R>void run(float*d,int audit,unsigned long long delay){
 std::vector<float>h(65536);
 for(int rep=0;rep<5;rep++){
  CUDA(cudaMemset(d,0xff,h.size()*4));
  probe<T,P,R><<<1,128>>>(d,audit,delay);CUDA(cudaGetLastError());CUDA(cudaDeviceSynchronize());CUDA(cudaMemcpy(h.data(),d,h.size()*4,cudaMemcpyDeviceToHost));
  int pre_bad=0;if(audit)for(int row=0;row<128;row++)for(int n=0;n<256;n++)pre_bad+=h[32768+row*256+n]!=bv(n,row%16);
  int old=0,zero=0,other=0;for(int row=0;row<128;row++)for(int n=0;n<256;n++){float v=h[row*256+n];if(v==bv(n,row%16))old++;else if(v==0)zero++;else other++;}
  printf("RESULT tmem=%d poison=%d reuse=%d rep=%d audit=%d delay=%llu pre_bad=%d old=%d zero=%d other=%d\n",T,P,R,rep,audit,delay,pre_bad,old,zero,other);fflush(stdout);
  if(pre_bad||(!P&&old!=32768)||(P&&!R&&zero!=32768))exit(3);
 }
}
int main(){float*d;CUDA(cudaMalloc(&d,65536*4));
 for(int audit:{0,1})for(unsigned long long delay:{0ull,100000ull}){
 run<0,0,0>(d,audit,delay);run<0,0,1>(d,audit,delay);run<0,1,0>(d,audit,delay);run<0,1,1>(d,audit,delay);
 run<1,0,0>(d,audit,delay);run<1,0,1>(d,audit,delay);run<1,1,0>(d,audit,delay);run<1,1,1>(d,audit,delay);
 }
 CUDA(cudaFree(d));puts("COMPLETE 160 launches");}
