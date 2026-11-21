"""Sparse shared-B perturbations testing a K16 x N8 staging hypothesis.

Each warp store changes one N column or a whole N8 block, in either K8
half or both halves. Identity A exposes each B element in eight M replicas.
"""
import argparse,base64,contextlib,io,json,re,signal,struct,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel,CudaModule
from probe_sm100_as_b_fetch import source as base,b_offset,FINE_PADS
from probe_sm100_ws_throughput import OUT_SIZE,group

EXTRA=OUT_SIZE+512
CHECK=EXTRA+32+32*4
SIZE=CHECK+8+256
TILES=(0,8,16,24,64,128,192,240)
PATCHES=((128,0),(128,8),(256,0))

def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

def source(width,k,ordering='race',joint=False,checked=False):
    assert not checked or joint and width==256
    s=base(width,0,k,ordering,fine=True)
    s=once(s,'lane_xor<4>)','lane_xor<4>, tile<4>, select_col<4>)')
    anchor='LOP3.LUT R35, R6, R63, RZ, 0x3c, !PT;[7:7:{2}:5:1]'
    s=once(s,anchor,anchor+'\nLDC R64, #param(tile);[2:7:{}:1:0]\n'
           'LDC R65, #param(select_col);[2:7:{}:1:0]\n'
           'SHL R64, R64, 0x8;[7:7:{2}:5:1]')
    anchor=f'IADD3 R36, R36, {0x2000+b_offset(k,0):#x}, RZ;[7:7:{{}}:5:1]'
    s=once(s,anchor,anchor+'\nIADD3 R36, R36, R64, RZ;[7:7:{}:5:1]')
    # R35 is the physical chunk, even under reverse lane assignment. Each
    # column occupies 16 bytes in a K8 half. select_col=8 selects the full N8.
    anchor='ISETP.NE.AND P2, PT, R61, RZ, PT;[7:7:{2}:13:1]'
    s=once(s,anchor,
           f'SHR R66, R35, {2 if width==128 else 1};[7:7:{{2}}:5:1]\n'
           'LOP3.LUT R66, R66, 0x7, RZ, 0xc0, !PT;[7:7:{}:5:1]\n'
           'ISETP.EQ.AND P4, PT, R66, R65, PT;[7:7:{}:13:1]\n'
           'ISETP.EQ.OR P4, PT, R65, 8, P4;[7:7:{}:13:1]\n'
           'ISETP.NE.AND P2, PT, R61, RZ, P4;[7:7:{}:13:1]')
    # Keep writer STGs out of the in-flight window, like the LDTM probe.
    start=s.index('ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]',s.index('#def_label(modifier_store)'))
    end=s.index('#def_label(mma_done)',start)
    exports=s[start:end];s=s[:start]+s[end:]
    marker='@P0 BRA #label(b_verified);[7:7:{}:5:0]'
    s=once(s,marker,marker+'\n'+exports)
    if joint:
        # Capture an output after the same warp has modified and fenced B.
        # No assumption that the fence orders an already-running MMA: that
        # is precisely what the retained final-D evidence tests.
        for col in range(0,256,8):
            st=f'STTM.x8 tmem[UR10+{col:#x}], {group(24,8)};[7:7:{{}}:1:0]'
            init=[]
            for j in range(8):
                bits=struct.unpack('<I',struct.pack('<f',-float(col+j+1)))[0]
                init.append(f'MOV32I R{24+j}, {bits:#x};[7:7:{{}}:5:1]')
            s=once(s,st,'\n'.join(init+[st,'FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]','NOP;[7:7:{0}:8:1]']))
        anchor='ISETP.EQ.AND P0, PT, R4, RZ, PT;[7:7:{}:13:1]'
        s=once(s,anchor,'SHR R67, R64, 0x5;[7:7:{}:5:1]\n'
               'IADD3 R67, R67, R65, RZ;[7:7:{}:5:1]\n'
               'R2UR UR30, R67;[7:7:{}:13:1]\n'
               'UIADD3 UR30, UPT, UPT, UR10, UR30, URZ;[7:7:{}:5:1]\n'+anchor)
        start=s.index('#def_label(modifier_store)');tail=s[start:]
        anchor='CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]'
        tail=once(tail,anchor,anchor+'\nCS2R {R72,R73}, SR_CLOCKLO;[7:7:{}:5:1]\n'
                  'LDTM R70, tmem[UR30];[2:7:{}:1:0]\n'
                  'CS2R {R74,R75}, SR_CLOCKLO;[7:7:{}:5:1]\n'
                  'NOP;[7:7:{2}:8:1]\n'
                  'CS2R {R76,R77}, SR_CLOCKLO;[7:7:{}:5:1]')
        s=s[:start]+tail
        anchor='#def_label(b_verified)'
        exports=[]
        for reg,offset in ((72,0),(74,8),(76,16)):
            exports.append(f'@P1 STG.E.64.STRONG.GPU [{{R2,R3}}+{EXTRA+offset}], {group(reg,2)};[7:1:{{1}}:8:1]')
        exports+=['IMAD.WIDE.U32 {R68,R69}, R6, 4, {R2,R3};[7:7:{}:5:1]',
                  f'STG.E.STRONG.GPU [{{R68,R69}}+{EXTRA+32}], R70;[7:1:{{1,2}}:8:1]',
                  'NOP;[7:7:{1}:8:1]']
        s=once(s,anchor,'\n'.join(exports)+'\n'+anchor)
        if checked:
            anchor='CS2R {R72,R73}, SR_CLOCKLO;[7:7:{}:5:1]'
            s=once(s,anchor,'LDS.64 {R80,R81}, [R36];[2:7:{}:1:0]\n'
                   'NOP;[7:7:{2}:8:1]\n'
                   'CS2R {R78,R79}, SR_CLOCKLO;[7:7:{}:5:1]\n'+anchor)
            anchor='#def_label(b_verified)'
            s=once(s,anchor,
                   f'@P1 STG.E.64.STRONG.GPU [{{R2,R3}}+{CHECK}], {{R78,R79}};[7:1:{{1}}:8:1]\n'
                   'IMAD.WIDE.U32 {R68,R69}, R35, 8, {R2,R3};[7:7:{}:5:1]\n'
                   f'STG.E.64.STRONG.GPU [{{R68,R69}}+{CHECK+8}], {{R80,R81}};[7:1:{{1,2}}:8:1]\n'
                   'NOP;[7:7:{1}:8:1]\n'+anchor)
    assert s.count('UTCHMMA.1CTA')==1
    return s

def configurations(suite):
    tiles=TILES if suite!='smoke' else (0,128)
    patches=[(w,k,n,col,xor) for w,k in PATCHES for n in tiles for col in range(9) for xor in (0,31)]
    if suite in ('joint','checked'):patches=[(256,0,n,col,xor) for n in TILES for col in (0,3,7) for xor in (0,31)]
    jobs=[dict(width=w,k=k,n=n,select_col=col,lane_xor=xor,mode=mode,delta=d,pad=0,enabled=en)
          for w,k,n,col,xor in patches for mode,d,en in (('none',0,0),('early',-512,1),('late',1024,1))]
    if suite in ('cutoff','joint','checked'):
        jobs += [dict(width=w,k=k,n=n,select_col=col,lane_xor=xor,mode='race',delta=16*(n//64)-64,pad=pad,enabled=1)
                 for w,k,n,col,xor in patches for pad in FINE_PADS]
    if suite in ('joint','checked'):
        for cfg in jobs:cfg['joint']=True
    if suite=='checked':
        for cfg in jobs:cfg['checked']=True
    return jobs

def affected(cfg,k,n):
    return (cfg['n']<=n<cfg['n']+8 and (cfg['select_col']==8 or n==cfg['n']+cfg['select_col'])
            and (cfg['width']==256 or cfg['k']<=k<cfg['k']+8))

def inspect(cfg,raw):
    pre,admit,done,ms,me=struct.unpack_from('<5Q',raw);debug=struct.unpack_from('<5I',raw,40)
    epoch,delay,target,observed,diff=debug
    assert pre<admit<done and ms<me
    assert target==(epoch+512+delay)&0xffffffff and diff==(observed-target)&0xffffffff and diff<0x80000000
    assert 0<((ms-epoch)&0xffffffff)<1000000
    vals=struct.unpack_from('<32768f',raw,64)
    mask=[affected(cfg,i//256%16,i%256) for i in range(32768)]
    outside=sum(v!=1. for v,m in zip(vals,mask) if not m)
    other=sum(v not in (1.,2.) for v in vals)
    replicas=sum(v!=vals[i%4096] for i,v in enumerate(vals))
    control=sum(v!=(2. if m and cfg['mode']=='early' else 1.) for v,m in zip(vals,mask)) if cfg['mode']!='race' else 0
    shared=struct.unpack_from(f"<{cfg['width']//2}H",raw,OUT_SIZE)
    off=b_offset(cfg['k'],cfg['n']);expected=[]
    for offset in range(off,off+cfg['width'],2):
        rel=offset-off;n=cfg['n']+(rel%128)//16
        selected=cfg['select_col']==8 or n==cfg['n']+cfg['select_col']
        expected.append(0x4000 if selected and cfg['enabled'] else 0x3f80)
    assert list(shared)==expected,('shared readback',cfg)
    assert not outside and not control,('outside/control',cfg,outside,control)
    if cfg['mode']=='early':assert me<pre
    if cfg['mode']=='late':assert ms>done
    result=dict(pre=pre,admit=admit,done=done,mut_start=ms,mut_done=me,phase=ms-admit,writer_duration=me-ms,
                wait_debug=debug,outside_errors=outside,control_errors=control,other=other,replica_disagreements=replicas,
                new_count=sum(v==2. and m for v,m in zip(vals,mask)),target_count=sum(mask),
                d_zlib_b64=base64.b64encode(zlib.compress(raw[64:OUT_SIZE],9)).decode(),
                shared_zlib_b64=base64.b64encode(zlib.compress(raw[OUT_SIZE:OUT_SIZE+cfg['width']],9)).decode())
    if cfg.get('joint'):
        rs,ra,rd=struct.unpack_from('<3Q',raw,EXTRA);v=struct.unpack_from('<32f',raw,EXTRA+32)
        c=cfg['n']+cfg['select_col'];sentinel=-float(c+1)
        assert me<rs<ra<=rd
        if cfg['mode']=='early':assert rd<pre and all(t==sentinel for t in v)
        if cfg['mode']=='late':assert rs>done and all(t==1. for t in v)
        final_col=[vals[(32+i)*256+c] for i in range(32)]
        result.update(read_start=rs,read_admit=ra,read_done=rd,
                      snapshot_sentinel=sum(t==sentinel for t in v),snapshot_one=sum(t==1. for t in v),
                      snapshot_two=sum(t==2. for t in v),snapshot_other=sum(t not in (sentinel,1.,2.) for t in v),
                      locked_before_visible=(cfg['enabled']==1 and cfg['mode']=='race' and all(t==sentinel for t in v) and all(t==1. for t in final_col)),
                      snapshot_zlib_b64=base64.b64encode(zlib.compress(raw[EXTRA:CHECK],9)).decode())
        if cfg.get('checked'):
            checked_done=struct.unpack_from('<Q',raw,CHECK)[0]
            early_shared=struct.unpack_from('<128H',raw,CHECK+8)
            assert me<checked_done<rs and list(early_shared)==expected,('in-flight shared readback',cfg)
            result.update(shared_check_done=checked_done,
                          checked_zlib_b64=base64.b64encode(zlib.compress(raw[CHECK:SIZE],9)).decode())
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=('smoke','cutoff','joint','checked'),default='cutoff');p.add_argument('--reps',type=int,default=1);p.add_argument('--build-only',action='store_true');a=p.parse_args()
    assert a.reps>0
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    built={};modules={};jobs=configurations(a.suite)
    for index,cfg in enumerate(jobs,1):
        key=cfg['width'],cfg['k'],cfg['mode'] if cfg['mode'] in ('early','late') else 'race'
        if key not in built:
            diag=io.StringIO()
            with contextlib.redirect_stderr(diag):r=assemble_kernel(source(*key,joint=a.suite in ('joint','checked'),checked=a.suite=='checked'),arch='sm100a',check_deps=True,strict_deps=True)
            assert not (set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}),diag.getvalue()
            built[key]=r.code
        if a.build_only:continue
        if key not in modules:
            mod=CudaModule(built[key]);modules[key]=mod,mod.devmem_alloc(SIZE)
        mod,ptr=modules[key]
        for rep in range(a.reps):
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            args=[ptr,struct.pack('<i',cfg['delta'])]+[struct.pack('<I',v) for v in (cfg['enabled'],cfg['pad'],cfg['lane_xor'],cfg['n']//8,cfg['select_col'])]
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=args);mod.synchronize()
            raw=mod.device_read(ptr,SIZE);signal.alarm(0)
            r=inspect(cfg,raw);print(json.dumps(dict(event='result',index=index,rep=rep,**cfg,**r)),flush=True)
    for mod,ptr in modules.values():mod.devmem_free(ptr)
    print(json.dumps(dict(event='complete',suite=a.suite,reps=a.reps,cases=len(jobs),kernels=len(built),build_only=a.build_only)),flush=True)
if __name__=='__main__':main()
