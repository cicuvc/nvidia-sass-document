"""Validate every final payload and compare same-local-column input versions."""
import argparse,base64,collections,json,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/asm_construct'))
from probe_sm100_ws_b_versions import configurations,inspect,SIZE

def analyze(path):
    data=json.loads(Path(path).read_text());assert data['returncode']==0
    records=[json.loads(s) for s in data['stdout'].splitlines() if s.startswith('{')]
    complete=[x for x in records if x.get('event')=='complete'];assert len(complete)==1
    jobs=configurations(data['suite']);reps=data['reps']
    assert complete[0]['cases']==len(jobs) and complete[0]['reps']==reps and not complete[0]['build_only']
    xs=[x for x in records if x.get('event')=='result'];assert len(xs)==len(jobs)*reps
    seen=set();counts=collections.defaultdict(collections.Counter);pairs=collections.defaultdict(collections.Counter)
    coverage=collections.defaultdict(collections.Counter);examples={};patterns=collections.Counter();phases=collections.defaultdict(list)
    for x in xs:
        cfg=jobs[x['index']-1];assert all(x[k]==v for k,v in cfg.items())
        key=x['index'],x['rep'];assert key not in seen and 0<=x['rep']<reps;seen.add(key)
        raw=zlib.decompress(base64.b64decode(x['raw_zlib_b64']));assert len(raw)==SIZE
        checked=inspect(raw,cfg);assert all(x[k]==v for k,v in checked.items())
        m=str(cfg['m']);counts[m]['launches']+=1
        if cfg['mode']!='race':counts[m]['controls']+=1;continue
        counts[m]['races']+=1
        counts[m]['differing_regions']+=int(x['differing_regions'])
        counts[m]['replica_disagreements']+=x['replica_disagreements']
        counts[m]['mixed_launches']+=int(0<x['new_count']<256)
        counts[m]['all_old']+=int(x['new_count']==0);counts[m]['all_new']+=int(x['new_count']==256)
        counts[m]['within_N8_transition']+=int(any('O' in s and 'N' in s for s in x['columns']))
        counts[m]['within_K8_split']+=int(any('?' in s for s in x['columns']))
        for pair,diff in x['pair_differences'].items():pairs[m][pair]+=int(diff>0)
        phases[m].append(x['phase'])
        for w,mask in enumerate(x['masks']):
            for j in range(8):
                ckey=f'{m}/k{cfg["k"]}/c{cfg["nbase"]+j}/w{w}'
                coverage[ckey]['new']+=sum(row[j] for row in mask)
                coverage[ckey]['old']+=sum(1-row[j] for row in mask)
        if x['differing_regions']:
            pkey=f'M{m}/K{cfg["k"]}/xor{cfg["lane_xor"]}/'+','.join(x['columns'])
            patterns[pkey]+=1
            if pkey not in examples:examples[pkey]={k:v for k,v in x.items() if k not in ('raw_zlib_b64','masks')}
    return dict(validated_launches=len(xs),counts=counts,pair_disagreement_launches=pairs,
                phase_ranges={m:[min(v),max(v)] for m,v in phases.items()},patterns=patterns,examples=examples,
                coverage=coverage,missing_old_or_new=[k for k,v in coverage.items() if not v['old'] or not v['new']])

def plot_phase(result,stem,phase=4,k=0):
    """Each N8 block is a separate launch; only within-block comparisons are simultaneous."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    data=json.loads(Path(result).read_text())
    xs=[json.loads(line) for line in data['stdout'].splitlines() if line.startswith('{')]
    by=collections.defaultdict(list)
    for x in xs:
        if x.get('event')=='result' and x['mode']=='race' and x['k']==k and x['phase']==phase:
            by[x['m'],x['lane_xor'],x['nbase']].append(x)
    fig,axes=plt.subplots(3,2,figsize=(11,7),layout='constrained')
    saved=[]
    for i,m in enumerate((32,64,128)):
        for j,lx in enumerate((0,31)):
            rows=[[] for _ in range(4)];indices=[]
            for n in range(0,2*m,8):
                samples=by[m,lx,n];assert samples,(m,lx,n,phase)
                assert len({tuple(x['columns']) for x in samples})==1
                x=samples[0];indices.append(x['index'])
                for w in range(4):
                    assert '?' not in x['columns'][w]
                    rows[w].extend(int(c=='N') for c in x['columns'][w])
            boundaries=[]
            for row in rows:
                boundary=next((c for c,v in enumerate(row) if v),len(row))
                assert row==[0]*boundary+[1]*(len(row)-boundary)
                boundaries.append(boundary)
            ax=axes[i,j]
            ax.imshow(rows,aspect='auto',interpolation='nearest',cmap=ListedColormap(['#c3c8d1','#248b69']),vmin=0,vmax=1,extent=(0,2*m,3.5,-.5))
            ax.set_yticks(range(4),[f'region {w}' for w in range(4)])
            ax.set_xticks(range(0,2*m+1,max(8,m//2)))
            ax.set_title(f'M={m}, '+('forward' if lx==0 else 'reversed')+f'; first new = {boundaries}',fontsize=10)
            ax.set_xlabel('Local TMEM column')
            saved.append(dict(m=m,lane_xor=lx,phase=phase,k=k,first_new=boundaries,case_indices=indices))
    fig.suptitle(f'Final B version at measured mutation phase {phase:+d} cycles (K{k}..{k+7})\nGray = old, green = new. N8 blocks come from separate launches.',fontsize=12)
    stem=Path(stem)
    fig.savefig(str(stem)+'.svg');fig.savefig(str(stem)+'.png',dpi=150);plt.close(fig)
    stem.with_suffix('.json').write_text(json.dumps(dict(caveat='Cross-block reconstruction, not a single-launch full-B snapshot',panels=saved),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--output',type=Path);a=p.parse_args()
    r=analyze(a.result)
    if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('coverage','examples')},indent=2))
    print('example_count',len(r['examples']))
    for k,v in list(r['examples'].items())[:24]:print(k,json.dumps(v))
