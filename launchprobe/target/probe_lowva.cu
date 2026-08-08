// probe_lowva.cu — verify the SM's LDC constant path can read a low-VA bank.
// Builds: low-VA bank (mmap+cudaHostRegister) filled with known words at
// +0x380; QMD const-bank descriptors point at it; a probe kernel reads
// c[0x0][0x380..0x398] and stores to a UVM buffer the host reads back.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <dlfcn.h>
#include <unistd.h>
#include <sys/mman.h>
#include <cuda_runtime.h>

typedef void (*mark_fn)(const char *);
static mark_fn get_mark(){ static mark_fn f=(mark_fn)dlsym(RTLD_DEFAULT,"nvtrace_mark"); return f; }
#define MARK(msg) do { mark_fn f=get_mark(); if(f) f(msg); } while(0)

__global__ void warm(){}
struct Big { uint32_t a[64]; };
__global__ void dumpc(__grid_constant__ const Big b, int base_word, int count, uint32_t *out){
    #pragma unroll 1
    for (int i=0;i<count;++i) out[i]=b.a[base_word+i];
}
static void die(const char*w,cudaError_t e){fprintf(stderr,"[probe] %s: %s\n",w,cudaGetErrorString(e));exit(1);}
#define CK(x) do{cudaError_t e_=(x); if(e_) die(#x,e_);}while(0)

int main(){
    MARK("probe start");
    CK(cudaFree(0)); warm<<<1,1>>>(); CK(cudaDeviceSynchronize());
    uint32_t *cdump; CK(cudaMalloc(&cdump,256*4));
    { Big d{}; dumpc<<<1,1>>>(d,(0-0x380)/4,256,cdump); CK(cudaDeviceSynchronize()); }
    uint32_t c0[256]; CK(cudaMemcpy(c0,cdump,sizeof(c0),cudaMemcpyDeviceToHost));
    uint64_t stage_va=(((uint64_t)c0[0x14c/4]<<32)|c0[0x148/4])+0x800;
    uint64_t qmd_sema_va=stage_va+0x400;

    uint8_t *probe_out; CK(cudaMalloc(&probe_out,256));
    CK(cudaMemset(probe_out,0,256));
    uint64_t probe_out_va=(uint64_t)probe_out;

    char cmd[512]; snprintf(cmd,sizeof cmd,"python3 tools/extract_cubin.py target/demo_kernel.cubin demo /tmp/param_read.bin",probe_out_va);
    if(system(cmd)!=0){fprintf(stderr,"gen fail\n");return 1;}
    uint8_t *arena; CK(cudaHostAlloc((void**)&arena,1<<20,cudaHostAllocDefault));
    memset(arena,0,1<<20);
    FILE*f=fopen("/tmp/param_read.bin","rb"); size_t klen=fread(arena+0x1000,1,0x1000,f); fclose(f);
    uint64_t code_va=(uint64_t)arena+0x1000;
    volatile uint32_t *rep_sema=(volatile uint32_t*)(arena+0x2000);
    uint64_t rep_sema_va=(uint64_t)arena+0x2000;

    // low-VA bank (or UVM arena if PB_BANK_UVM set; PB_BANK_VA = explicit VA)
    uint64_t cb_va=0x200000;
    const char *bvenv=getenv("PB_BANK_VA");
    if (bvenv) cb_va=strtoull(bvenv,NULL,0);
    uint8_t *bank=NULL;
    if (getenv("PB_BANK_UVM")) {
        // bank lives in the same UVM arena as code (Phase 10 construct style)
        cb_va=(uint64_t)arena;
        bank=arena;
    } else if (bvenv) {
        // explicit low VA: assume CPU-writable (e.g. pushbuffer nvidiactl map)
        bank=(uint8_t*)(uintptr_t)cb_va;
    } else {
        void*bm=mmap((void*)(uintptr_t)cb_va,0x4000,PROT_READ|PROT_WRITE,
                     MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
        if(bm==MAP_FAILED){perror("mmap");return 1;}
        cb_va=(uint64_t)(uintptr_t)bm;
        CK(cudaHostRegister(bm,0x4000,0));
        bank=(uint8_t*)bm;
    }
    if (bank && !getenv("PB_NO_WRITE")) {
        memset(bank,0,0x4000);
        *(uint32_t*)(bank+0x358)=0;
        *(uint32_t*)(bank+0x37c)=0x00fffdc0u;
        memcpy(bank+0x380,&probe_out_va,8);   // out ptr
        *(uint32_t*)(bank+0x388)=7;           // a
        *(uint32_t*)(bank+0x38c)=9;           // b
        __sync_synchronize();
    }
    fprintf(stderr,"[probe] bank VA=%#lx code=%#lx probe_out=%#lx staging=%#lx\n",cb_va,code_va,probe_out_va,stage_va);

    uint32_t q[96]={};
    q[0x10/4]=0x013f0000;
    uint64_t spacer_va=stage_va+0x1800;
    q[0x30/4]=(uint32_t)(stage_va>>8);
    q[0x3c/4]=(uint32_t)qmd_sema_va;
    q[0x40/4]=2;
    q[0x50/4]=1;
    q[0x80/4]=(uint32_t)(code_va>>4);
    int regcount=16;
    { FILE*mf=fopen("/tmp/param_read.bin.meta","r");
      if(mf){ fscanf(mf,"regcount=%d",&regcount); fclose(mf); } }
    uint32_t alloc84=0x100u+4u*(uint32_t)regcount;
    q[0x84/4]=(alloc84<<16)|(uint32_t)((code_va>>36)&0xffff);
    q[0x88/4]=0x00010001;
    q[0x8c/4]=1|((uint32_t)regcount<<8);
    q[0x9c/4]=1;q[0xa0/4]=1;q[0xa4/4]=1;
    q[0xa8/4]=(uint32_t)(cb_va>>6); q[0xac/4]=0x020001fe;
    q[0xb0/4]=(uint32_t)(cb_va>>6); q[0xb4/4]=0x048001fe;
    q[0xd0/4]=((uint32_t)(cb_va>>6))|0xc; q[0xd4/4]=0x010001fe;
    q[0xe0/4]=(uint32_t)(cb_va>>6); q[0xe4/4]=0x800001fe;
    q[0xe8/4]=1;
    q[0xec/4]=(uint32_t)(code_va>>8);
    q[0xf0/4]=(uint32_t)(code_va>>40);

    uint32_t seg[98+5+4+2]; int n=0;
    seg[n++]=0x206220c6; seg[n++]=0x40000000; seg[n++]=(uint32_t)(stage_va>>8);
    memcpy(&seg[n],q,384); n+=96;
    seg[n++]=0x200426c0; seg[n++]=(uint32_t)(rep_sema_va>>32); seg[n++]=(uint32_t)(rep_sema_va&0xffffffff);
    seg[n++]=0xdead0001; seg[n++]=0x04;
    FILE*sg=fopen("/tmp/probe_lowva_seg.bin","wb"); fwrite(seg,4,n,sg); fclose(sg);

    MARK("injectraw:/tmp/probe_lowva_seg.bin");
    int ok=0;
    for(int i=0;i<2000;i++){ if(*rep_sema==0xdead0001u){ok=1;break;} usleep(1000); }
    fprintf(stderr,"[probe] sema=%#x %s\n",*rep_sema,ok?"SIGNALED":"TIMEOUT");
    uint32_t h[64]={};
    cudaError_t e=cudaMemcpy(h,probe_out,256,cudaMemcpyDeviceToHost);
    fprintf(stderr,"[probe] dump=%s\n",e?cudaGetErrorString(e):"ok");
    for(int i=0;i<8;i++) fprintf(stderr,"  [0x%02x]=%08x\n",0x380+i*4,h[i]);
    int good = ok && h[0]==0x11110000u && h[1]==0x11110001u && h[2]==0x11110002u && h[3]==0x11110003u;
    fprintf(stderr,"[probe] %s\n",good?"SUCCESS":"FAIL");
    return good?0:1;
}
