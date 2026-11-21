"""WS final input-version masks across physical regions; no in-flight LDTM.

One STS.128 updates K8 x N8 in each distinct logical N band. For M32/64
these are distinct shared addresses, so lane-order controls are essential.
"""
import argparse,base64,contextlib,functools,io,itertools,json,re,signal,struct,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel,CudaModule
from probe_sm100_as_b_fetch import source as base,b_offset,FINE_PADS
from probe_sm100_ws_throughput import OUT_SIZE
SIZE=OUT_SIZE+544

def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def source(m,k,ordering='race'):
    assert m in (32,64,128) and k in (0,8)
    s=base(512,0,0,ordering,fine=True)
    s=once(s,'lane_xor<4>)','lane_xor<4>, nbase<4>)')
    s=once(s,'UTCHMMA.1CTA tmem[UR12]','UTCHMMA.1CTA.WS tmem[UR12]')
    old=(8<<24)|(32<<17)|0x490
    new=((m//16)<<24)|(32<<17)|0x490
    s=once(s,f'UMOV UR15, {old:#x};',f'UMOV UR15, {new:#x};')
    a='SHL R36, R35, 4;[7:7:{}:5:1]\nIADD3 R36, R36, 0x2000, RZ;[7:7:{}:5:1]'
    b=['LDC R64, #param(nbase);[2:7:{}:1:0]',
       'SHR R65, R35, 3;[7:7:{}:5:1]',
       'LOP3.LUT R36, R35, 7, RZ, 0xc0, !PT;[7:7:{}:5:1]',
       'SHL R36, R36, 4;[7:7:{}:5:1]',
       f'IMAD R36, R65, {64*m:#x}, R36;[7:7:{{}}:5:1]',
       'IMAD R36, R64, 32, R36;[7:7:{2}:5:1]',
       f'IADD3 R36, R36, {0x2000+16*k:#x}, RZ;[7:7:{{}}:5:1]']
    s=once(s,a,'\n'.join(b))
    a='ISETP.NE.AND P2, PT, R61, RZ, PT;[7:7:{2}:13:1]'
    s=once(s,a,a+f'\nISETP.LT.AND P2, PT, R35, {1024//m}, P2;[7:7:{{}}:13:1]')
    # Record exact runtime parameters after the writer interval.
    a='#def_label(b_verified)'
    echo=['ISETP.EQ.AND P1, PT, R4, 32, PT;[7:7:{}:13:1]']
    for i,r in enumerate(range(60,65)):
        echo.append(f'@P1 STG.E.STRONG.GPU [{{R2,R3}}+{OUT_SIZE+512+4*i:#x}], R{r};[7:1:{{1}}:8:1]')
    echo.append('NOP;[7:7:{1}:8:1]')
    return once(s,a,a+'\n'+'\n'.join(echo))

def configurations(suite):
    jobs=[]
    for mode in ('none','early','late','race'):
        if suite=='smoke' and mode=='race':continue
        for m in (32,64,128):
            blocks=range(0,2*m,8) if suite=='scan' else (0,) if suite=='repeat' else (0, m, 2*m-8)
            for k,n,lx in itertools.product((0,8),blocks,(0,31)):
                delays=((-64,) if suite=='repeat' else (-128,-64,0,64)) if mode=='race' else ({'none':0,'early':-512,'late':1024}[mode],)
                for d,pad in itertools.product(delays,FINE_PADS if mode=='race' else (0,)):
                    jobs.append(dict(m=m,k=k,nbase=n,lane_xor=lx,mode=mode,delta=d,pad=pad,enabled=int(mode!='none')))
    return jobs

@functools.lru_cache(None)
def layout(m,k,n):
    targets=[]; outside=[]; zero=[]
    for w in range(4):
        for lane in range(32):
            for c in range(256):
                i=(w*32+lane)*256+c
                if c>=2*m:zero.append(i)
                elif n<=c<n+8 and k<=lane%16<k+8:targets.append(i)
                else:outside.append(i)
    return targets,outside,zero

def inspect(raw,cfg):
    m,k,n=cfg['m'],cfg['k'],cfg['nbase'];mode=cfg['mode']
    pre,admit,done,ms,me=struct.unpack_from('<5Q',raw)
    assert pre<admit<done and ms<me
    epoch,delay,target,observed,diff=struct.unpack_from('<5I',raw,40)
    assert target==(epoch+512+delay)&0xffffffff and diff==(observed-target)&0xffffffff and diff<0x80000000
    assert 0<((ms-epoch)&0xffffffff)<1000000
    echo=struct.unpack_from('<5I',raw,OUT_SIZE+512)
    assert echo==tuple(cfg[x]&0xffffffff for x in ('delta','enabled','pad','lane_xor','nbase')),(echo,cfg)
    vs=struct.unpack_from('<32768f',raw,64)
    shared=struct.unpack_from('<256H',raw,OUT_SIZE)
    assert all(x==(0x4000 if cfg['enabled'] else 0x3f80) for x in shared[:(1024//m)*8])
    targets,outside,zero=layout(m,k,n)
    assert all(vs[i]==0 for i in zero),'outside footprint'
    assert all(vs[i]==1 for i in outside),'outside patch'
    assert all(vs[i] in (1,2) for i in targets),'unexpected value'
    if mode!='race':assert all(vs[i]==(2 if mode=='early' else 1) for i in targets),'ordered control'
    if mode=='early':assert me<pre
    if mode=='late':assert ms>done
    masks=[]; replicas=0
    for w in range(4):
        masks.append([[int(vs[(w*32+kk)*256+n+j]==2) for j in range(8)] for kk in range(k,k+8)])
        replicas+=sum(vs[(w*32+kk)*256+n+j]!=vs[(w*32+kk+16)*256+n+j] for kk in range(k,k+8) for j in range(8))
    differences={f'{a}-{b}':sum(x!=y for ra,rb in zip(masks[a],masks[b]) for x,y in zip(ra,rb))
                 for a,b in itertools.combinations(range(4),2)}
    columns=[''.join('N' if all(row[j] for row in mask) else 'O' if not any(row[j] for row in mask) else '?' for j in range(8)) for mask in masks]
    return dict(pre=pre,admit=admit,done=done,mut_start=ms,mut_done=me,phase=ms-admit,writer_duration=me-ms,
                masks=masks,columns=columns,pair_differences=differences,replica_disagreements=replicas,
                differing_regions=bool(any(differences.values())),new_count=sum(sum(sum(row) for row in mask) for mask in masks))

def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=('smoke','focus','scan','repeat'),default='focus');p.add_argument('--reps',type=int,default=1);p.add_argument('--build-only',action='store_true');a=p.parse_args()
    assert a.reps>0
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    built={};mods={};jobs=configurations(a.suite)
    for index,cfg in enumerate(jobs,1):
        key=cfg['m'],cfg['k'],cfg['mode'] if cfg['mode'] in ('early','late') else 'race'
        if key not in built:
            diag=io.StringIO()
            with contextlib.redirect_stderr(diag):obj=assemble_kernel(source(*key),arch='sm100a',check_deps=True,strict_deps=True)
            assert not (set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}),diag.getvalue()
            built[key]=obj
        if a.build_only:continue
        if key not in mods:
            mod=CudaModule(built[key].code);mods[key]=mod,mod.devmem_alloc(SIZE)
        mod,ptr=mods[key]
        print(json.dumps(dict(event='launch',index=index,**cfg)),flush=True)
        for rep in range(a.reps):
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            params=[ptr]+[struct.pack('<I',cfg[x]&0xffffffff) for x in ('delta','enabled','pad','lane_xor','nbase')]
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=params);mod.synchronize()
            raw=mod.device_read(ptr,SIZE);signal.alarm(0)
            r=inspect(raw,cfg)
            print(json.dumps(dict(event='result',index=index,rep=rep,**cfg,**r,raw_zlib_b64=base64.b64encode(zlib.compress(raw,9)).decode())),flush=True)
    for mod,ptr in mods.values():mod.devmem_free(ptr)
    print(json.dumps(dict(event='complete',cases=len(jobs),reps=a.reps,suite=a.suite,kernels=len(built),build_only=a.build_only)),flush=True)

if __name__=='__main__':main()
