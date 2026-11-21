"""Validate matched WS shape scans without assuming the predicted outcome."""
import argparse,json
from pathlib import Path
from analyze_tcgen05_tmem_cross_partition import analyze
from probe_sm100_ws_shape_visibility import configurations,inspect

def plot_match(path,stem):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data=json.loads(Path(path).read_text());examples={}
    columns={'ws32':32,'ws64':72,'ws128':76}
    for line in data['stdout'].splitlines():
        if not line.startswith('{'):continue
        x=json.loads(line)
        if x.get('event')!='result' or x['mode']!='race' or x['rep']!=1:continue
        if x['column']==columns[x['experiment']] and x['skews']==[0,0,0,0]:examples[x['experiment']]=x
    assert set(examples)==set(columns)
    fig,axes=plt.subplots(3,1,figsize=(10,7),sharex=True,layout='constrained')
    for ax,mode in zip(axes,columns):
        x=examples[mode];by={r['warp']:r for r in x['records']}
        for i,w in enumerate((1,3,0)):
            r=by[w];a,b,c=[r[k]-x['admit'] for k in ('read_start','read_admit','read_done')]
            new=r['new']==32;color='#167d8d' if new else '#b17726'
            ax.plot([a,b],[i,i],color=color,lw=10,alpha=.25,solid_capstyle='butt')
            ax.plot([b,c],[i,i],color=color,lw=10,solid_capstyle='butt')
            ax.scatter([a,b,c],[i,i,i],color=color,s=20,zorder=3)
            ax.text(c+2,i,f"{'NEW' if new else 'OLD'}  {a}/{b}/{c}",va='center',fontsize=10)
        ax.set(yticks=range(3),yticklabels=('warp 1','warp 3','warp 0'),ylim=(-.6,2.6))
        ax.set_title(f"WS M{x['m']}N256 — local column {x['column']}, producer warp 2",loc='left',fontsize=11)
        ax.grid(axis='x',alpha=.2)
    first=min(r['phase'] for x in examples.values() for r in x['records'])
    last=max(r['read_done']-x['admit'] for x in examples.values() for r in x['records'])
    axes[-1].set_xlim(first-5,last+30)
    axes[-1].set_xlabel('Cycles relative to post-MMA stamp; labels: pre-read / post-issue / wait complete\nLight bars: pre-to-post issue clocks; solid bars: post-issue to post-wait clocks')
    for suffix in ('.svg','.png'):fig.savefig(str(stem)+suffix,dpi=160)
    plt.close(fig)
    Path(str(stem)+'.json').write_text(json.dumps({m:{k:v for k,v in x.items() if k!='raw_zlib_b64'} for m,x in examples.items()},indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--output');p.add_argument('--plot-match');a=p.parse_args()
    out=analyze(a.result,config_factory=configurations,inspector=inspect,modes=('ws32','ws64','ws128'))
    if a.output:Path(a.output).write_text(json.dumps(out,indent=2)+'\n')
    if a.plot_match:plot_match(a.result,a.plot_match)
    print(json.dumps({k:v if k!='modes' else {m:{'counts':q['counts'],'pairs':q['pairs'],'witnesses':len(q['witnesses'])} for m,q in v.items()} for k,v in out.items()},indent=2))
