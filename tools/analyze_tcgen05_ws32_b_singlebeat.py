"""Offline validation of single-STS cross-N-band B capture."""
import argparse,base64,collections,json,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/asm_construct'))
from probe_sm100_ws32_b_singlebeat import configurations,inspect,SIZE,static_check

def analyze(path):
    data=json.loads(Path(path).read_text());assert data['returncode']==0
    records=[json.loads(s) for s in data['stdout'].splitlines() if s.startswith('{')]
    complete=[x for x in records if x.get('event')=='complete'];assert len(complete)==1
    jobs=configurations(data['suite']);reps=data['reps']
    assert complete[0]['cases']==len(jobs) and complete[0]['reps']==reps and not complete[0]['build_only']
    xs=[x for x in records if x.get('event')=='result'];assert len(xs)==len(jobs)*reps
    seen=set();counts=collections.Counter();by=collections.defaultdict(collections.Counter);examples={};bounds=collections.defaultdict(lambda:{'new':[],'old':[]});coverage=collections.defaultdict(collections.Counter)
    repeats=collections.defaultdict(collections.Counter)
    for x in xs:
        assert 1<=x['index']<=len(jobs)
        cfg=jobs[x['index']-1];assert all(x[k]==v for k,v in cfg.items())
        key=x['index'],x['rep'];assert key not in seen and 0<=x['rep']<reps;seen.add(key)
        raw=zlib.decompress(base64.b64decode(x['raw_zlib_b64']));assert len(raw)==SIZE
        r=inspect(raw,cfg);assert all(x[k]==v for k,v in r.items())
        counts['launches']+=1
        if cfg['mode']!='race':counts['controls']+=1;continue
        counts['races']+=1;counts[x['states']]+=1;counts['group_split']+=int(x['group_split'])
        counts['replica_disagreements']+=x['replica_disagreements'];counts['nonprefix_states']+=int(not x['prefix_order'])
        g=f'{cfg["partition"]}/k{cfg["k"]}/swap{cfg["tile_swap"]}/xor{cfg["lane_xor"]}'
        by[g][x['states']]+=1
        if x['group_split'] or 'M' in x['states']:
            ekey=g+'/'+x['states']
            if ekey not in examples:examples[ekey]={k:v for k,v in x.items() if k not in ('raw_zlib_b64','masks')}
        repeats[str(x['index'])][f'{x["phase"]}:{x["states"]}']+=1
        for w,mask in enumerate(x['masks']):
            ck=g+f'/n{cfg["nbase"]}/w{w}'
            for j,v in enumerate(mask):coverage[ck+f'/element{j}']['new' if v else 'old']+=1
            if x['states'][w] in 'ON':bounds[ck]['new' if x['states'][w]=='N' else 'old'].append(x['phase'])
    return dict(validated_launches=len(xs),static=static_check(),counts=counts,groups=by,examples=examples,
                bounds={k:dict(latest_new=max(v['new']) if v['new'] else None,earliest_old=min(v['old']) if v['old'] else None) for k,v in bounds.items()},
                sampled_elements=len(coverage),missing_old_or_new=[k for k,v in coverage.items() if not v['old'] or not v['new']],repeated_outcomes=repeats)

def plot_patterns(result,stem):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    d=json.loads(Path(result).read_text())
    xs=[json.loads(l) for l in d['stdout'].splitlines() if l.startswith('{')]
    xs=[x for x in xs if x.get('event')=='result' and x['mode']=='race']
    order=['NNNN','ONNN','OONN','OOON','OOOO']
    order=[state for state in order if any(x['states']==state for x in xs)]+sorted({x['states'] for x in xs}-set(order))
    chosen=[]
    for state in order:
        ys=[x for x in xs if x['states']==state]
        x=min(ys,key=lambda x:(x['nbase']!=0,x['k']!=8,x['partition']!='interleaved',x['tile_swap']!=0,x['lane_xor']!=0,abs(x['phase']),x['index'],x['rep']))
        raw=zlib.decompress(base64.b64decode(x['raw_zlib_b64']));r=inspect(raw,x);assert r['states']==state
        chosen.append(x)
    arr=[[0 if x['states'][w]=='O' else 1 if x['states'][w]=='N' else .5 for x in chosen] for w in range(4)]
    fig,ax=plt.subplots(figsize=(max(10,len(chosen)*2),4.5),layout='constrained')
    ax.imshow(arr,aspect='auto',interpolation='nearest',cmap=ListedColormap(['#557cb4','#e5aa39','#248b69']),vmin=0,vmax=1)
    ax.set_xticks(range(len(chosen)),[f'{x["states"]}\nN8 start {x["nbase"]}, K{x["k"]}\nphase {x["phase"]:+d}' for x in chosen])
    ax.set_yticks(range(4),[f'region {w} / N band {64*w}..{64*w+63}' for w in range(4)])
    for j,x in enumerate(chosen):
        for w in range(4):ax.text(j,w,x['states'][w],ha='center',va='center',color='white',fontsize=16)
    ax.set_title('M32 final B versions: one 128B conflict-free STS\nIndependent launches; four regions compared within each launch.',fontsize=12)
    fig.legend(handles=[Patch(color='#557cb4',label='O: old B'),Patch(color='#248b69',label='N: new B')],loc='outside lower center',ncol=2)
    stem=Path(stem);fig.savefig(str(stem)+'.svg');fig.savefig(str(stem)+'.png',dpi=150);plt.close(fig)
    stem.with_suffix('.json').write_text(json.dumps([{k:v for k,v in x.items() if k!='raw_zlib_b64'} for x in chosen],indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--output',type=Path);a=p.parse_args();r=analyze(a.result)
    if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('bounds','repeated_outcomes','examples')},indent=2))
    for k,v in r['examples'].items():print(k,json.dumps(v))
