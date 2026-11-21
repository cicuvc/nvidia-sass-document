"""Full raw-buffer validation of WS M32 simultaneous chunk observations."""
import argparse,json
from pathlib import Path
from analyze_tcgen05_tmem_cross_partition import analyze
from probe_sm100_ws32_tmem_cross_partition import configurations,inspect

def plot_candidate(out,stem):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    x=out['modes']['ws32']['witnesses'][0]
    fig,ax=plt.subplots(figsize=(10,3.8),layout='constrained')
    rows=sorted(x['records'],key=lambda r:r['read_start'])
    for i,r in enumerate(rows):
        a,b,c=[r[k]-x['admit'] for k in ('read_start','read_admit','read_done')]
        color='#167d8d' if r['new']==32 else '#b17726'
        ax.plot([a,b],[i,i],color=color,lw=10,alpha=.25,solid_capstyle='butt')
        ax.plot([b,c],[i,i],color=color,lw=10,solid_capstyle='butt')
        ax.scatter([a,b,c],[i,i,i],s=24,color=color,zorder=3)
        ax.text(c+1,i,f"{'NEW' if r['new']==32 else 'OLD'}  {a}/{b}/{c}",va='center',fontsize=10)
    ax.set_yticks(range(len(rows)),[f"warp {r['warp']} / logical n={r['logical_column']}" for r in rows])
    ax.set_ylim(-.6,len(rows)-.4);ax.set_xlim(25,110)
    ax.set_title(f"WS M32N256: local column {x['column']}, producer warp {x['producer']}",loc='left')
    ax.set_xlabel('Cycles from post-MMA stamp; labels: pre-read / post-issue / result ready\nLight segment brackets LDTM issue; solid segment ends after the result wait')
    ax.grid(axis='x',alpha=.2)
    for suffix in ('.svg','.png'):fig.savefig(str(stem)+suffix,dpi=160)
    plt.close(fig)
    Path(str(stem)+'.json').write_text(json.dumps(x,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--output');p.add_argument('--plot');a=p.parse_args()
    out=analyze(a.result,config_factory=configurations,inspector=inspect,modes=('ws32',))
    if a.output:Path(a.output).write_text(json.dumps(out,indent=2)+'\n')
    if a.plot:plot_candidate(out,a.plot)
    print(json.dumps({k:v if k!='modes' else {m:{'counts':q['counts'],'pairs':q['pairs'],'witnesses':len(q['witnesses'])} for m,q in v.items()} for k,v in out.items()},indent=2))
