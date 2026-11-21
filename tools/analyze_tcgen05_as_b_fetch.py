"""Inspect complete K/N old/new masks and repeated-row agreement."""
import argparse,base64,collections,json,struct,zlib
from pathlib import Path

def decode(x):
    raw=zlib.decompress(base64.b64decode(x['d_zlib_b64']))
    assert len(raw)==128*256*4
    return struct.unpack('<32768f',raw)

def runs(indices):
    if not indices:return '-'
    out=[];lo=last=indices[0]
    for i in indices[1:]:
        if i!=last+1:out.append(str(lo) if lo==last else f'{lo}-{last}');lo=i
        last=i
    out.append(str(lo) if lo==last else f'{lo}-{last}')
    return ','.join(out)

def plot_phases(by,path):
    """Optional publication/export artifact; the text analyzer stays stdlib-only."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(4,4,figsize=(12,9),sharex=True,sharey=True)
    for row,(width,k) in enumerate(((128,0),(128,8),(256,0),(512,0))):
        for col,n in enumerate((0,64,128,192)):
            ax=axes[row,col]
            for direction,color,marker in ((0,'#1768ac','o'),(31,'#e87500','x')):
                rows=by.get((width,n,k,direction),[])
                points=sorted({(x['phase'],x['new_count']/(width*4)) for x in rows})
                if points:
                    ax.scatter(*zip(*points),s=18,marker=marker,color=color,alpha=.75,
                               label='ascending lanes' if direction==0 else 'reversed lanes')
            ax.axvline(0,color='0.6',linewidth=.7)
            ax.grid(alpha=.18);ax.set_ylim(-.08,1.08)
            if row==0:ax.set_title(f'N start = {n}')
            if col==0:ax.set_ylabel(f'{width} B, K start {k}\nnew fraction')
            if row==3:ax.set_xlabel('measured phase (cycles)')
    axes[0,0].legend(fontsize=8,loc='center left')
    fig.suptitle('B200 AS input-version sensitivity: identity A, one warp store',fontsize=13)
    fig.text(.5,.015,'phase = pre-store clock − post-MMA clock; each point is an observed output fraction, not a physical transaction timestamp',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.96))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--maps',action='store_true')
    p.add_argument('--allow-incomplete',action='store_true',help='inspect failed historical runs without accepting them')
    p.add_argument('--plot',type=Path,help='optional SVG/PNG output stem (requires matplotlib)')
    a=p.parse_args()
    data=json.loads(Path(a.result).read_text());xs=[];complete=None
    for line in data['stdout'].splitlines():
        if not line.startswith('{'):continue
        x=json.loads(line)
        if x.get('event')=='result':xs.append(x)
        if x.get('event')=='complete':complete=x
    valid=data.get('returncode')==0 and complete is not None
    if complete:valid &= len(xs)==complete['cases']*complete['reps']
    patches={(w,n,0) for w in (128,256,512) for n in (0,64,128,192)}|{(128,n,8) for n in (0,64,128,192)}
    directions=(0,31) if data['suite'] in ('fine','tagged') else (0,)
    controls=collections.Counter((x['width'],x['n'],x['k'],x.get('lane_xor',0),x['mode']) for x in xs if x['mode']!='race')
    valid &= set(controls)=={(*patch,direction,mode) for patch in patches for direction in directions for mode in ('none','early','late')}
    valid &= all(v==data['reps'] for v in controls.values())
    valid &= not any(x['outside_errors'] or x['control_errors'] for x in xs)
    expected_cases={'smoke':48,'coarse':304,'fine':1952,'tagged':1024}
    valid &= bool(complete and not complete.get('build_only',False)
                  and complete['cases']==expected_cases.get(data['suite'])
                  and complete['reps']==data['reps'])
    identities=[(x['width'],x['n'],x['k'],x['mode'],x['delta'],x.get('pad',0),x.get('lane_xor',0),x['rep']) for x in xs]
    valid &= len(identities)==len(set(identities))
    print('Complete run metadata; validating D payloads' if valid else 'INVALID/INCOMPLETE run; no fetch conclusion')
    if not valid and not a.allow_incomplete:
        raise SystemExit('Use --allow-incomplete only to inspect diagnostics.')
    print('returncode',data.get('returncode'),'samples',len(xs),'controls',sum(x['mode']!='race' for x in xs))
    print('outside_errors',sum(x['outside_errors'] for x in xs),'control_errors',sum(x['control_errors'] for x in xs),
          'other_values',sum(x['other'] for x in xs),'replica_disagreements',sum(x['replica_disagreements'] for x in xs))
    by=collections.defaultdict(list);masks={};mixed_tiles=collections.Counter()
    for x in xs:
        vs=decode(x)
        key=x['width'],x['n'],x['k'],x.get('tagged',False)
        if key not in masks:
            width,n,k,tagged=key
            def offset(kk,nn):return 2*((nn//8)*128+(kk//8)*64+(nn%8)*8+kk%8)
            lo=offset(k,n)
            mask=tuple(lo<=offset(i//256,i%256)<lo+width for i in range(4096))
            target=tuple(struct.unpack('<f',struct.pack('<I',(0x4000+(offset(i//256,i%256)-lo)//2)<<16))[0]
                         if tagged and mask[i] else 2. for i in range(4096))
            masks[key]=(mask*8,target*8)
        mask,target=masks[key]
        assert sum(v==new and inside for v,new,inside in zip(vs,target,mask))==x['new_count']
        assert sum(v not in (1.,new) for v,new in zip(vs,target))==x['other']
        if valid:
            assert sum(v!=1. for v,inside in zip(vs,mask) if not inside)==x['outside_errors']==0
            assert sum(v!=ref for v,ref in zip(vs,vs[:4096]*8))==x['replica_disagreements']
            if x['mode']!='race':
                assert all(v==(new if x['mode']=='early' and inside else 1.) for v,new,inside in zip(vs,target,mask))
            assert x['pre']<x['admit']<x['done'] and x['mut_start']<x['mut_done']
            assert x['phase']==x['mut_start']-x['admit']
            epoch,delay,target,observed,diff=x['wait_debug']
            assert target==(epoch+512+delay)&0xffffffff
            assert diff==(observed-target)&0xffffffff and diff<0x80000000
            if x['mode']=='early':assert x['mut_done']<x['pre']
            if x['mode']=='late':assert x['mut_start']>x['done']
        if x['mode']=='race':
            by[x['width'],x['n'],x['k'],x.get('lane_xor',0)].append(x)
            if 0<x['new_count']<x['width']*4:
                states=[]
                for tile in range(x['width']//128):
                    kk=x['k']+(tile%2)*8;nn=x['n']+(tile//2)*8
                    versions={vs[k*256+n]!=1. for k in range(kk,kk+8) for n in range(nn,nn+8)}
                    states.append('1' if versions=={True} else '0' if versions=={False} else '?')
                mixed_tiles[x.get('lane_xor',0),x['width'],''.join(states)]+=1
    if valid:print('ACCEPTED complete run; full payloads and timing validated')
    print('mixed tile patterns (ascending 128-byte address order, 1=new, 0=old, ?=split):')
    for (direction,width,pattern),count in sorted(mixed_tiles.items()):
        print(' lane_xor',direction,'width',width,'pattern',pattern,'samples',count)
    if a.plot:
        if not valid:raise SystemExit('Plots require a validated complete run.')
        plot_phases(by,a.plot)
    print('width n k lane_xor | all-new phases | mixed phases | all-old phases | writer duration | distinct phases')
    def span(v):return f'{min(v)}..{max(v)} ({len(v)})' if v else '-'
    for key,rows in sorted(by.items()):
        full=key[0]//2*8
        phases=[[x['phase'] for x in rows if (x['new_count']==full if mode==0 else x['new_count']==0 if mode==2 else 0<x['new_count']<full)] for mode in range(3)]
        print(*key,'|',' | '.join(map(span,phases)),'|',span([x['writer_duration'] for x in rows]),
              '|',runs(sorted({x['phase'] for x in rows})))
        if a.maps:
            unique={}
            for x in rows:
                if not 0<x['new_count']<full:continue
                vs=decode(x);pattern=tuple(vs[:4096]);unique.setdefault(pattern,[]).append(x['phase'])
            for pattern,ps in sorted(unique.items(),key=lambda kv:min(kv[1])):
                print(' phases',span(ps))
                matching_k=collections.defaultdict(list)
                for k in range(16):
                    ids=tuple(n for n in range(256) if pattern[k*256+n]!=1.)
                    if ids:matching_k[ids].append(k)
                for ns,ks in matching_k.items():print('  K',runs(ks),'new N',runs(ns))

if __name__=='__main__':main()
