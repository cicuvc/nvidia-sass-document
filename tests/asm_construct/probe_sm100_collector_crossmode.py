"""AS/WS collector interference and cross-mode reuse diagnostics."""
import sys, json, struct, signal, argparse, io, contextlib, re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from probe_sm100_ws_retention import source as retention
from probe_sm100_ws_throughput import random_b_data, OUT_SIZE
from assembler import assemble_kernel, CudaModule

def source(mode, poison=True, reuse=True):
    s=retention(slots=4,poison=poison,reuse=reuse)
    asop=('UTCHMMA.1CTA'+('.A_KEEP' if mode not in ('interfere_discard','interfere_tmem') else '')+
          ' gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, !UPT;[7:0:{}:1:1]')
    if mode=='interfere_empty':asop=''
    if mode=='interfere_ws':asop='UTCHMMA.1CTA.WS tmem[UR12], gdesc[{UR22,UR23}], tmem[UR10], tmem[UR14], idesc[{UR15,UR16}], URZ, !UPT;[7:0:{}:1:1]'
    if mode=='interfere_tmem':asop=asop.replace('gdesc[{UR20,UR21}]','tmem[UR12]')
    start=s.index('UTCHMMA.1CTA.WS')
    end=s.index('UTCBAR.1CTA',start)
    if mode=='direct':s=s[:start]+asop+'\n'+s[end:]
    elif mode.startswith('interfere'):
        pos=s.index('#!mbarrier_wait(UR18, 0)',end)+len('#!mbarrier_wait(UR18, 0)')
        s=s[:pos]+'\n'+asop+'\nUTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]\n#!mbarrier_wait(UR18, 1)'+s[pos:]
        pos=s.rindex('#!mbarrier_wait(UR18, 1)')
        s=s[:pos]+s[pos:].replace('#!mbarrier_wait(UR18, 1)','#!mbarrier_wait(UR18, 0)',1)
    elif mode=='as_control':
        # Fill and then query A collector itself, retaining random B for verification.
        s=s[:start]+asop+'\n'+s[end:]
        lines=s.splitlines()
        for i,l in enumerate(lines):
            if l.startswith('UTCHMMA.1CTA.WS'):lines[i]=asop.replace('.A_KEEP','.A_REUSE' if reuse else '')
        s='\n'.join(lines)+'\n'
        if poison:
            begin=s.index('STS.128',s.index('#!mbarrier_wait(UR18, 0)'))
            end=s.index('FENCE.VIEW.ASYNC.S',begin)
            stores='\n'.join(f'STS.128 [R12+{off:#x}], {{R24,R25,R26,R27}};[7:1:{{1}}:8:1]' for off in range(0x1000,0x2000,0x200))
            s=s[:begin]+stores+'\n'+s[end:]
    elif mode!='baseline':raise ValueError(mode)
    return s

def main():
    p=argparse.ArgumentParser();p.add_argument('--build-only',action='store_true');args=p.parse_args()
    data,sums=random_b_data();bits=struct.unpack('<16384H',data)
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('GPU timeout')))
    for mode in ('as_control','baseline','interfere_empty','interfere_ws','interfere_discard','interfere_fill','interfere_tmem','direct'):
      for poison,reuse in ((False,False),(False,True),(True,False),(True,True)):
        src=source(mode,poison,reuse);diag=io.StringIO()
        with contextlib.redirect_stderr(diag):a=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
        if set(re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diag.getvalue()))-{'sb_capacity'}:raise RuntimeError(diag.getvalue())
        if args.build_only:continue
        mod=CudaModule(a.code);out=mod.devmem_alloc(OUT_SIZE);inp=mod.devmem_alloc(len(data));mod.device_write(inp,data)
        for q in (range(1) if mode=='as_control' else range(4)):
          cfg=dict(mode=mode,poison=poison,reuse=reuse,query=q)
          print(json.dumps(dict(event='launch',**cfg)),flush=True)
          for rep in range(3):
            signal.alarm(30)
            mod.launch('ws_throughput',grid=(1,),block=(128,),args=[out,inp,struct.pack('<I',q)]);mod.synchronize()
            raw=mod.device_read(out,OUT_SIZE);signal.alarm(0)
            assert struct.unpack_from('<I',raw,32)[0]==q
            vals=struct.unpack('<32768f',raw[64:]);counts=dict(old=0,zero=0,one=0,other=0);examples=[]
            for row in range(128):
              for n in range(256):
                k=row%16;off=q*4096+(n//8)*128+(k//8)*64+(n%8)*8+k%8
                want=struct.unpack('<f',struct.pack('<I',bits[off]<<16))[0]
                if mode=='as_control':want=sum(struct.unpack('<f',struct.pack('<I',bits[(n//8)*128+(kk//8)*64+(n%8)*8+kk%8]<<16))[0] for kk in range(16))
                v=vals[row*256+n];key='old' if v==want else 'zero' if v==0 else 'one' if v==1 else 'other';counts[key]+=1
                if key=='other' and len(examples)<4:examples.append([row,n,v,want])
            print(json.dumps(dict(event='result',rep=rep,counts=counts,examples=examples,**cfg)),flush=True)
            if (mode=='as_control' and not poison) or (not reuse and not poison):assert counts['old']==32768
            if not reuse and poison:assert counts['zero']==32768
        mod.devmem_free(out);mod.devmem_free(inp)
    print(json.dumps(dict(event='complete')),flush=True)
if __name__=='__main__':main()
