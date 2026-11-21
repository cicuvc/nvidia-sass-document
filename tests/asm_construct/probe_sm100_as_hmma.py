"""Does legacy HMMA interfere with AS UTCHMMA A reuse on B200?"""
import argparse
import contextlib
import io
import itertools
import json
from pathlib import Path
import re
import signal
import statistics
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble_kernel
from probe_sm100_ws_throughput import source as base, OUT_SIZE, group
from probe_sm100_as_isolation import attributes

HMMA_OFF = OUT_SIZE + 128
SIZE = HMMA_OFF + 4 * 512


def hmma(j=0, enabled=True):
    return (('' if enabled else '@!PT ') +
            f'HMMA.16816.F32.BF16 {group(40+4*j,4)}, '
            f'{group(64,4)}, {group(68,2)}, {group(72,4)};[7:7:{{}}:1:0]')


def init_regs():
    # Distinct from AS's A=B=1. Packed BF16 A=2, B=3, FP32 C=5 -> D=101.
    return [f'MOV32I R{r}, {v:#x};[7:7:{{}}:5:1]'
            for regs,v in ((range(40,56),0), (range(64,68),0x40004000),
                           (range(68,70),0x40404040), (range(72,76),0x40a00000))
            for r in regs]


def smoke_source(enabled):
    lines = ['#fn hmma_smoke(out<8>) {', '#pragma MAXREG_COUNT(112)',
             'LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]',
             'S2R R4, SR_TID.X;[1:7:{}:2:0]',
             'IMAD.WIDE.U32 {R8,R9}, R4, 0x10, {R2,R3};[7:7:{0,1}:5:1]']
    lines += init_regs() + [hmma(enabled=enabled)]
    lines += ['NOP;[7:7:{}:8:1]'] * 16
    lines += ['STG.E.128.STRONG.GPU [{R8,R9}], {R40,R41,R42,R43};[7:0:{}:8:1]',
              'NOP;[7:7:{0}:8:1]', 'EXIT;[7:7:{}:5:0]', '}']
    return '\n'.join(lines)+'\n'


def source(count, reuse, meter, kind, amount):
    s = base(m=128,n=64,count=count,mode='reuse' if reuse else 'discard',
             ws=False,lds_iters=2048 if meter else 0)
    out=[]; seen=0
    for line in s.splitlines():
        if line == '#def_label(timer_begin)':
            out += init_regs()
        if line.startswith('UTCHMMA.'):
            seen += 1
            if reuse and '.A_REUSE' in line and '.A_KEEP' not in line:
                line=line.replace('.A_REUSE','.A_REUSE.A_KEEP')
            out.append(line)
            if seen<count:
                if kind in ('hmma','off'):
                    out += [hmma(j,kind=='hmma') for j in range(amount)]
                elif kind=='slot':
                    out += ['NOP;[7:7:{}:1:0]']*amount
                elif kind=='nop8':
                    out += ['NOP;[7:7:{}:8:1]']*amount
        else:
            out.append(line)
    assert seen==count
    # Save HMMA outputs only after ALL LDS meters finish, before scalar TMEM
    # readback overwrites R40. No observer instructions enter the timed region.
    pos=out.index('#def_label(mma_done)')
    pos=out.index('BAR.SYNC 0;[7:7:{}:5:1]',pos)+1
    save=['ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]',
          '@P0 BRA #label(hmma_saved);[7:7:{}:5:0]']
    save += ['NOP;[7:7:{}:8:1]']*16
    save += ['IMAD.WIDE.U32 {R56,R57}, R6, 0x10, {R2,R3};[7:7:{}:5:1]']
    for j in range(4):
        save += [f'STG.E.128.STRONG.GPU [{{R56,R57}}+{HMMA_OFF+j*512:#x}], '
                 f'{group(40+4*j,4)};[7:1:{{1}}:8:1]']
    save += ['NOP;[7:7:{1}:8:1]', '#def_label(hmma_saved)']
    out[pos:pos]=save
    return '\n'.join(out)+'\n'


def build(src):
    diag=io.StringIO()
    with contextlib.redirect_stderr(diag):
        a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
    unexpected=set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}
    if unexpected: raise RuntimeError(diag.getvalue())
    return a


POINTS=[('slot',0),('slot',1),('off',1),('hmma',1),('off',2),('hmma',2),
        ('off',4),('hmma',4),('nop8',4),('nop8',6),('nop8',8),('nop8',12)]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--build-only',action='store_true')
    args=p.parse_args()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    for enabled in (False,True):
        a=build(smoke_source(enabled))
        if args.build_only: continue
        print(json.dumps(dict(event='smoke_launch',enabled=enabled)),flush=True)
        mod=CudaModule(a.code); ptr=mod.devmem_alloc(512)
        for rep in range(3):
            mod.devmem_set(ptr,0,128);signal.alarm(30)
            mod.launch('hmma_smoke',grid=(1,),block=(32,),args=[ptr]);mod.synchronize()
            vals=struct.unpack('<128f',mod.device_read(ptr,512));signal.alarm(0)
            assert all(v==(101. if enabled else 0.) for v in vals),(enabled,vals)
        mod.devmem_free(ptr)
        print(json.dumps(dict(event='smoke_result',enabled=enabled,value=vals[0],errors=0)),flush=True)
    index=0
    for kind,amount in POINTS:
      for meter,reuse,count in itertools.product((False,True),(False,True),(64,256)):
        cfg=dict(count=count,reuse=reuse,meter=meter,kind=kind,amount=amount)
        # Build-only exercises every control shape at short count; full kernels
        # are independently checked by build() immediately before GPU execution.
        a=build(source(**dict(cfg,count=8 if args.build_only else count)))
        index+=1
        if args.build_only: continue
        print(json.dumps(dict(event='launch',index=index,**cfg)),flush=True)
        mod=CudaModule(a.code);dynamic,resources=attributes(mod,True)
        ptr=mod.devmem_alloc(SIZE);samples=[];ms=[];diagnostics=[]
        for rep in range(6):
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=[ptr],shared_mem=dynamic)
            mod.synchronize();raw=mod.device_read(ptr,SIZE);signal.alarm(0)
            hv=struct.unpack_from('<512f',raw,HMMA_OFF)
            hbad=[(i,v) for i,v in enumerate(hv) if v!=(101. if kind=='hmma' and i//128<amount else 0.)]
            assert not hbad,('HMMA output mismatch',cfg,hbad[:12])
            vals=struct.unpack_from('<32768f',raw,64)
            bad=[(i//256,i%256,v) for i,v in enumerate(vals) if v!=(16.*count if i%256<64 else 0.)]
            # A changed AS result could be evidence of clobber, so preserve it
            # instead of discarding the entire probe. Such rows are NOT accepted
            # as ordinary timing evidence by the analyzer.
            diagnostics.append(dict(rep=rep,as_errors=len(bad),first_bad=bad[:16]))
            start,end=struct.unpack_from('<QQ',raw);assert end>start
            if meter:
                times=[struct.unpack_from('<QQ',raw,16*w) for w in (1,2,3)]
                checks=[struct.unpack_from('<II',raw,OUT_SIZE+8*w) for w in (1,2,3)]
                assert all(c==((2048*12*0x3f803f80)&0xffffffff,(48*0x3f803f80)&0xffffffff) for c in checks)
                if rep:ms.append(dict(begin=[t[0] for t in times],end=[t[1] for t in times],
                                      span=max(t[1] for t in times)-min(t[0] for t in times),mma_begin=start,mma_end=end))
            if rep:samples.append(end-start)
        mod.devmem_free(ptr)
        print(json.dumps(dict(event='result',**cfg,resources=resources,cycles=samples,
                              median=statistics.median(samples),lds=ms,
                              errors=sum(x['as_errors'] for x in diagnostics),diagnostics=diagnostics)),flush=True)
    print(json.dumps(dict(event='complete',cases=index,reps=5)),flush=True)


if __name__=='__main__': main()
