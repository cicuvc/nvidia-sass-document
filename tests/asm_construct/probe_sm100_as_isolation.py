"""Immutable-A AS reuse across commit boundaries versus scheduled gaps."""
import sys,json,struct,signal,argparse,contextlib,io,re,statistics,ctypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from probe_sm100_as_commit import source as commit_source
from probe_sm100_ws_throughput import OUT_SIZE
from assembler.runner import _cuda,_check
from assembler import assemble_kernel,CudaModule

def source(count,reuse,gap,meter,isolated):
    s=commit_source(count,reuse,False,gap,meter)
    return s

def attributes(mod,isolated):
    lib=_cuda();f=mod.func('ws_throughput')
    def da(k):
        v=ctypes.c_int();_check(lib.cuDeviceGetAttribute(ctypes.byref(v),k,mod._dev));return v.value
    def fa(k):
        v=ctypes.c_int();_check(lib.cuFuncGetAttribute(ctypes.byref(v),k,f));return v.value
    attrs={str(k):da(k) for k in (16,81,82,97,111)}
    static=fa(1);regs=fa(4);dynamic=attrs['97']-static if isolated else 0
    if isolated:
        _check(lib.cuFuncSetAttribute(f,8,dynamic));_check(lib.cuFuncSetAttribute(f,9,100))
        assert regs==112
        assert static+dynamic+attrs['111']==attrs['81'],attrs
    block=128
    occ=ctypes.c_int();_check(lib.cuOccupancyMaxActiveBlocksPerMultiprocessor(ctypes.byref(occ),f,block,ctypes.c_size_t(dynamic)))
    if isolated:assert occ.value==1
    return dynamic,dict(device_attributes=attrs,static_shared=static,dynamic_shared=dynamic,registers_per_thread=regs,block=block,active_blocks_per_sm=occ.value)

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-only',action='store_true');args=p.parse_args()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    for isolated,gap in ((True,0),(False,0),(True,32),(False,32)):
     for meter in (False,True):
      for reuse in (False,True):
       for count in (64,256):
        cfg=dict(count=count,reuse=reuse,isolated=isolated,gap=gap,meter=meter)
        src=source(**cfg);diag=io.StringIO()
        with contextlib.redirect_stderr(diag):a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
        if set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}:raise RuntimeError(diag.getvalue())
        if args.build_only:continue
        print(json.dumps(dict(event='launch',**cfg)),flush=True)
        mod=CudaModule(a.code);dynamic,resources=attributes(mod,isolated);print(json.dumps(dict(event='resources',**cfg,**resources)),flush=True);size=OUT_SIZE+128;ptr=mod.devmem_alloc(size);samples=[];ms=[]
        for rep in range(6):
            mod.devmem_set(ptr,0,size//4);signal.alarm(30)
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=[ptr],shared_mem=dynamic);mod.synchronize();raw=mod.device_read(ptr,size);signal.alarm(0)
            vals=struct.unpack_from('<32768f',raw,64)
            bad=[(i//256,i%256,v) for i,v in enumerate(vals) if v!=(16.*count if i%256<64 else 0.)]
            assert not bad,(cfg,len(bad),bad[:12])
            start,end=struct.unpack_from('<QQ',raw);assert end>start
            if meter:
                times=[struct.unpack_from('<QQ',raw,16*w) for w in (1,2,3)]
                checks=[struct.unpack_from('<II',raw,OUT_SIZE+8*w) for w in (1,2,3)]
                assert all(c==((2048*12*0x3f803f80)&0xffffffff,(48*0x3f803f80)&0xffffffff) for c in checks)
                if rep:ms.append(dict(begin=[t[0] for t in times],end=[t[1] for t in times],span=max(t[1] for t in times)-min(t[0] for t in times),mma_begin=start,mma_end=end))
            if rep:samples.append(end-start)
        mod.devmem_free(ptr)
        print(json.dumps(dict(event='result',**cfg,resources=resources,cycles=samples,median=statistics.median(samples),lds=ms,errors=0)),flush=True)
    print(json.dumps(dict(event='complete',cases=32,reps=5)),flush=True)
if __name__=='__main__':main()
