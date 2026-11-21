"""AS B-fetch tomography: identity A, one shared store, complete D readback.

Intentional input race is a silicon diagnostic, not a portable CUDA/PTX program.
Store issue and fence timestamps bound the writer, not a guaranteed atomic bus
transaction. Different store widths and repeated identity rows are controls.
"""
import argparse,base64,contextlib,io,json,re,signal,struct,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel,CudaModule
from probe_sm100_ws_throughput import source as base,OUT_SIZE,group

SIZE=OUT_SIZE+512
FINE_PADS=tuple(range(0,57,2))

def b_offset(k,n):
    return 2*((n//8)*128+(k//8)*64+(n%8)*8+k%8)

def clock_wait(label,modifier=False):
    a=['IADD3 R31, R30, 512, RZ;[7:7:{}:5:1]']
    if modifier:a+=['IADD3 R31, R31, R60, RZ;[7:7:{}:5:1]']
    return a+[f'#def_label({label})','CS2R {R32,R33}, SR_CLOCKLO;[7:7:{}:13:1]',
              'NOP;[7:7:{}:8:1]', 'NOP;[7:7:{}:8:1]',
              'IADD3 R34, R32, -R31, RZ;[7:7:{}:5:1]',
              'ISETP.LT.AND P3, PT, R34, RZ, PT;[7:7:{}:13:1]',
              f'@P3 BRA #label({label});[7:7:{{}}:5:0]']

def source(width,n,k,ordering='race',fine=False,tagged=False):
    assert width in (128,256,512) and n%16==0 and k in (0,8)
    assert k==0 or width==128
    assert ordering in ('race','early','late')
    assert not tagged or fine
    rendezvous=['WARPSYNC.ALL;[7:7:{}:5:0]', 'BAR.SYNC 1;[7:7:{}:5:1]']
    off=b_offset(k,n); perlane=width//32
    suffix={128:'',256:'.64',512:'.128'}[width]
    values='R24' if width==128 else group(24,perlane//4)
    loaded='R40' if width==128 else group(40,perlane//4)
    s=base(m=128,n=256,count=8,mode='discard',atmem=True,ws=False)
    s=s.replace('out<8>)','out<8>, delta<4>, enabled<4>)')
    if fine:s=s.replace('enabled<4>)','enabled<4>, pad<4>, lane_xor<4>)')
    old='\n'.join(f'MOV32I R{r}, 0x3f803f80;[7:7:{{}}:5:1]' for r in range(24,32))
    a=['LOP3.LUT R34, R6, 0xf, RZ, 0xc0, !PT;[7:7:{}:5:1]']
    for j in range(8):
        a += [f'MOV R{24+j}, RZ;[7:7:{{}}:5:1]']
        for kk,val in ((2*j,0x3f80),(2*j+1,0x3f800000)):
            a += [f'ISETP.EQ.AND P3, PT, R34, {kk}, PT;[7:7:{{}}:13:1]',
                  f'@P3 MOV32I R{24+j}, {val:#x};[7:7:{{}}:5:1]']
    assert s.count(old)==1;s=s.replace(old,'\n'.join(a))
    # Replace the eight-MMA body with ONE overwrite AS operation.
    begin=s.index('UTCHMMA.1CTA');end=s.index('UTCBAR.1CTA',begin)
    s=s[:begin]+('UTCHMMA.1CTA tmem[UR12], gdesc[{UR22,UR23}], tmem[UR10], '
                 'tmem[UR14], idesc[{UR15,UR16}], URZ, !UPT;[7:0:{}:1:1]\n'
                 'CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:1]\n')+s[end:]
    dispatch='ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]\n@P0 BRA #label(mma_done);[7:7:{}:5:0]\n'
    prep=['LDC R60, #param(delta);[2:7:{}:1:0]',
          'LDC R61, #param(enabled);[2:7:{}:1:0]']
    if fine:
        prep+=['LDC R62, #param(pad);[2:7:{}:1:0]',
               'LDC R63, #param(lane_xor);[2:7:{}:1:0]',
               'LOP3.LUT R35, R6, R63, RZ, 0x3c, !PT;[7:7:{2}:5:1]']
    prep+=[f'SHL R36, R{35 if fine else 6}, {perlane.bit_length()-1};[7:7:{{}}:5:1]',
          f'IADD3 R36, R36, {0x2000+off:#x}, RZ;[7:7:{{}}:5:1]']
    prep += [f'MOV32I R{r}, 0x40004000;[7:7:{{}}:5:1]' for r in range(24,28)]
    if tagged:
        # Every physical BF16 element gets its own exactly representable value.
        # R35 is the physical chunk index, including reversed lane assignment.
        for j in range(perlane//4):
            prep += [f'MOV32I R{24+j}, {0x40014000+j*0x20002:#x};[7:7:{{}}:5:1]',
                     f'IMAD R{24+j}, R35, {(perlane//2)*0x10001:#x}, R{24+j};[7:7:{{}}:5:1]']
    prep += ['ISETP.NE.AND P2, PT, R61, RZ, PT;[7:7:{2}:13:1]',
             'ISETP.EQ.AND P0, PT, R4, RZ, PT;[7:7:{}:13:1]',
             'CS2R {R30,R31}, SR_CLOCKLO;[7:7:{}:13:1]',
             'NOP;[7:7:{}:8:1]', 'NOP;[7:7:{}:8:1]',
             '@P0 IADD3 R30, R30, 0x1000, RZ;[7:7:{}:5:1]',
             '@P0 STS [RZ+0x700], R30;[7:1:{}:8:1]',
             'NOP;[7:7:{1}:8:1]','WARPSYNC.ALL;[7:7:{}:5:0]',
             'BAR.SYNC 0;[7:7:{}:5:1]',
             'LDS R30, [RZ+0x700];[0:7:{}:1:0]',
             'ISETP.EQ.AND P0, PT, R5, 0x1, PT;[7:7:{0}:13:1]',
             '@P0 BRA #label(modifier);[7:7:{}:5:0]',
             'ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]',
             '@P0 BRA #label(idle_control);[7:7:{}:5:0]']
    if ordering=='early':prep+=rendezvous
    assert s.count(dispatch)==1;s=s.replace(dispatch,'\n'.join(prep+clock_wait('producer_wait'))+'\n')
    old_end='@P1 STG.E.64.STRONG.GPU [{R2,R3}+8], {R18,R19};[7:1:{}:8:1]'
    assert s.count(old_end)==1
    s=s.replace(old_end,
                '@P1 STG.E.64.STRONG.GPU [{R2,R3}+16], {R18,R19};[7:1:{0}:8:1]\n'
                '@P1 STG.E.64.STRONG.GPU [{R2,R3}+8], {R20,R21};[7:1:{1}:8:1]')
    marker='#def_label(mma_done)'
    mut=(rendezvous if ordering=='late' else [])+[
         'BRA #label(mma_done);[7:7:{}:5:0]', '#def_label(idle_control)']
    if ordering!='race':mut+=rendezvous
    mut+=['BRA #label(mma_done);[7:7:{}:5:0]','#def_label(modifier)']
    if ordering=='late':mut+=rendezvous
    if fine:
        # Select before waiting on the future epoch. Each path has its own
        # poll, then a short straight-line delay, then the same branch to STS.
        # This fills the 57-cycle gaps without any indirect-branch CFG guesses.
        for pad in FINE_PADS[:-1]:
            mut += [f'ISETP.EQ.AND P3, PT, R62, {pad}, PT;[7:7:{{}}:13:1]',
                    f'@P3 BRA #label(fine_{pad});[7:7:{{}}:5:0]']
        mut += [f'BRA #label(fine_{FINE_PADS[-1]});[7:7:{{}}:5:0]']
        for pad in FINE_PADS:
            mut += [f'#def_label(fine_{pad})']+clock_wait(f'modifier_wait_{pad}',True)
            whole,rem=divmod(pad,8)
            mut += ['NOP;[7:7:{}:8:1]']*whole
            if rem:mut += [f'NOP;[7:7:{{}}:{rem}:1]']
            mut += ['BRA #label(modifier_store);[7:7:{}:5:0]']
        mut += ['#def_label(modifier_store)']
    else:
        mut+=clock_wait('modifier_wait',True)
    mut+=['CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]',
          f'@P2 STS{suffix} [R36], {values};[7:1:{{}}:1:0]',
          'FENCE.VIEW.ASYNC.S;[7:7:{1}:5:1]',
          'CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]']
    if ordering=='early':mut+=rendezvous
    mut+=[
          'ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]',
          '@P1 STG.E.64.STRONG.GPU [{R2,R3}+24], {R16,R17};[7:0:{}:8:1]',
          '@P1 STG.E.64.STRONG.GPU [{R2,R3}+32], {R18,R19};[7:1:{0}:8:1]',
          'NOP;[7:7:{0,1}:8:1]']
    for r,offset in ((30,40),(60,44),(31,48),(32,52),(34,56)):
        mut += [f'@P1 STG.E.STRONG.GPU [{{R2,R3}}+{offset}], R{r};[7:1:{{1}}:8:1]']
    mut += ['NOP;[7:7:{1}:8:1]']
    s=s.replace(marker,'\n'.join(mut)+'\n'+marker)
    marker='#def_label(mma_done)\nWARPSYNC.ALL;[7:7:{}:5:0]\nBAR.SYNC 0;[7:7:{}:5:1]'
    verify=['ISETP.NE.AND P0, PT, R5, 1, PT;[7:7:{}:13:1]',
            '@P0 BRA #label(b_verified);[7:7:{}:5:0]',
            f'LDS{suffix} {loaded}, [R36];[2:7:{{}}:1:0]',
            f'IMAD.WIDE.U32 {{R38,R39}}, R{35 if fine else 6}, {perlane}, {{R2,R3}};[7:7:{{}}:5:1]',
            f'STG.E{suffix}.STRONG.GPU [{{R38,R39}}+{OUT_SIZE:#x}], {loaded};[7:1:{{2}}:8:1]',
            'NOP;[7:7:{1}:8:1]','#def_label(b_verified)']
    assert s.count(marker)==1;s=s.replace(marker,marker+'\n'+'\n'.join(verify))
    return s

PATCHES=[(w,n,0) for w in (128,256,512) for n in (0,64,128,192)]+[(128,n,8) for n in (0,64,128,192)]

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-only',action='store_true');p.add_argument('--suite',choices=('smoke','coarse','fine','tagged'),default='coarse');p.add_argument('--reps',type=int,default=3);args=p.parse_args()
    if args.reps<1:p.error('reps must be positive')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    cases=0
    # Complete the entire control matrix before admitting any racing launch.
    fine=args.suite in ('fine','tagged');tagged=args.suite=='tagged'
    directions=(0,31) if fine else (0,)
    jobs=[(patch,mode,delta,enabled,0,lane_xor) for lane_xor in directions for patch in PATCHES
          for mode,delta,enabled in [('none',0,0),('early',-512,1),('late',1024,1)]]
    if args.suite=='coarse':
        jobs += [(patch,'race',d,1,0,0) for patch in PATCHES for d in range(-80,161,16)]
    if fine:
        jobs += [(patch,'race',d,1,pad,lane_xor) for lane_xor in directions
                 for patch in PATCHES for d in ((-64 if patch[1]==0 else 0,) if tagged else (-64,0)) for pad in FINE_PADS]
    built={};modules={}
    for (width,n,k),mode,delta,enabled,pad,lane_xor in jobs:
        ordering=mode if mode in ('early','late') else 'race'
        key=(width,n,k,ordering)
        if key not in built:
            src=source(width,n,k,ordering,fine=fine,tagged=tagged);diag=io.StringIO()
            with contextlib.redirect_stderr(diag):a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
            unexpected=set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}
            if unexpected:raise RuntimeError(diag.getvalue())
            built[key]=a
        a=built[key]
        if args.build_only:continue
        if key not in modules:
            mod=CudaModule(a.code)
            modules[key]=(mod,mod.devmem_alloc(SIZE))
        mod,ptr=modules[key]
        off=b_offset(k,n);mask=[off<=b_offset(kk,nn)<off+width for kk in range(16) for nn in range(256)]
        target=[struct.unpack('<f',struct.pack('<I',(0x4000+(b_offset(kk,nn)-off)//2)<<16))[0]
                if tagged and mask[kk*256+nn] else 2. for kk in range(16) for nn in range(256)]
        full_mask=mask*8;full_target=target*8
        cfg=dict(width=width,n=n,k=k,mode=mode,delta=delta,enabled=enabled,pad=pad,lane_xor=lane_xor,tagged=tagged)
        cases+=1;print(json.dumps(dict(event='launch',index=cases,**cfg)),flush=True)
        for rep in range(args.reps):
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            params=[ptr,struct.pack('<i',delta),struct.pack('<I',enabled)]
            if fine:params += [struct.pack('<I',pad),struct.pack('<I',lane_xor)]
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=params)
            mod.synchronize();raw=mod.device_read(ptr,SIZE);signal.alarm(0)
            pre,admit,done,ms,me=struct.unpack_from('<5Q',raw)
            vals=struct.unpack_from('<32768f',raw,64)
            final=struct.unpack_from(f'<{width//2}H',raw,OUT_SIZE)
            assert all(v==((0x4000+i if tagged else 0x4000) if enabled else 0x3f80)
                       for i,v in enumerate(final)),('writer readback',cfg)
            assert pre<admit<done and ms<me,('timestamps',cfg,(pre,admit,done,ms,me))
            epoch,delay,target,observed,diff=struct.unpack_from('<5I',raw,40)
            assert target==(epoch+512+delay)&0xffffffff,('clock target',cfg)
            assert diff==(observed-target)&0xffffffff,('stale clock operand',cfg,(epoch,delay,target,observed,diff))
            assert diff<0x80000000,('clock wait exited early',cfg)
            assert 0<((ms-epoch)&0xffffffff)<1000000,('invalid epoch',cfg,epoch,ms)
            outside=sum(v!=1. for v,inside in zip(vals,full_mask) if not inside)
            other=sum(v not in (1.,new) for v,new in zip(vals,full_target))
            replicas=sum(vals[i]!=vals[(i//256%16)*256+i%256] for i in range(len(vals)))
            control_errors=0
            if mode!='race':
                control_errors=sum(v!=(new if mode=='early' and inside else 1.)
                                   for v,new,inside in zip(vals,full_target,full_mask))
            result=dict(event='result',rep=rep,**cfg,pre=pre,admit=admit,done=done,mut_start=ms,mut_done=me,
                        wait_debug=struct.unpack_from('<5I',raw,40),
                        phase=ms-admit,writer_duration=me-ms,outside_errors=outside,other=other,replica_disagreements=replicas,
                        control_errors=control_errors,new_count=sum(v==new and inside for v,new,inside in zip(vals,full_target,full_mask)),
                        d_zlib_b64=base64.b64encode(zlib.compress(raw[64:OUT_SIZE],9)).decode())
            print(json.dumps(result),flush=True)
            assert not outside and not control_errors,('mapping/control failed',cfg,outside,control_errors)
            if mode=='early':assert me<pre,('early timing',cfg)
            if mode=='late':assert ms>done,('late timing',cfg)
    for mod,ptr in modules.values():mod.devmem_free(ptr)
    print(json.dumps(dict(event='complete',cases=cases,reps=args.reps,suite=args.suite,kernels=len(built),build_only=args.build_only)),flush=True)

if __name__=='__main__':main()
