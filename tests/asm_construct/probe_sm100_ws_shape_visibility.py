"""Matched WS M32/M64/M128 timing: vary only the M descriptor immediate."""
import functools,itertools
from probe_sm100_ws32_tmem_cross_partition import source as tagged_base
from probe_sm100_tmem_cross_partition import inspect as inspect_base,main,FINE_PADS,SKEWS
from probe_sm100_as_tmem_snapshot import replace_once

SHAPES=(32,64,128)
COLUMNS=(0,1,16,31,32,33,47,62,63)

def source(experiment='ws64',ordering='race'):
    m=int(experiment.removeprefix('ws'));assert m in SHAPES
    s=tagged_base('ws32',ordering)
    old=(2<<24)|(32<<17)|0x490;new=((m//16)<<24)|(32<<17)|0x490
    return replace_once(s,f'UMOV UR15, {old:#x};[7:7:{{}}:5:1]',f'UMOV UR15, {new:#x};[7:7:{{}}:5:1]')

def configurations(suite):
    if suite=='match':
        # Hypothesis-driven timing match: the sampled post-issue frontiers
        # suggest M64 c72/73 and M128 c76/77 may coincide with M32 c32/33.
        # These are predictions to test, not assumptions used by validation.
        jobs=[]
        for mode in ('none','early','late','race'):
            for m in SHAPES:
                for column,skew in itertools.product({32:(32,33),64:(72,73),128:(76,77)}[m],SKEWS[:3]):
                    offsets=[skew[0],skew[1],0,skew[2]]
                    jobs.append(dict(experiment=f'ws{m}',m=m,n=256,producer=2,column=column,mode=mode,
                                     delta={'none':0,'early':-512,'late':1024,'race':0}[mode],
                                     enabled=int(mode!='none'),pad=28,skews=offsets))
        return jobs
    if suite=='relative':
        jobs=[]
        for mode in ('none','early','late','race'):
            for m in SHAPES:
                for producer,column,skew in itertools.product(range(4),(m-1,m,m+1),SKEWS):
                    offsets=[0]*4
                    for w,d in zip([w for w in range(4) if w!=producer],skew):offsets[w]=d
                    delays=(-64,0,64,128) if mode=='race' else ({'none':0,'early':-512,'late':1024}[mode],)
                    for delta,pad in itertools.product(delays,FINE_PADS if mode=='race' else (0,)):
                        jobs.append(dict(experiment=f'ws{m}',m=m,n=256,producer=producer,column=column,mode=mode,
                                         delta=delta,enabled=int(mode!='none'),pad=pad,skews=offsets))
        return jobs
    cols=(0,32,63) if suite=='smoke' else (31,32,33) if suite=='focus' else COLUMNS
    producers=(1,2) if suite=='focus' else range(4)
    jobs=[]
    for mode in ('none','early','late','race'):
        if suite=='smoke' and mode=='race':continue
        for producer,column,skew in itertools.product(producers,cols,SKEWS):
            offsets=[0]*4
            for w,d in zip([w for w in range(4) if w!=producer],skew):offsets[w]=d
            delays=((0,) if suite=='focus' else (-64,0,64)) if mode=='race' else ({'none':0,'early':-512,'late':1024}[mode],)
            for delta,pad,m in itertools.product(delays,FINE_PADS if mode=='race' else (0,),SHAPES):
                jobs.append(dict(experiment=f'ws{m}',m=m,n=256,producer=producer,column=column,mode=mode,
                                 delta=delta,enabled=int(mode!='none'),pad=pad,skews=offsets))
    if suite=='blocked':
        # Identical case matrix and device code; only host launch order differs.
        # Keep all controls before races, then avoid switching shape modules
        # between adjacent racing launches.
        order={'none':0,'early':1,'late':2,'race':3}
        jobs.sort(key=lambda c:(order[c['mode']],c['m']))
    return jobs

def logical_column(m,warp,c):return (warp//(m//32))*(m*2)+c

@functools.lru_cache(maxsize=6)
def reference(m,enabled):
    return tuple(float(logical_column(m,i//8192,i%256)//64+1) if enabled and i%256<m*2 else -float(i%256+1)
                 for i in range(32768))

def inspect(raw,cfg):
    m=cfg['m'];assert m in SHAPES and cfg['experiment']==f'ws{m}' and cfg['n']==256 and 0<=cfg['column']<m*2
    values=[float(logical_column(m,w,cfg['column'])//64+1) for w in range(4)]
    result=inspect_base(raw,cfg,final_reference=reference(m,cfg['enabled']),new_values=values)
    for r in result['records']:
        r.update(physical_column=cfg['column'],logical_column=logical_column(m,r['warp'],cfg['column']),
                 logical_row_base=32*(r['warp']%(m//32)),new_value=values[r['warp']])
    return result

if __name__=='__main__':main(source_factory=source,config_factory=configurations,inspector=inspect,suites=('smoke','scan','focus','blocked','relative','match'))
