"""Destructive source-poison retention diagnostic; not a PTX correctness test."""
import sys, json, struct, signal, argparse, io, contextlib, re, random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from probe_sm100_ws_throughput import source as base, random_b_data, OUT_SIZE
from assembler import assemble_kernel, CudaModule

def source(slots=1, query=0, poison=False, reuse=True):
    s=base(m=128,n=256,count=8,mode='reuse',atmem=True,pattern='0123',pattern_addresses=True,random_b=True)
    # TMEM row = thread row. Repeat I16 eight times, exposing every K element.
    old='\n'.join(f'MOV32I R{r}, 0x3f803f80;[7:7:{{}}:5:1]' for r in range(24,32))
    a=['LOP3.LUT R34, R6, 0xf, RZ, 0xc0, !PT;[7:7:{}:5:1]']
    for j in range(8):
        a += [f'MOV R{24+j}, RZ;[7:7:{{}}:5:1]']
        for k,val in ((2*j,0x3f80),(2*j+1,0x3f800000)):
            a += [f'ISETP.EQ.AND P3, PT, R34, {k}, PT;[7:7:{{}}:13:1]',f'@P3 MOV32I R{24+j}, {val:#x};[7:7:{{}}:5:1]']
    assert old in s
    s=s.replace(old,'\n'.join(a))
    begin=s.index('UTCHMMA.1CTA.WS')
    end=s.index('UTCBAR.1CTA',begin)
    def mma(b,mods):
        buf=f'.BUFFER{b}' if b else ''
        return f'UTCHMMA.1CTA.WS{buf}{mods} tmem[UR12], gdesc[{{UR{22+2*b},UR{23+2*b}}}], tmem[UR10], tmem[UR14], idesc[{{UR15,UR16}}], URZ, !UPT;[7:0:{{}}:1:1]'
    seq=[mma(b,'.B_KEEP') for b in range(slots)]
    seq += ['UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]','#!mbarrier_wait(UR18, 0)']
    if poison:
        seq += ['NOP;[7:7:{0,1,2}:8:1]']
        seq += [f'MOV R{r}, RZ;[7:7:{{}}:5:1]' for r in range(24,28)]
        # Only warp zero participates: its lanes cover 512 bytes per stripe.
        seq += [f'STS.128 [R12+{off:#x}], {{R24,R25,R26,R27}};[7:1:{{1}}:8:1]' for off in range(0x2000,0xa000,0x200)]
        seq += ['FENCE.VIEW.ASYNC.S;[7:7:{1}:5:1]','WARPSYNC.ALL;[7:7:{}:5:0]']
    seq += ['NOP;[7:7:{}:8:1]']*32
    # Selection is loaded only after erasure; all queries share identical SASS.
    seq += ['LDC R35, #param(query);[2:7:{}:1:0]', 'NOP;[7:7:{2}:8:1]']
    seq += ['NOP;[7:7:{}:8:1]']*4
    seq += ['STG.E.STRONG.GPU [{R2,R3}+32], R35;[7:1:{}:8:1]', 'NOP;[7:7:{1}:8:1]']
    for b in range(slots):
        seq += [f'ISETP.NE.AND P3, PT, R35, {b}, PT;[7:7:{{}}:13:1]',f'@P3 BRA #label(skip_{b});[7:7:{{}}:5:0]',mma(b,'.B_REUSE' if reuse else ''),f'#def_label(skip_{b})']
    s=s[:begin]+'\n'.join(seq)+'\n'+s[end:]
    # Second completion uses the next phase of the same mbarrier.
    pos=s.rindex('#!mbarrier_wait(UR18, 0)')
    s=s[:pos]+s[pos:].replace('#!mbarrier_wait(UR18, 0)','#!mbarrier_wait(UR18, 1)',1)
    return s.replace('inputs<8>)','inputs<8>, query<4>)')

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-only',action='store_true');args=p.parse_args()
    rng=random.Random(20261118)
    bits=[(rng.randrange(2)<<15)|(rng.randrange(1,255)<<7)|rng.randrange(128) for _ in range(16384)]
    data=struct.pack('<16384H',*bits)
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    for slots in (1,4):
      for q in range(slots):
       for poison,reuse in ((False,False),(False,True),(True,False),(True,True)):
        cfg=dict(slots=slots,query=q,poison=poison,reuse=reuse)
        src=source(**cfg)
        diag=io.StringIO()
        with contextlib.redirect_stderr(diag):
            a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
        if set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}:raise RuntimeError(diag.getvalue())
        if args.build_only: continue
        print(json.dumps(dict(event='launch',**cfg)),flush=True)
        mod=CudaModule(a.code);out=mod.devmem_alloc(OUT_SIZE);inp=mod.devmem_alloc(len(data)+4);mod.device_write(inp,data+struct.pack('<I',q))
        for rep in range(3):
            signal.alarm(30)
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=[out,inp,struct.pack('<I',q)]);mod.synchronize()
            raw=mod.device_read(out,OUT_SIZE);vals=struct.unpack('<32768f',raw[64:]);signal.alarm(0)
            selector=struct.unpack_from('<I',raw,32)[0]
            old=zero=other=0
            for row in range(128):
                k=row%16
                for n in range(256):
                    off=q*4096+(n//8)*128+(k//8)*64+(n%8)*8+k%8
                    want=struct.unpack('<f',struct.pack('<I',bits[off]<<16))[0]
                    v=vals[row*256+n]
                    if v==want:old+=1
                    elif v==0:zero+=1
                    else:other+=1
            print(json.dumps(dict(event='result',selector=selector,rep=rep,old=old,zero=zero,other=other,**cfg)),flush=True)
            if not poison and old!=32768:raise RuntimeError('identity/control failed')
            if poison and not reuse and zero!=32768:raise RuntimeError('poison control failed')
        mod.devmem_free(out);mod.devmem_free(inp)
    print(json.dumps(dict(event='complete')),flush=True)
if __name__=='__main__':main()
