"""AS reuse eligibility versus NOP delay/yield and instruction identity."""
import sys,json,struct,signal,argparse,contextlib,io,re,statistics,itertools
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from probe_sm100_ws_throughput import source as base,OUT_SIZE
from probe_sm100_as_isolation import attributes
from assembler import assemble_kernel,CudaModule

def source(count,reuse,meter,nops,stall=8,nop_yield=1,mma_yield=1,filler='NOP'):
    s=base(m=128,n=64,count=count,mode='reuse' if reuse else 'discard',ws=False,lds_iters=2048 if meter else 0)
    out=[];seen=0
    for l in s.splitlines():
        if l.startswith('UTCHMMA.'):
            seen+=1
            if reuse and '.A_REUSE' in l and '.A_KEEP' not in l:l=l.replace('.A_REUSE','.A_REUSE.A_KEEP')
            l=l.replace('[7:0:{}:1:1]',f'[7:0:{{}}:1:{mma_yield}]')
            out.append(l)
            if seen<count:
                op='NOP' if filler=='NOP' else 'MOV R110, RZ'
                out += [f'{op};[7:7:{{}}:{stall}:{nop_yield}]']*nops
        else:out.append(l)
    assert seen==count
    return '\n'.join(out)+'\n'

def points_for(suite):
    if suite=='spacing':
        return [dict(nops=n,stall=st,nop_yield=y) for n,st in ((8,8),(16,4),(32,2),(64,1)) for y in (0,1)]
    if suite=='followup':
        return points_for('fine')+points_for('controls')
    if suite=='coarse':
        points=[dict(nops=0)]+[dict(nops=n,nop_yield=y) for n in (1,2,4,8,16,32) for y in (0,1)]
    elif suite=='fine':
        points=[dict(nops=n,nop_yield=y) for n in range(3,17) if n not in (4,8,16) for y in (0,1)]
    else:
        points=[dict(nops=n,nop_yield=y,mma_yield=0) for n in (0,8,16,32) for y in (0,1) if n or y==1]
        points += [dict(nops=n,nop_yield=y,filler='MOV') for n in (1,4,8,16,32) for y in (0,1)]
        points += [dict(nops=n,stall=st,nop_yield=y) for n,st in ((16,4),(32,2),(64,1)) for y in (0,1)]
    return points

def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=['coarse','fine','controls','followup','spacing'],default='coarse');p.add_argument('--build-only',action='store_true');args=p.parse_args()
    points=points_for(args.suite)
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    index=0
    for pt in points:
      for meter,reuse,count in itertools.product((False,True),(False,True),(64,256)):
        cfg=dict(count=count,reuse=reuse,meter=meter,nops=pt['nops'],stall=pt.get('stall',8),nop_yield=pt.get('nop_yield',1),mma_yield=pt.get('mma_yield',1),filler=pt.get('filler','NOP'))
        src=source(**cfg);diag=io.StringIO()
        with contextlib.redirect_stderr(diag):a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
        if set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}:raise RuntimeError(diag.getvalue())
        index+=1
        if args.build_only:continue
        print(json.dumps(dict(event='launch',index=index,**cfg)),flush=True)
        mod=CudaModule(a.code);dynamic,resources=attributes(mod,True);size=OUT_SIZE+128;ptr=mod.devmem_alloc(size);samples=[];ms=[]
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
    print(json.dumps(dict(event='complete',suite=args.suite,cases=index,reps=5)),flush=True)
if __name__=='__main__':main()
