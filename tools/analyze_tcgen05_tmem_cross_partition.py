"""Validate full same-launch payloads and enumerate visibility inversions."""
import argparse,base64,collections,json,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/asm_construct'))
from probe_sm100_tmem_cross_partition import configurations,inspect

def identity(x):
    return tuple(x[k] for k in ('experiment','producer','column','mode','delta','enabled','pad'))+(tuple(x['skews']),x['rep'])

def analyze(path,config_factory=configurations,inspector=inspect,modes=('as','ws')):
    data=json.loads(Path(path).read_text())
    events=[json.loads(s) for s in data['stdout'].splitlines() if s.startswith('{')]
    results=[x for x in events if x.get('event')=='result']
    ends=[x for x in events if x.get('event')=='complete']
    assert data['returncode']==0 and len(ends)==1 and not ends[0]['build_only']
    configs=config_factory(data['suite']);reps=data['reps']
    assert ends[0]['cases']==len(configs) and ends[0]['reps']==reps
    ids=[identity(x) for x in results]
    assert len(ids)==len(set(ids))==len(configs)*reps
    assert set(ids)=={identity(dict(c,rep=r)) for c in configs for r in range(reps)}
    for x in results:
        raw=zlib.decompress(base64.b64decode(x['raw_zlib_b64']))
        measured=inspector(raw,x)
        for k,v in measured.items():assert x[k]==v,(identity(x),k)
        assert not any(x[k] for k in ('final_errors','control_errors','other','row_disagreements'))
    out=dict(validated_launches=len(results),controls=sum(x['mode']!='race' for x in results),modes={})
    for mode in modes:
        xs=[x for x in results if x['mode']=='race' and x['experiment']==mode]
        counts=collections.Counter();pairs=collections.defaultdict(collections.Counter);extents=collections.defaultdict(list)
        clock_extents=collections.defaultdict(list)
        issue_intervals=collections.Counter();wait_intervals=collections.Counter()
        witnesses=[]
        for x in xs:
            counts['launches']+=1
            counts['all_old']+=all(r['old']==32 for r in x['records'])
            counts['all_new']+=all(r['new']==32 for r in x['records'])
            counts['mixed_launches']+=bool(x['mixed_pairs'])
            for k in ('start_inversions','strong_inversions','mixed_pairs','ordered_pairs'):
                counts[k]+=len(x[k])
            by_warp={r['warp']:r for r in x['records']}
            for a,b in x['ordered_pairs']:
                states=''.join('new' if by_warp[w]['new']==32 else 'old' for w in (a,b))
                counts['ordered_'+states]+=1
            for a in x['records']:
                issue_intervals[a['read_admit']-a['read_start']]+=1
                wait_intervals[a['read_done']-a['read_admit']]+=1
                extents[a['warp'],x['column'],'old' if a['old']==32 else 'new'].append(a['phase'])
                for clock in ('read_start','read_admit','read_done'):
                    clock_extents[x['column'],clock,'old' if a['old']==32 else 'new'].append(a[clock]-x['admit'])
                for b in x['records']:
                    if a['warp']>=b['warp']:continue
                    p=pairs[a['warp'],b['warp']];p['coobservations']+=1
                    p['mixed']+=(a['new']!=b['new'])
                    p['equal_start_mixed']+=(a['new']!=b['new'] and a['read_start']==b['read_start'])
                    p['post_issue_order_inversions']+=((a['new']==32 and b['old']==32 and a['read_admit']<b['read_admit']) or
                                                       (b['new']==32 and a['old']==32 and b['read_admit']<a['read_admit']))
                    p['completion_order_inversions']+=((a['new']==32 and b['old']==32 and a['read_done']<b['read_done']) or
                                                       (b['new']==32 and a['old']==32 and b['read_done']<a['read_done']))
                    p['start_inversions']+=([a['warp'],b['warp']] in x['start_inversions'] or [b['warp'],a['warp']] in x['start_inversions'])
                    p['strong_inversions']+=([a['warp'],b['warp']] in x['strong_inversions'] or [b['warp'],a['warp']] in x['strong_inversions'])
                    p['a_done_before_b_start']+=a['read_done']<b['read_start']
                    p['b_done_before_a_start']+=b['read_done']<a['read_start']
            if x['start_inversions'] or x['strong_inversions']:
                witnesses.append({k:v for k,v in x.items() if k!='raw_zlib_b64'})
        bounds=[]
        for warp,column in sorted({(w,c) for w,c,k in extents}):
            old=extents[warp,column,'old'];new=extents[warp,column,'new']
            bounds.append(dict(warp=warp,column=column,old_count=len(old),new_count=len(new),
                               latest_old=max(old) if old else None,earliest_new=min(new) if new else None))
        clock_bounds=[]
        for column,clock in sorted({(c,k) for c,k,state in clock_extents}):
            old=clock_extents[column,clock,'old'];new=clock_extents[column,clock,'new']
            clock_bounds.append(dict(column=column,clock=clock,old_count=len(old),new_count=len(new),
                                     latest_old=max(old) if old else None,earliest_new=min(new) if new else None))
        out['modes'][mode]=dict(counts=dict(counts),pairs={f'{a}-{b}':dict(v) for (a,b),v in sorted(pairs.items())},
                                bounds=bounds,column_clock_bounds=clock_bounds,witnesses=witnesses,
                                read_issue_intervals=dict(sorted(issue_intervals.items())),
                                read_wait_intervals=dict(sorted(wait_intervals.items())))
    if not {'as','ws'}<=set(modes):return out
    as_rows={identity(x)[1:]:x for x in results if x['experiment']=='as'}
    comparison=collections.Counter()
    for b in results:
        if b['experiment']!='ws':continue
        a=as_rows[identity(b)[1:]]
        comparison['configurations']+=1
        comparison['same_snapshot_values']+=all((p['old'],p['new'])==(q['old'],q['new']) for p,q in zip(a['records'],b['records']))
        comparison['same_read_phases']+=all(p['phase']==q['phase'] for p,q in zip(a['records'],b['records']))
        comparison['same_read_intervals']+=all(p['read_done']-p['read_start']==q['read_done']-q['read_start'] for p,q in zip(a['records'],b['records']))
    out['as_ws_comparison']=dict(comparison)
    return out

def plot_example(path,stem):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data=json.loads(Path(path).read_text());examples={}
    for line in data['stdout'].splitlines():
        if not line.startswith('{'):continue
        x=json.loads(line)
        if x.get('event')!='result' or x['mode']!='race':continue
        if (x['producer'],x['column'],x['pad'],x['skews'])==(0,128,40,[0,32,0,-32]):
            examples[x['experiment']]=x
    assert set(examples)=={'as','ws'}
    fig,axes=plt.subplots(2,1,figsize=(9,5),sharex=True,layout='constrained')
    for ax,mode in zip(axes,('as','ws')):
        x=examples[mode]
        for i,r in enumerate(sorted(x['records'],key=lambda r:r['read_start'])):
            start=r['phase'];end=r['read_done']-x['admit'];new=r['new']==32
            ax.plot([start,end],[i,i],lw=10,solid_capstyle='butt',color='#167d8d' if new else '#b17726')
            ax.scatter([r['read_admit']-x['admit']],[i],c='white',s=18,zorder=3)
            ax.text(end+3,i,f"warp {r['warp']}: {'new' if new else 'old'}  [{start}, {end}]",va='center',fontsize=9)
        ax.set_title(f'{mode.upper()} — one MMA, column 128, producer warp 0',loc='left',fontsize=11)
        ax.set(yticks=[],ylim=(-.6,2.6),xlim=(20,225))
        ax.grid(axis='x',alpha=.2)
    axes[-1].set_xlabel('Cycles relative to first post-MMA timestamp; bars: pre-LDTM to result wait completed')
    for suffix in ('.svg','.png'):fig.savefig(str(stem)+suffix,dpi=160)
    plt.close(fig)
    Path(str(stem)+'.json').write_text(json.dumps({m:{k:v for k,v in x.items() if k!='raw_zlib_b64'} for m,x in examples.items()},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--output');p.add_argument('--plot');a=p.parse_args()
    out=analyze(a.result);s=json.dumps(out,indent=2)+'\n'
    if a.output:Path(a.output).write_text(s)
    if a.plot:plot_example(a.result,a.plot)
    print(json.dumps({k:v if k!='modes' else {m:{'counts':q['counts'],'pairs':q['pairs'],'witnesses':len(q['witnesses'])} for m,q in v.items()} for k,v in out.items()},indent=2))
