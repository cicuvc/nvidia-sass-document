"""Continuous AS issuer plus a separate legacy-HMMA warp and two LDS meters."""
import argparse
import base64
import itertools
import json
import signal
import statistics
import struct
import zlib

from probe_sm100_as_hmma import base, build, init_regs, hmma, group, attributes, CudaModule, OUT_SIZE, HMMA_OFF

TIME_OFF=HMMA_OFF+2048
WORKER_ITERS=1024
TRACE_OFF=TIME_OFF+16
SIZE=TRACE_OFF+8*WORKER_ITERS


def source(count,reuse,enabled,amount):
    s=base(m=128,n=64,count=count,mode='reuse' if reuse else 'discard',ws=False,lds_iters=2048)
    s=s.replace('.A_REUSE ','.A_REUSE.A_KEEP ')
    marker='#def_label(mma_done)\nWARPSYNC.ALL;[7:7:{}:5:0]\n'
    assert s.count(marker)==1
    worker=['ISETP.NE.AND P0, PT, R5, 0x1, PT;[7:7:{}:13:1]',
            '@P0 BRA #label(worker_done);[7:7:{}:5:0]']
    worker+=init_regs()
    worker += [f'IADD3 R58, P5, R2, {TRACE_OFF:#x}, RZ;[7:7:{{}}:5:1]',
               'IADD3.X R59, R3, RZ, RZ, P5, !PT;[7:7:{}:5:1]',
               'ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]']
    worker+=['CS2R {R20,R21}, SR_CLOCKLO;[7:7:{}:5:1]',
             f'MOV32I R32, {WORKER_ITERS};[7:7:{{}}:5:1]', '#def_label(worker_loop)']
    worker += [hmma(j,enabled) for j in range(amount)]
    # Conservative coupled-result/WAW spacing, common to active/off controls.
    worker += ['NOP;[7:7:{}:8:1]']*16
    # Timestamp every completed burst, so interval overlap alone cannot hide a
    # worker that was starved until AS finished. Identical tracing in controls.
    worker += ['CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:1]',
               '@P1 STG.E.64.STRONG.GPU [{R58,R59}], {R22,R23};[7:1:{}:8:1]',
               'IADD3 R58, P5, R58, 0x8, RZ;[7:7:{1}:5:1]',
               'IADD3.X R59, R59, RZ, RZ, P5, !PT;[7:7:{}:5:1]',
               'IADD3 R32, R32, -0x1, RZ;[7:7:{}:5:1]',
               'ISETP.NE.AND P0, PT, R32, RZ, PT;[7:7:{}:13:1]',
               '@P0 BRA #label(worker_loop);[7:7:{}:5:0]',
               'CS2R {R22,R23}, SR_CLOCKLO;[7:7:{}:5:1]',
               'IMAD.WIDE.U32 {R56,R57}, R6, 0x10, {R2,R3};[7:7:{}:5:1]']
    for j in range(4):
        worker += [f'STG.E.128.STRONG.GPU [{{R56,R57}}+{HMMA_OFF+j*512:#x}], '
                   f'{group(40+4*j,4)};[7:1:{{1}}:8:1]']
    worker += ['ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]',
               f'@P1 STG.E.64.STRONG.GPU [{{R2,R3}}+{TIME_OFF:#x}], {{R20,R21}};[7:1:{{1}}:8:1]',
               f'@P1 STG.E.64.STRONG.GPU [{{R2,R3}}+{TIME_OFF+8:#x}], {{R22,R23}};[7:1:{{1}}:8:1]',
               'NOP;[7:7:{1}:8:1]', 'BRA #label(meter_done);[7:7:{}:5:0]',
               '#def_label(worker_done)']
    return s.replace(marker,marker+'\n'.join(worker)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--build-only',action='store_true');args=p.parse_args()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    index=0
    for amount,enabled in ((0,False),(1,False),(1,True),(4,False),(4,True)):
      for reuse,count in itertools.product((False,True),(128,512)):
        cfg=dict(count=count,reuse=reuse,enabled=enabled,amount=amount)
        a=build(source(**dict(cfg,count=8 if args.build_only else count)));index+=1
        if args.build_only:continue
        print(json.dumps(dict(event='launch',index=index,**cfg)),flush=True)
        mod=CudaModule(a.code);dynamic,resources=attributes(mod,True);ptr=mod.devmem_alloc(SIZE)
        samples=[];ms=[];diagnostics=[]
        for rep in range(6):
            mod.devmem_set(ptr,0,SIZE//4);signal.alarm(30)
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=[ptr],shared_mem=dynamic)
            mod.synchronize();raw=mod.device_read(ptr,SIZE);signal.alarm(0)
            hv=struct.unpack_from('<512f',raw,HMMA_OFF)
            hbad=[(i,v) for i,v in enumerate(hv) if v!=(101. if enabled and i//128<amount else 0.)]
            assert not hbad,('HMMA worker output mismatch',cfg,hbad[:12])
            vals=struct.unpack_from('<32768f',raw,64)
            bad=[(i//256,i%256,v) for i,v in enumerate(vals) if v!=(16.*count if i%256<64 else 0.)]
            diagnostics.append(dict(rep=rep,as_errors=len(bad),first_bad=bad[:16]))
            start,end=struct.unpack_from('<QQ',raw);assert end>start
            times=[struct.unpack_from('<QQ',raw,16*w) for w in (2,3)]
            checks=[struct.unpack_from('<II',raw,OUT_SIZE+8*w) for w in (2,3)]
            assert all(c==((2048*12*0x3f803f80)&0xffffffff,(48*0x3f803f80)&0xffffffff) for c in checks)
            wb,we=struct.unpack_from('<QQ',raw,TIME_OFF);assert we>wb
            trace=list(struct.unpack_from(f'<{WORKER_ITERS}Q',raw,TRACE_OFF))
            assert wb<trace[0] and all(a<b for a,b in zip(trace,trace[1:])) and trace[-1]<we
            in_window=sum(start<=t<=end for t in trace)
            # Lossless host-side compression; GPU instructions are unchanged.
            # Avoid Modal's 64-KiB log-line truncation and oversized return blobs.
            packed=struct.pack(f'<{WORKER_ITERS-1}I',*(b-a for a,b in zip(trace,trace[1:])))
            trace_deltas=base64.b64encode(zlib.compress(packed)).decode('ascii')
            if rep:
                samples.append(end-start)
                ms.append(dict(begin=[t[0] for t in times],end=[t[1] for t in times],
                               span=max(t[1] for t in times)-min(t[0] for t in times),
                               mma_begin=start,mma_end=end,worker_begin=wb,worker_end=we,
                               worker_iters=WORKER_ITERS,worker_bursts_in_mma=in_window,
                               worker_trace_first=trace[0],worker_trace_deltas_zlib_b64=trace_deltas))
        mod.devmem_free(ptr)
        print(json.dumps(dict(event='worker_result',**cfg,resources=resources,cycles=samples,
                              median=statistics.median(samples),lds=ms,
                              errors=sum(d['as_errors'] for d in diagnostics),diagnostics=diagnostics)),flush=True)
    print(json.dumps(dict(event='complete',cases=index,reps=5)),flush=True)


if __name__=='__main__':main()
