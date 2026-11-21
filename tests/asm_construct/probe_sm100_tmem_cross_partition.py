"""Same-launch, same-column observations from three TMEM row regions.

Rotate the producer warp to cover all six region pairs. No communication or
global exports between observers until all reads and MMA have completed.
This intentionally races LDTM with MMA; it tests silicon visibility only.
"""
import argparse,base64,contextlib,io,itertools,json,re,signal,struct,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel,CudaModule
from probe_sm100_as_tmem_snapshot import source as base,replace_once,FINE_PADS
from probe_sm100_ws_throughput import OUT_SIZE

SIZE=OUT_SIZE+4*256
COLUMNS=(0,1,64,128,192,240,250,254)
SKEWS=((0,0,0),(-8,0,8),(8,0,-8),(-32,0,32),(32,0,-32))

def source(experiment='as',ordering='race'):
    assert experiment in ('as','ws') and ordering in ('none','early','late','race')
    s=base(1,1,ordering)
    s=replace_once(s,'#fn tmem_snapshot(out<8>, delta<4>, enabled<4>, pad<4>, column<4>)',
                   '#fn cross_partition(out<8>, delta<4>, enabled<4>, pad<4>, column<4>, producer<4>, skew0<4>, skew1<4>, skew2<4>, skew3<4>)')
    # Set each warp's target before publishing the common future epoch.
    anchor='LDC R60, #param(delta);[2:7:{}:1:0]'
    prep=[anchor,'LDC R65, #param(producer);[2:7:{}:1:0]']
    for w in range(4):
        prep += [f'LDC R{68+w}, #param(skew{w});[2:7:{{}}:1:0]']
    prep += ['MOV R72, RZ;[7:7:{2}:5:1]']
    for w in range(4):
        prep += [f'ISETP.EQ.AND P0, PT, R5, {w}, PT;[7:7:{{}}:13:1]',
                 f'SEL R72, R{68+w}, R72, P0;[7:7:{{}}:5:1]']
    prep += ['IADD3 R60, R60, R72, RZ;[7:7:{}:5:1]']
    s=replace_once(s,anchor,'\n'.join(prep))
    s=replace_once(s,'ISETP.EQ.AND P0, PT, R5, 0x1, PT;[7:7:{0}:13:1]',
                   'ISETP.NE.AND P0, PT, R5, R65, PT;[7:7:{0}:13:1]')
    # The old idle path is unreachable: all non-producers take modifier.
    anchor='@P0 BRA #label(modifier);[7:7:{}:5:0]\nISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]'
    s=replace_once(s,anchor,anchor.replace('R5, RZ','R5, R65'))
    start=s.index('ISETP.NE.AND P0, PT, R5, 1, PT;[7:7:{}:13:1]')
    end=s.index('#def_label(b_verified)',start)+len('#def_label(b_verified)')
    export=['ISETP.EQ.AND P0, PT, R5, R65, PT;[7:7:{}:13:1]',
            '@P0 BRA #label(b_verified);[7:7:{}:5:0]',
            'IMAD.WIDE.U32 {R66,R67}, R5, 256, {R2,R3};[7:7:{}:5:1]',
            'ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]']
    for reg,offset in ((16,0),(22,8),(18,16)):
        export += [f'@P1 STG.E.64.STRONG.GPU [{{R66,R67}}+{OUT_SIZE+offset}], {{R{reg},R{reg+1}}};[7:1:{{1}}:8:1]']
    for reg,offset in ((30,24),(60,28),(31,32),(32,36),(34,40)):
        export += [f'@P1 STG.E.STRONG.GPU [{{R66,R67}}+{OUT_SIZE+offset}], R{reg};[7:1:{{1}}:8:1]']
    for j in range(5):
        export += [f'@P1 STG.E.STRONG.GPU [{{R66,R67}}+{OUT_SIZE+44+4*j}], R{68+j};[7:1:{{1}}:8:1]']
    export += ['IMAD.WIDE.U32 {R38,R39}, R6, 4, {R66,R67};[7:7:{}:5:1]',
               f'STG.E.STRONG.GPU [{{R38,R39}}+{OUT_SIZE+64}], R40;[7:1:{{1,2}}:8:1]',
               'NOP;[7:7:{1}:8:1]','#def_label(b_verified)']
    s=s[:start]+'\n'.join(export)+s[end:]
    if experiment=='ws':s=s.replace('UTCHMMA.1CTA ','UTCHMMA.1CTA.WS ')
    assert s.count('LDTM')==2
    return s

def configurations(suite):
    cols=(0,254) if suite=='smoke' else COLUMNS
    jobs=[]
    for mode in ('none','early','late','race'):
        if suite=='smoke' and mode=='race':continue
        for experiment,producer,column in itertools.product(('as','ws'),range(4),cols):
            for skew,pad in itertools.product(SKEWS, FINE_PADS if mode=='race' else (0,)):
                observers=[w for w in range(4) if w!=producer]
                offsets=[0]*4
                for w,d in zip(observers,skew):offsets[w]=d
                delta=16*(column//32)-32 if mode=='race' else {'none':0,'early':-512,'late':1024}[mode]
                jobs.append(dict(experiment=experiment,producer=producer,column=column,mode=mode,
                                 delta=delta,enabled=int(mode!='none'),pad=pad,skews=offsets))
    return jobs

def pack(raw):return base64.b64encode(zlib.compress(raw,9)).decode()

def inspect(raw,cfg,final_reference=None,new_values=None):
    assert len(raw)==SIZE
    pre,admit,done=struct.unpack_from('<3Q',raw)
    assert pre<admit<done
    final=struct.unpack_from('<32768f',raw,64)
    final_errors=(sum(v!=ref for v,ref in zip(final,final_reference)) if final_reference is not None else
                  sum(v!=(1. if cfg['enabled'] else -float(i%256+1)) for i,v in enumerate(final)))
    if final_reference is not None:assert len(final_reference)==len(final)
    records=[];control_errors=other=row_disagreements=0
    for w in range(4):
        offset=OUT_SIZE+w*256
        if w==cfg['producer']:
            assert raw[offset:offset+256]==bytes(256),'producer wrote observer record'
            continue
        rs,ra,rd=struct.unpack_from('<3Q',raw,offset)
        epoch,delay,target,observed,diff=struct.unpack_from('<5I',raw,offset+24)
        skew_debug=list(struct.unpack_from('<5I',raw,offset+44))
        assert skew_debug==[s&0xffffffff for s in cfg['skews']+[cfg['skews'][w]]],('skew selection',w,skew_debug,cfg['skews'])
        expected_delay=cfg['delta']+cfg['skews'][w]
        assert delay==expected_delay&0xffffffff,('delay',w,delay,expected_delay&0xffffffff)
        assert target==(epoch+512+delay)&0xffffffff
        assert diff==(observed-target)&0xffffffff and diff<0x80000000
        assert rs<ra<=rd and 0<((rs-epoch)&0xffffffff)<1000000
        if cfg['mode']=='early':assert rd<pre
        if cfg['mode']=='late':assert rs>done
        vals=struct.unpack_from('<32f',raw,offset+64)
        old=sum(v==-float(cfg['column']+1) for v in vals)
        new=sum(v==(new_values[w] if new_values is not None else 1.) for v in vals)
        other+=32-old-new;row_disagreements+=sum(v!=vals[0] for v in vals)
        control_errors+=32-new if cfg['mode']=='late' else 32-old if cfg['mode'] in ('early','none') else 0
        records.append(dict(warp=w,read_start=rs,read_admit=ra,read_done=rd,phase=rs-admit,
                            old=old,new=new,wait_debug=[epoch,delay,target,observed,diff],skew_debug=skew_debug))
    assert len({r['wait_debug'][0] for r in records})==1
    # Compare only within one launch and one column. Do not conflate source
    # issue order with the unobserved SRAM sampling order.
    start_inversions=[];strong_inversions=[];mixed_pairs=[];ordered_pairs=[]
    for a,b in itertools.permutations(records,2):
        if a['read_done']<b['read_start']:ordered_pairs.append([a['warp'],b['warp']])
        if a['new']==32 and b['old']==32:
            mixed_pairs.append([a['warp'],b['warp']])
            if a['read_start']<b['read_start']:start_inversions.append([a['warp'],b['warp']])
            if a['read_done']<b['read_start']:strong_inversions.append([a['warp'],b['warp']])
    return dict(pre=pre,admit=admit,done=done,records=records,final_errors=final_errors,
                control_errors=control_errors,other=other,row_disagreements=row_disagreements,
                start_inversions=start_inversions,strong_inversions=strong_inversions,
                mixed_pairs=mixed_pairs,ordered_pairs=ordered_pairs)

def main(source_factory=source,config_factory=configurations,inspector=inspect,suites=('smoke','scan')):
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=suites,default='scan')
    p.add_argument('--reps',type=int,default=1);p.add_argument('--build-only',action='store_true');a=p.parse_args()
    assert a.reps>0
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    built={};modules={};jobs=config_factory(a.suite)
    for index,cfg in enumerate(jobs,1):
        key=(cfg['experiment'],cfg['mode'])
        if key not in built:
            diag=io.StringIO()
            with contextlib.redirect_stderr(diag):compiled=assemble_kernel(source_factory(*key),arch='sm100a',check_deps=True,strict_deps=True)
            unexpected=set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}
            if unexpected:raise RuntimeError(diag.getvalue())
            built[key]=compiled.code
        if a.build_only:continue
        if key not in modules:
            print(json.dumps(dict(event='module_load',experiment=key[0],mode=key[1])),flush=True)
            mod=CudaModule(built[key]);modules[key]=(mod,mod.devmem_alloc(SIZE))
        mod,ptr=modules[key]
        for rep in range(a.reps):
            print(json.dumps(dict(event='launch',index=index,rep=rep,**cfg)),flush=True)
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            args=[ptr]+[struct.pack('<I',v&0xffffffff) for v in [cfg['delta'],cfg['enabled'],cfg['pad'],cfg['column'],cfg['producer'],*cfg['skews']]]
            mod.launch('cross_partition',grid=(1,),block=(128,),args=args)
            mod.synchronize();raw=mod.device_read(ptr,SIZE);signal.alarm(0)
            try:result=inspector(raw,cfg)
            except Exception:
                print(json.dumps(dict(event='validation_failure',rep=rep,**cfg,raw_zlib_b64=pack(raw))),flush=True)
                raise
            print(json.dumps(dict(event='result',rep=rep,**cfg,**result,raw_zlib_b64=pack(raw))),flush=True)
            assert not any(result[k] for k in ('final_errors','control_errors','other','row_disagreements')),result
    for mod,ptr in modules.values():mod.devmem_free(ptr)
    print(json.dumps(dict(event='complete',suite=a.suite,reps=a.reps,cases=len(jobs),kernels=len(built),build_only=a.build_only)),flush=True)

if __name__=='__main__':main()
