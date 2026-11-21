"""Immutable-A AS reuse across commit boundaries versus scheduled gaps."""
import sys,json,struct,signal,argparse,contextlib,io,re,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from probe_sm100_ws_throughput import source as base, OUT_SIZE
from assembler import assemble_kernel,CudaModule

def source(count, reuse, commit, gap, meter):
    s=base(m=128,n=64,count=count,mode='reuse' if reuse else 'discard',ws=False,lds_iters=2048 if meter else 0)
    # Aggregate count arrivals into one phase. Intermediate commits do not wait
    # or recycle an incomplete barrier; final phase completion covers them all.
    if commit:s=s.replace('#!mbarrier_init(UR18, 1)',f'#!mbarrier_init(UR18, {count})')
    lines=s.splitlines();out=[];seen=0
    for l in lines:
        if l.startswith('UTCHMMA.'):
            seen+=1
            # Keep the final reuse too; the query is use, not lastuse.
            if reuse and '.A_REUSE' in l and '.A_KEEP' not in l:l=l.replace('.A_REUSE','.A_REUSE.A_KEEP')
            out.append(l)
            if seen<count:
                if commit:out.append('UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]')
                out += ['NOP;[7:7:{}:8:1]']*gap
        else:out.append(l)
    assert seen==count
    return '\n'.join(out)+'\n'

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-only',action='store_true');args=p.parse_args()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    for commit,gap in ((False,0),(True,0),(False,32),(True,32)):
     for meter in (False,True):
      for reuse in (False,True):
       for count in (64,256):
        cfg=dict(count=count,reuse=reuse,commit=commit,gap=gap,meter=meter)
        src=source(**cfg);diag=io.StringIO()
        with contextlib.redirect_stderr(diag):a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
        if set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}:raise RuntimeError(diag.getvalue())
        if args.build_only:continue
        print(json.dumps(dict(event='launch',**cfg)),flush=True)
        mod=CudaModule(a.code);size=OUT_SIZE+128;ptr=mod.devmem_alloc(size);samples=[];ms=[]
        for rep in range(6):
            mod.devmem_set(ptr,0,size//4);signal.alarm(30)
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=[ptr]);mod.synchronize();raw=mod.device_read(ptr,size);signal.alarm(0)
            vals=struct.unpack_from('<32768f',raw,64)
            assert all(v==(16.*count if i%256<64 else 0.) for i,v in enumerate(vals)),cfg
            start,end=struct.unpack_from('<QQ',raw);assert end>start
            if meter:
                times=[struct.unpack_from('<QQ',raw,16*w) for w in (1,2,3)]
                checks=[struct.unpack_from('<II',raw,OUT_SIZE+8*w) for w in (1,2,3)]
                assert all(c==((2048*12*0x3f803f80)&0xffffffff,(48*0x3f803f80)&0xffffffff) for c in checks)
                if rep:ms.append(dict(begin=[t[0] for t in times],end=[t[1] for t in times],span=max(t[1] for t in times)-min(t[0] for t in times),mma_begin=start,mma_end=end))
            if rep:samples.append(end-start)
        mod.devmem_free(ptr)
        print(json.dumps(dict(event='result',**cfg,cycles=samples,median=statistics.median(samples),lds=ms,errors=0)),flush=True)
    print(json.dumps(dict(event='complete',cases=32,reps=5)),flush=True)
if __name__=='__main__':main()
