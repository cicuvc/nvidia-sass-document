"""AS collector retention across completion and shared/TMEM source erasure."""
import sys,json,struct,signal,argparse,io,contextlib,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from probe_sm100_collector_crossmode import source as cross
from probe_sm100_ws_throughput import random_b_data,OUT_SIZE
from assembler import assemble_kernel,CudaModule

def source(atmem=True,poison=True,reuse=True):
    s=cross('as_control',poison=False,reuse=reuse)
    if atmem:s=s.replace('gdesc[{UR20,UR21}]','tmem[UR12]')
    # Nonissuer warps join after the issuer's first commit/wait, so every
    # 32-row TMEM partition is overwritten by its owning warp.
    old='@P0 BRA #label(mma_done);[7:7:{}:5:0]'
    assert s.count(old)==1
    s=s.replace(old,'@P0 BRA #label(clear_a);[7:7:{}:5:0]')
    block=['#def_label(clear_a)','WARPSYNC.ALL;[7:7:{}:5:0]','BAR.SYNC 0;[7:7:{}:5:1]']
    if poison:
        block += ['NOP;[7:7:{0,1,2}:8:1]']
        block += [f'MOV R{r}, RZ;[7:7:{{}}:5:1]' for r in range(24,32)]
        if atmem:block += ['STTM.x8 tmem[UR12], {R24,R25,R26,R27,R28,R29,R30,R31};[7:7:{}:1:0]']
        else:block += [f'STS.128 [R12+{off:#x}], {{R24,R25,R26,R27}};[7:1:{{1}}:8:1]' for off in (0x1000,0x1800)]
    if atmem:block += ['FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]','NOP;[7:7:{0}:8:1]']
    else:block += ['FENCE.VIEW.ASYNC.S;[7:7:{1}:5:1]']
    block += ['WARPSYNC.ALL;[7:7:{}:5:0]','BAR.SYNC 0;[7:7:{}:5:1]',
              'ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]',old]
    needle='#!mbarrier_wait(UR18, 0)';pos=s.index(needle)+len(needle)
    return s[:pos]+'\n'+'\n'.join(block)+s[pos:]

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-only',action='store_true');args=p.parse_args()
    data,_=random_b_data();bits=struct.unpack('<16384H',data)
    b=[[struct.unpack('<f',struct.pack('<I',bits[(n//8)*128+(k//8)*64+(n%8)*8+k%8]<<16))[0] for n in range(256)] for k in range(16)]
    sums=[sum(b[k][n] for k in range(16)) for n in range(256)]
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    for atmem in (False,True):
      for poison in (False,True):
       for reuse in (False,True):
        cfg=dict(atmem=atmem,poison=poison,reuse=reuse);src=source(**cfg);diag=io.StringIO()
        with contextlib.redirect_stderr(diag):a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
        if set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}:raise RuntimeError(diag.getvalue())
        if args.build_only:continue
        print(json.dumps(dict(event='launch',**cfg)),flush=True)
        mod=CudaModule(a.code);out=mod.devmem_alloc(OUT_SIZE);inp=mod.devmem_alloc(len(data));mod.device_write(inp,data)
        for rep in range(5):
            signal.alarm(30);mod.launch('ws_throughput',grid=(1,),block=(128,),args=[out,inp,struct.pack('<I',0)]);mod.synchronize()
            raw=mod.device_read(out,OUT_SIZE);signal.alarm(0)
            vals=struct.unpack('<32768f',raw[64:]);old=zero=other=0
            chunks=[]
            for w in range(4):
                cnt=dict(old=0,zero=0,other=0)
                for row in range(w*32,(w+1)*32):
                    for n in range(256):
                        v=vals[row*256+n];want=b[row%16][n] if atmem else sums[n]
                        key='old' if v==want else 'zero' if v==0 else 'other';cnt[key]+=1
                chunks.append(cnt)
            totals={k:sum(c[k] for c in chunks) for k in chunks[0]}
            print(json.dumps(dict(event='result',rep=rep,counts=totals,chunks=chunks,**cfg)),flush=True)
            if not poison:assert totals['old']==32768
            if poison and not reuse:assert totals['zero']==32768
        mod.devmem_free(out);mod.devmem_free(inp)
    print(json.dumps(dict(event='complete')),flush=True)
if __name__=='__main__':main()
