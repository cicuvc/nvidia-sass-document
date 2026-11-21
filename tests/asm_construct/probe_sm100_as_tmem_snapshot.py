"""Timed in-flight LDTM observations of one AS M128N256K16 UTCHMMA.

Old D[m,n]=-(n+1); identity A and constant BF16 B give final D[m,n]=1.
Each launch captures one x1/x2/x16 read from one observer warp, then validates
all 128x256 final values after the producer completion and CTA rendezvous.
"""
import argparse,base64,contextlib,io,json,re,signal,struct,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel,CudaModule
from probe_sm100_as_b_fetch import source as timed_base,FINE_PADS
from probe_sm100_ws_throughput import OUT_SIZE,group

EXTRA=OUT_SIZE+32*16*4
SIZE=EXTRA+32
COLUMNS=(0,1,64,65,128,192,240)
WIDTHS=(1,2,16)
WARPS=(1,2,3)
ALIGN_COLUMNS=tuple(sorted(set(range(0,241,8))|set(range(7,241,8))))
CONFIRM_COLUMNS=tuple(range(32))+tuple(range(112,144))+tuple(range(224,256))

def replace_once(s,old,new):
    assert s.count(old)==1,(old,s.count(old))
    return s.replace(old,new)

def source(width=1,warp=1,ordering='race',paired=False):
    assert width in WIDTHS and warp in WARPS
    assert not paired or width==2
    s=timed_base(128,0,0,'race' if ordering=='none' else ordering,fine=True)
    s=replace_once(s,'#fn ws_throughput(', '#fn tmem_snapshot(')
    s=s.replace('lane_xor','column')
    # Initialize every column with a recognizable exact sentinel. Each STTM
    # is fenced before changing its source registers; setup is outside timing.
    for col in range(0,256,8):
        st=f'STTM.x8 tmem[UR10+{col:#x}], {group(24,8)};[7:7:{{}}:1:0]'
        init=[]
        for j in range(8):
            bits=struct.unpack('<I',struct.pack('<f',-float(col+j+1)))[0]
            init.append(f'MOV32I R{24+j}, {bits:#x};[7:7:{{}}:5:1]')
        init += [st,'FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]','NOP;[7:7:{0}:8:1]']
        s=replace_once(s,st,'\n'.join(init))
    if ordering=='none':
        mma=next(line for line in s.splitlines() if line.startswith('UTCHMMA.1CTA'))
        s=replace_once(s,mma,'NOP;[7:7:{}:1:1]')
    addr='LOP3.LUT R35, R6, R63, RZ, 0x3c, !PT;[7:7:{2}:5:1]'
    s=replace_once(s,addr,'R2UR UR30, R63;[7:7:{2}:13:1]\n'
                   'UIADD3 UR30, UPT, UPT, UR10, UR30, URZ;[7:7:{}:5:1]\n'
                   'MOV R35, R6;[7:7:{}:5:1]')
    if paired:
        anchor='MOV R35, R6;[7:7:{}:5:1]'
        s=replace_once(s,anchor,anchor+'\nMOV32I R64, 240;[7:7:{}:5:1]\n'
                       'IADD3 R64, R64, -R63, RZ;[7:7:{}:5:1]\n'
                       'R2UR UR31, R64;[7:7:{}:13:1]\n'
                       'UIADD3 UR31, UPT, UPT, UR10, UR31, URZ;[7:7:{}:5:1]')
    s=replace_once(s,'ISETP.EQ.AND P0, PT, R5, 0x1, PT;[7:7:{0}:13:1]',
                   f'ISETP.EQ.AND P0, PT, R5, {warp:#x}, PT;[7:7:{{0}}:13:1]')
    suffix='' if width==1 else f'.x{width}'
    operand='R40' if width==1 else group(40,width)
    start=s.index('CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]\n@P2 STS')
    end=s.index('#def_label(mma_done)',start)
    snapshot=['CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]',
              f'LDTM{suffix} {operand}, tmem[UR30];[2:7:{{}}:1:0]',
              'CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:1]',
              'NOP;[7:7:{2}:8:1]',
              'CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]']
    if paired:
        snapshot=['CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]',
                  'LDTM R40, tmem[UR30];[2:7:{}:1:0]',
                  'CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:1]',
                  'NOP;[7:7:{2}:8:1]',
                  'CS2R {R24,R25}, SR_CLOCKLO;[7:7:{}:5:1]',
                  'CS2R {R26,R27}, SR_CLOCKLO;[7:7:{}:5:1]',
                  'LDTM R41, tmem[UR31];[2:7:{}:1:0]',
                  'CS2R {R28,R29}, SR_CLOCKLO;[7:7:{}:5:1]',
                  'NOP;[7:7:{2}:8:1]',
                  'CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]']
    if ordering=='early':snapshot += ['WARPSYNC.ALL;[7:7:{}:5:0]','BAR.SYNC 1;[7:7:{}:5:1]']
    s=s[:start]+'\n'.join(snapshot)+'\n'+s[end:]
    # Export the captured registers only AFTER both parties finish. No global
    # traffic between the sampled LDTM and the producer completion timestamp.
    start=s.index('ISETP.NE.AND P0, PT, R5, 1, PT;[7:7:{}:13:1]')
    end=s.index('#def_label(b_verified)',start)+len('#def_label(b_verified)')
    export=[f'ISETP.NE.AND P0, PT, R5, {warp}, PT;[7:7:{{}}:13:1]',
            '@P0 BRA #label(b_verified);[7:7:{}:5:0]',
            'ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]',
            '@P1 STG.E.64.STRONG.GPU [{R2,R3}+24], {R16,R17};[7:0:{}:8:1]',
            '@P1 STG.E.64.STRONG.GPU [{R2,R3}+32], {R18,R19};[7:1:{0}:8:1]',
            f'@P1 STG.E.64.STRONG.GPU [{{R2,R3}}+{EXTRA}], {{R22,R23}};[7:1:{{1}}:8:1]']
    if paired:
        for reg,off in ((24,8),(26,16),(28,24)):
            export += [f'@P1 STG.E.64.STRONG.GPU [{{R2,R3}}+{EXTRA+off}], {group(reg,2)};[7:1:{{1}}:8:1]']
    for reg,offset in ((30,40),(60,44),(31,48),(32,52),(34,56)):
        export += [f'@P1 STG.E.STRONG.GPU [{{R2,R3}}+{offset}], R{reg};[7:1:{{1}}:8:1]']
    export += [f'IMAD.WIDE.U32 {{R38,R39}}, R6, {width*4}, {{R2,R3}};[7:7:{{}}:5:1]']
    chunk=min(width,4);stsz={1:'',2:'.64',4:'.128'}[chunk]
    for j in range(0,width,chunk):
        regs=f'R{40+j}' if chunk==1 else group(40+j,chunk)
        export += [f'STG.E{stsz}.STRONG.GPU [{{R38,R39}}+{OUT_SIZE+4*j}], {regs};[7:1:{{1,2}}:8:1]']
    export += ['NOP;[7:7:{0,1,2}:8:1]','#def_label(b_verified)']
    s=s[:start]+'\n'.join(export)+s[end:]
    assert s.count('UTCHMMA.1CTA')==(0 if ordering=='none' else 1)
    assert s.count('LDTM')==(3 if paired else 2)
    return s

def configurations(suite):
    patches=([(1,warp,col) for warp in (2,3) for col in CONFIRM_COLUMNS]+
             [(2,1,col) for col in range(255)] if suite=='granularity' else
             [(1,1,col) for col in range(256)] if suite=='columns' else
             [(16,1,col) for col in ALIGN_COLUMNS] if suite=='alignment' else
             [(2,warp,col) for warp in WARPS for col in (0,240)] if suite=='paired'
             else [(w,warp,col) for w in WIDTHS for warp in WARPS for col in COLUMNS])
    jobs=[dict(width=w,warp=warp,column=col,mode=mode,delta=delta,pad=0,enabled=enabled)
          for w,warp,col in patches for mode,delta,enabled in [('none',0,0),('early',-512,1),('late',1024,1)]]
    if suite=='coarse':
        jobs += [dict(width=w,warp=warp,column=col,mode='race',delta=d,pad=0,enabled=1)
                 for w,warp,col in patches for d in range(-64,257,16)]
    if suite=='fine':
        jobs += [dict(width=w,warp=warp,column=col,mode='race',
                      delta=0 if col<64 else 64 if col<192 else 128,pad=pad,enabled=1)
                 for w,warp,col in patches for pad in FINE_PADS]
    if suite=='paired':
        jobs += [dict(width=w,warp=warp,column=col,mode='race',delta=0,pad=pad,enabled=1)
                 for w,warp,col in patches for pad in FINE_PADS]
    if suite in ('alignment','columns','granularity'):
        jobs += [dict(width=w,warp=warp,column=col,mode='race',
                      delta=16*(col//32)-32,pad=pad,enabled=1)
                 for w,warp,col in patches for pad in FINE_PADS]
    return jobs

def main(source_factory=source,experiment='as'):
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=('smoke','coarse','fine','paired','alignment','columns','granularity'),default='coarse')
    p.add_argument('--reps',type=int,default=3);p.add_argument('--build-only',action='store_true');a=p.parse_args()
    if a.reps<1:p.error('positive reps required')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    built={};modules={};jobs=configurations(a.suite);paired=a.suite=='paired'
    for index,cfg in enumerate(jobs,1):
        width,warp,col=cfg['width'],cfg['warp'],cfg['column'];mode=cfg['mode']
        ordering=mode if mode in ('none','early','late') else 'race';key=(width,warp,ordering)
        if key not in built:
            diag=io.StringIO()
            with contextlib.redirect_stderr(diag):result=assemble_kernel(source_factory(*key,paired=paired),arch='sm100a',check_deps=True,strict_deps=True)
            unexpected=set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}
            if unexpected:raise RuntimeError(diag.getvalue())
            built[key]=result.code
        if a.build_only:continue
        if key not in modules:
            print(json.dumps(dict(event='module_load',experiment=experiment,width=width,warp=warp,mode=ordering)),flush=True)
            mod=CudaModule(built[key]);modules[key]=(mod,mod.devmem_alloc(SIZE))
        mod,ptr=modules[key]
        print(json.dumps(dict(event='launch',index=index,**cfg)),flush=True)
        for rep in range(a.reps):
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            params=[ptr,struct.pack('<i',cfg['delta'])]+[struct.pack('<I',cfg[k]) for k in ('enabled','pad','column')]
            mod.launch('tmem_snapshot',grid=(1,),block=(128,),args=params)
            mod.synchronize();raw=mod.device_read(ptr,SIZE);signal.alarm(0)
            pre,admit,done,rs,rend=struct.unpack_from('<5Q',raw)
            ra=struct.unpack_from('<Q',raw,EXTRA)[0]
            debug=struct.unpack_from('<5I',raw,40);epoch,delay,target,observed,diff=debug
            assert pre<admit<done and rs<ra<=rend,('timestamps',cfg,(pre,admit,done,rs,ra,rend))
            assert target==(epoch+512+delay)&0xffffffff and diff==(observed-target)&0xffffffff and diff<0x80000000,('clock arithmetic',cfg,debug)
            assert 0<((rs-epoch)&0xffffffff)<1000000,('epoch',cfg,debug)
            final=struct.unpack_from('<32768f',raw,64)
            final_errors=sum(v!=(1. if cfg['enabled'] else -float(i%256+1)) for i,v in enumerate(final))
            vals=struct.unpack_from(f'<{32*width}f',raw,OUT_SIZE)
            columns=(col,240-col) if paired else tuple(range(col,col+width))
            old=sum(v==-float(columns[i%width]+1) for i,v in enumerate(vals));new=sum(v==1. for v in vals)
            other=len(vals)-old-new
            control_errors=(len(vals)-new if mode=='late' else len(vals)-old if mode in ('early','none') else 0)
            row_disagreements=sum(v!=vals[i%width] for i,v in enumerate(vals))
            r=dict(event='result',experiment=experiment,rep=rep,**cfg,pre=pre,admit=admit,done=done,read_start=rs,read_admit=ra,read_done=rend,
                   phase=rs-admit,read_issue_interval=ra-rs,read_interval=rend-rs,completion_interval=done-admit,
                   wait_debug=debug,final_errors=final_errors,control_errors=control_errors,old=old,new=new,other=other,
                   row_disagreements=row_disagreements,
                   snapshot_zlib_b64=base64.b64encode(zlib.compress(raw[OUT_SIZE:OUT_SIZE+32*width*4],9)).decode(),
                   d_zlib_b64=base64.b64encode(zlib.compress(raw[64:OUT_SIZE],9)).decode())
            if paired:
                first_done,second_start,second_admit=struct.unpack_from('<3Q',raw,EXTRA+8)
                assert rs<ra<=first_done<second_start<second_admit<=rend,('ordered reads',cfg)
                r.update(paired=True,second_column=240-col,first_read_done=first_done,
                         second_read_start=second_start,second_read_admit=second_admit,
                         first_new=sum(v==1. for v in vals[::2]),second_new=sum(v==1. for v in vals[1::2]))
            print(json.dumps(r),flush=True)
            assert not final_errors and not control_errors,('control/final validation',cfg,final_errors,control_errors)
            if mode=='early':assert rend<pre,('early ordering',cfg)
            if mode=='late':assert rs>done,('late ordering',cfg)
    for mod,ptr in modules.values():mod.devmem_free(ptr)
    print(json.dumps(dict(event='complete',experiment=experiment,suite=a.suite,reps=a.reps,cases=len(jobs),kernels=len(built),build_only=a.build_only)),flush=True)

if __name__=='__main__':main()
