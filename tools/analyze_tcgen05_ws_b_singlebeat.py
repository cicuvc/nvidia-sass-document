"""Offline validation of single-STS cross-N-band B capture."""
import argparse,base64,collections,json,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/asm_construct'))
from probe_sm100_ws_b_singlebeat import configurations,inspect,SIZE,static_check

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
        counts['replica_disagreements']+=x['replica_disagreements'];counts['same_B_pair_disagreements']+=sum(x['same_B_pair_differences'].values())
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

def plot_example(result,stem):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    from probe_sm100_ws_b_singlebeat import layout,OUT_SIZE
    import struct
    d=json.loads(Path(result).read_text())
    xs=[json.loads(l) for l in d['stdout'].splitlines() if l.startswith('{')]
    x=next(x for x in xs if x.get('event')=='result' and x['mode']=='race' and x['k']==0 and x['partition']=='alternating' and x['nbase']==0 and x['tile_swap']==0 and x['lane_xor']==0 and x['delta']==0 and x['pad']==2 and x['rep']==0)
    raw=zlib.decompress(base64.b64decode(x['raw_zlib_b64']));r=inspect(raw,x)
    vs=struct.unpack_from('<32768f',raw,64);selected=layout(0,0,'alternating',0)[0]
    colors=['#e5e7eb','#557cb4','#248b69'];fig,axes=plt.subplots(2,2,figsize=(8,6.5),layout='constrained')
    for w in range(4):
        target=set(selected[w]);arr=[]
        for k in range(8):
            arr.append([0 if (w*32+k)*256+n not in target else (1 if vs[(w*32+k)*256+n]==1 else 2) for n in range(8)])
        ax=axes[w%2,w//2];ax.imshow(arr,cmap=ListedColormap(colors),vmin=0,vmax=2,interpolation='nearest',aspect='equal')
        ax.set_xticks(range(0,8,2),range(128*(w//2),128*(w//2)+8,2));ax.set_yticks(range(8));ax.set_xlabel('Logical N');ax.set_ylabel('K')
        ax.set_title(f'Region {w}: '+('old (1)' if r['states'][w]=='O' else 'new (2)'))
    fig.suptitle(f'One 128B scalar STS, 32 distinct banks; selected versions = {r["states"]}\nK0..7, nbase=0; measured pre-store phase {r["phase"]:+d} cycles',fontsize=12)
    fig.legend(handles=[Patch(color=colors[0],label='Not modified'),Patch(color=colors[1],label='Modified, used old B'),Patch(color=colors[2],label='Modified, used new B')],loc='outside lower center',ncol=3)
    stem=Path(stem);fig.savefig(str(stem)+'.svg');fig.savefig(str(stem)+'.png',dpi=150);plt.close(fig)
    stem.with_suffix('.json').write_text(json.dumps({k:v for k,v in x.items() if k!='raw_zlib_b64'},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--output',type=Path);a=p.parse_args();r=analyze(a.result)
    if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('bounds','repeated_outcomes','examples')},indent=2))
    for k,v in r['examples'].items():print(k,json.dumps(v))
