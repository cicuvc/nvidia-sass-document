"""M32 WS B-version capture under one 128B, 32-distinct-bank scalar STS.

Complementary bank subsets address the four N64 bands. Only final D is read.
No atomicity or physical TC-buffer topology is assumed by the validator.
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

def band(q,partition,swap):
    return ((q&3) if partition=='interleaved' else (q>>3))^swap

def address(q,n,k,partition,swap):
    return 0x2000+n*32+band(q,partition,swap)*2048+k*16+4*q

def source(k,partition,ordering='race'):
    assert k in (0,8) and partition in ('interleaved','quarters')
    s=base(128,0,0,ordering,fine=True)
    s=once(s,'lane_xor<4>)','lane_xor<4>, nbase<4>, tile_swap<4>)')
    s=once(s,'UTCHMMA.1CTA tmem[UR12]','UTCHMMA.1CTA.WS tmem[UR12]')
    old=(8<<24)|(32<<17)|0x490;new=(2<<24)|(32<<17)|0x490
    s=once(s,f'UMOV UR15, {old:#x};',f'UMOV UR15, {new:#x};')
    a='SHL R36, R35, 2;[7:7:{}:5:1]\nIADD3 R36, R36, 0x2000, RZ;[7:7:{}:5:1]'
    b=['LDC R64, #param(nbase);[2:7:{}:1:0]',
       'LDC R65, #param(tile_swap);[2:7:{}:1:0]',
       'LOP3.LUT R66, R35, 3, RZ, 0xc0, !PT;[7:7:{}:5:1]' if partition=='interleaved' else 'SHR R66, R35, 3;[7:7:{}:5:1]',
       'LOP3.LUT R66, R66, R65, RZ, 0x3c, !PT;[7:7:{2}:5:1]',
       'SHL R36, R35, 2;[7:7:{}:5:1]',
       'IMAD R36, R66, 0x800, R36;[7:7:{}:5:1]',
       'IMAD R36, R64, 32, R36;[7:7:{}:5:1]',
       f'IADD3 R36, R36, {0x2000+16*k:#x}, RZ;[7:7:{{}}:5:1]']
    s=once(s,a,'\n'.join(b))
    echo=['ISETP.EQ.AND P1, PT, R4, 32, PT;[7:7:{}:13:1]']
    for i,r in enumerate(range(60,66)):
        echo.append(f'@P1 STG.E.STRONG.GPU [{{R2,R3}}+{OUT_SIZE+512+4*i:#x}], R{r};[7:1:{{1}}:8:1]')
    echo.append('NOP;[7:7:{1}:8:1]')
    s=once(s,'#def_label(b_verified)','#def_label(b_verified)\n'+'\n'.join(echo))
    assert s.count('@P2 STS [R36], R24;')==1 and '@P2 STS.128' not in s
    return s

def configurations(suite):
    jobs=[]
    for mode in ('none','early','late','race'):
        if suite=='smoke' and mode=='race':continue
        for k,partition in itertools.product((0,8),('interleaved','quarters')):
            blocks=range(0,64,8) if suite=='scan' else (0,) if suite=='repeat' else (0,16,32,56)
            for n,swap,lx in itertools.product(blocks,range(4),(0,31)):
                delays=((-64,) if suite=='repeat' else (-128,-64,0,64)) if mode=='race' else ({'none':0,'early':-512,'late':1024}[mode],)
                timings=((-64,36),(0,2),(0,8),(0,14),(0,0)) if suite=='repeat' and mode=='race' else itertools.product(delays,FINE_PADS if mode=='race' else (0,))
                for d,pad in timings:
                    jobs.append(dict(k=k,partition=partition,nbase=n,tile_swap=swap,lane_xor=lx,mode=mode,delta=d,pad=pad,enabled=int(mode!='none')))
    return jobs

@functools.lru_cache(None)
def layout(k,n,partition,swap):
    selected=[[],[],[],[]];copies=[];outside=[];zero=[]
    for w in range(4):
        coords={(k+2*(q%4)+h,n+q//4) for q in range(32) if band(q,partition,swap)==w for h in (0,1)}
        assert len(coords)==16
        for lane in range(32):
            for c in range(256):
                i=(w*32+lane)*256+c
                if c>=64:zero.append(i)
                elif (lane%16,c) in coords:
                    if lane<16:selected[w].append(i)
                    else:copies.append((i,i-16*256))
                else:outside.append(i)
    return selected,copies,outside,zero

def inspect(raw,cfg):
    k,n,partition,swap=cfg['k'],cfg['nbase'],cfg['partition'],cfg['tile_swap'];mode=cfg['mode']
    pre,admit,done,ms,me=struct.unpack_from('<5Q',raw);assert pre<admit<done and ms<me
    epoch,delay,target,observed,diff=struct.unpack_from('<5I',raw,40)
    assert target==(epoch+512+delay)&0xffffffff and diff==(observed-target)&0xffffffff and diff<0x80000000
    assert 0<((ms-epoch)&0xffffffff)<1000000
    echo=struct.unpack_from('<6I',raw,OUT_SIZE+512)
    assert echo==tuple(cfg[x]&0xffffffff for x in ('delta','enabled','pad','lane_xor','nbase','tile_swap')),(echo,cfg)
    shared=struct.unpack_from('<64H',raw,OUT_SIZE)
    assert all(x==(0x4000 if cfg['enabled'] else 0x3f80) for x in shared),'writer readback'
    vs=struct.unpack_from('<32768f',raw,64)
    selected,copies,outside,zero=layout(k,n,partition,swap)
    assert all(vs[i]==0 for i in zero),'outside footprint'
    assert all(vs[i]==1 for i in outside),'outside patch'
    targets=[i for indices in selected for i in indices]+[i for i,j in copies]
    assert all(vs[i] in (1,2) for i in targets),'unexpected value'
    if mode!='race':assert all(vs[i]==(2 if mode=='early' else 1) for i in targets),'control'
    if mode=='early':assert me<pre
    if mode=='late':assert ms>done
    masks=[[int(vs[i]==2) for i in indices] for indices in selected]
    states=''.join('N' if all(mask) else 'O' if not any(mask) else 'M' for mask in masks)
    return dict(pre=pre,admit=admit,done=done,mut_start=ms,mut_done=me,phase=ms-admit,writer_duration=me-ms,
                masks=masks,states=states,prefix_order=states in ('NNNN','ONNN','OONN','OOON','OOOO'),
                replica_disagreements=sum(vs[i]!=vs[j] for i,j in copies),
                group_split='M' not in states and states not in ('OOOO','NNNN'),new_count=sum(sum(mask) for mask in masks))

def static_check():
    for cfg in configurations('scan'):
        if cfg['mode']!='none':continue
        addrs=[address(lane^cfg['lane_xor'],cfg['nbase'],cfg['k'],cfg['partition'],cfg['tile_swap']) for lane in range(32)]
        assert len(set(addrs))==32 and sorted((a//4)%32 for a in addrs)==list(range(32))
        for lane,a in enumerate(addrs):
            q=lane^cfg['lane_xor'];logical_n=cfg['nbase']+q//4+64*band(q,cfg['partition'],cfg['tile_swap'])
            assert a==0x2000+b_offset(cfg['k']+2*(q%4),logical_n)
        assert [sum(0x2000+2048*b<=a<0x2000+2048*(b+1) for a in addrs) for b in range(4)]==[8]*4
    return dict(writer='one scalar STS, 32 active lanes x 4 bytes',banks=list(range(32)),bytes_per_tile=32)

def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=('smoke','focus','scan','repeat'),default='scan');p.add_argument('--reps',type=int,default=1);p.add_argument('--build-only',action='store_true');a=p.parse_args();assert a.reps>0
    print(json.dumps(dict(event='static',**static_check())),flush=True)
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    built={};mods={};jobs=configurations(a.suite)
    for index,cfg in enumerate(jobs,1):
        key=cfg['k'],cfg['partition'],cfg['mode'] if cfg['mode'] in ('early','late') else 'race'
        if key not in built:
            diag=io.StringIO()
            with contextlib.redirect_stderr(diag):obj=assemble_kernel(source(*key),arch='sm100a',check_deps=True,strict_deps=True)
            assert not (set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}),diag.getvalue()
            built[key]=obj
        if a.build_only:continue
        if key not in mods:
            mod=CudaModule(built[key].code);mods[key]=mod,mod.devmem_alloc(SIZE)
        mod,ptr=mods[key];print(json.dumps(dict(event='launch',index=index,**cfg)),flush=True)
        for rep in range(a.reps):
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            params=[ptr]+[struct.pack('<I',cfg[x]&0xffffffff) for x in ('delta','enabled','pad','lane_xor','nbase','tile_swap')]
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=params);mod.synchronize()
            raw=mod.device_read(ptr,SIZE);signal.alarm(0);r=inspect(raw,cfg)
            print(json.dumps(dict(event='result',index=index,rep=rep,**cfg,**r,raw_zlib_b64=base64.b64encode(zlib.compress(raw,9)).decode())),flush=True)
    for mod,ptr in mods.values():mod.devmem_free(ptr)
    print(json.dumps(dict(event='complete',cases=len(jobs),reps=a.reps,suite=a.suite,kernels=len(built),build_only=a.build_only)),flush=True)
if __name__=='__main__':main()
