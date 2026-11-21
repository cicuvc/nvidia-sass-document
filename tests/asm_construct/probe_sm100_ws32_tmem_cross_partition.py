"""WS M32N256: compare local-column visibility across four N/4 chunks.

Chunk w represents logical n=64*w+c, not the same logical column in every
warp. B's four N64 bands have BF16 values 1,2,3,4 to check that mapping.
"""
import functools,itertools
from probe_sm100_tmem_cross_partition import source as base,inspect as inspect_base,main,FINE_PADS,SKEWS
from probe_sm100_as_tmem_snapshot import replace_once

COLUMNS=(0,1,16,31,32,47,62,63)
DELTAS=(-64,0,64,128)

def source(experiment='ws32',ordering='race'):
    assert experiment=='ws32'
    s=base('ws',ordering)
    old=((128//16)<<24)|((256//8)<<17)|0x490
    new=((32//16)<<24)|((256//8)<<17)|0x490
    s=replace_once(s,f'UMOV UR15, {old:#x};[7:7:{{}}:5:1]',f'UMOV UR15, {new:#x};[7:7:{{}}:5:1]')
    # No-swizzle K-major B: each N64 band occupies one 0x800-byte stripe.
    for w,bits in enumerate((0x3f803f80,0x40004000,0x40404040,0x40804080)):
        anchor=f'STS.128 [R12+{0x2000+w*0x800:#x}], {{R24,R25,R26,R27}};[7:1:{{1}}:8:1]'
        prep=['NOP;[7:7:{1}:8:1]']+[f'MOV32I R{r}, {bits:#x};[7:7:{{}}:5:1]' for r in range(24,28)]
        s=replace_once(s,anchor,'\n'.join(prep+[anchor]))
    return s

def configurations(suite):
    cols=(0,63) if suite=='smoke' else (31,32,33) if suite=='focus' else COLUMNS
    producers=(1,2) if suite=='focus' else range(4)
    jobs=[]
    for mode in ('none','early','late','race'):
        if suite=='smoke' and mode=='race':continue
        for producer,column,skew in itertools.product(producers,cols,SKEWS):
            offsets=[0]*4
            for w,d in zip([w for w in range(4) if w!=producer],skew):offsets[w]=d
            delays=((0,) if suite=='focus' else DELTAS) if mode=='race' else ({'none':0,'early':-512,'late':1024}[mode],)
            for delta,pad in itertools.product(delays,FINE_PADS if mode=='race' else (0,)):
                jobs.append(dict(experiment='ws32',m=32,n=256,producer=producer,column=column,mode=mode,
                                 delta=delta,enabled=int(mode!='none'),pad=pad,skews=offsets))
    return jobs

@functools.lru_cache(maxsize=2)
def reference(enabled):
    return tuple(float(i//(32*256)+1) if enabled and i%256<64 else -float(i%256+1) for i in range(32768))

def inspect(raw,cfg):
    assert cfg['experiment']=='ws32' and cfg['m']==32 and cfg['n']==256 and 0<=cfg['column']<64
    result=inspect_base(raw,cfg,final_reference=reference(cfg['enabled']),new_values=(1.,2.,3.,4.))
    for r in result['records']:
        r.update(physical_column=cfg['column'],logical_column=64*r['warp']+cfg['column'],new_value=float(r['warp']+1))
    return result

if __name__=='__main__':main(source_factory=source,config_factory=configurations,inspector=inspect,suites=('smoke','scan','focus'))
