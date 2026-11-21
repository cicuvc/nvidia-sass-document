"""Validate sparse shared-B staging probes and compare version cutoffs."""
import argparse,base64,collections,json,struct,sys,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/asm_construct'))
from probe_sm100_as_b_stage import configurations,inspect,SIZE,OUT_SIZE,EXTRA,CHECK

def load(path):
    data=json.loads(Path(path).read_text());events=[json.loads(l) for l in data['stdout'].splitlines() if l.startswith('{')]
    xs=[x for x in events if x.get('event')=='result'];end=[x for x in events if x.get('event')=='complete']
    jobs=configurations(data['suite']);assert data['returncode']==0 and len(end)==1
    assert end[0]['cases']==len(jobs) and end[0]['reps']==data['reps'] and not end[0]['build_only']
    assert len(xs)==len(jobs)*data['reps']
    keys=('width','k','n','select_col','lane_xor','mode','delta','pad','enabled')
    expected={tuple(c[k] for k in keys)+(rep,) for c in jobs for rep in range(data['reps'])}
    actual=[tuple(x[k] for k in keys)+(x['rep'],) for x in xs]
    assert len(set(actual))==len(actual) and set(actual)==expected
    for x in xs:
        raw=bytearray(SIZE);struct.pack_into('<5Q',raw,0,*[x[k] for k in ('pre','admit','done','mut_start','mut_done')])
        struct.pack_into('<5I',raw,40,*x['wait_debug'])
        d=zlib.decompress(base64.b64decode(x['d_zlib_b64']));b=zlib.decompress(base64.b64decode(x['shared_zlib_b64']))
        assert len(d)==32768*4 and len(b)==x['width']
        raw[64:OUT_SIZE]=d;raw[OUT_SIZE:OUT_SIZE+len(b)]=b
        if x.get('joint'):
            snapshot=zlib.decompress(base64.b64decode(x['snapshot_zlib_b64']))
            assert len(snapshot)==CHECK-EXTRA
            raw[EXTRA:CHECK]=snapshot
        if x.get('checked'):
            checked=zlib.decompress(base64.b64decode(x['checked_zlib_b64']))
            assert len(checked)==SIZE-CHECK
            raw[CHECK:]=checked
        rebuilt=inspect(x,raw)
        for k,v in rebuilt.items():
            if isinstance(v,tuple):v=list(v)
            assert x[k]==v,(k,x[k],v)
    return data,xs

def cutoffs(xs):
    by=collections.defaultdict(list)
    for x in xs:
        if x['mode']=='race':by[x['width'],x['k'],x['n'],x['select_col'],x['lane_xor']].append(x)
    result=[]
    for key,rs in sorted(by.items()):
        new=[x['phase'] for x in rs if x['new_count']==x['target_count']]
        old=[x['phase'] for x in rs if x['new_count']==0]
        mixed=[x['phase'] for x in rs if 0<x['new_count']<x['target_count']]
        result.append((key,max(new) if new else None,min(old) if old else None,mixed))
    return result

def summarize(xs):
    races=[x for x in xs if x['mode']=='race']
    print('ACCEPTED complete matrix; full D, shared bytes, counters, clocks and controls revalidated')
    print('samples',len(xs),'controls',len(xs)-len(races),'races',len(races))
    print('errors',dict((k,sum(x[k] for x in xs)) for k in ('control_errors','outside_errors','other','replica_disagreements')))
    for k in (0,8):
        rs=[x for x in races if x['width']==128 and x['k']==k]
        if rs:
            mismatches=sum((x['new_count']==x['target_count'])!=(x['phase']<=x['n']//4-9+k//8) for x in rs)
            print('Half-tile cutoff model K',k,'new iff phase <= N/4 - 9 + K/8:',mismatches,'mismatches /',len(rs))
    groups=collections.defaultdict(list)
    for x in races:groups[x['width'],x['k'],x['n'],x['lane_xor'],x['pad'],x['rep']].append(x)
    print('N8 column-selection version-fraction disagreements',
          sum(len({x['new_count']/x['target_count'] for x in rs})!=1 for rs in groups.values()),'/',len(groups),'groups')
    if any(x.get('joint') for x in xs):
        witnesses=[x for x in races if x['locked_before_visible']]
        print('JOINT shared changed/fenced, D still sentinel, final D uses old B:',len(witnesses))
        print('snapshot unexpected',sum(x['snapshot_other'] for x in xs))
        print('witnesses by N8',dict(collections.Counter(x['n'] for x in witnesses)))
        for x in witnesses[:12]:
            print('witness',x['n'],x['select_col'],x['lane_xor'],'store',x['phase'],x['mut_done']-x['admit'],
                  'read',x['read_start']-x['admit'],x['read_done']-x['admit'],'producer done',x['done']-x['admit'])
            if x.get('checked'):print('  observed new shared bytes before D read; LDS wait finished',x['shared_check_done']-x['admit'])
    print('width K N selected_col lane_xor | latest all-new | earliest all-old | mixed phases')
    for key,lo,hi,mix in cutoffs(xs):print(*key,'|',lo,'|',hi,'|',sorted(set(mix)))
    # Inspect each B element, not just the fraction changed by the writer.
    mixed=collections.Counter()
    for x in races:
        if not 0<x['new_count']<x['target_count']:continue
        v=struct.unpack('<32768f',zlib.decompress(base64.b64decode(x['d_zlib_b64'])))
        pat=tuple(''.join('N' if v[k*256+n]==2. else 'O' if v[k*256+n]==1. else '?' for n in range(x['n'],x['n']+8)) for k in range(16))
        mixed[x['width'],x['k'],x['select_col'],x['lane_xor'],pat]+=1
    print('MIXED K/N maps (16 K rows of 8 columns; unmodified elements also O)')
    for key,count in sorted(mixed.items()):print(key,count)

def plot(xs,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,2,figsize=(12,10),sharex=True,sharey=True)
    for row,(width,k) in enumerate(((128,0),(128,8),(256,0))):
        for col,xor in enumerate((0,31)):
            ax=axes[row,col]
            for (w,kk,n,select,direction),lo,hi,mix in cutoffs(xs):
                if (w,kk,direction)!=(width,k,xor) or select==8:continue
                x=n+select
                if lo is not None:ax.scatter(x,lo,s=10,c='#df6c24')
                if hi is not None:ax.scatter(x,hi,s=10,c='#235789')
                if lo is not None and hi is not None:ax.plot([x,x],[lo,hi],c='0.6',lw=.7)
            for n in range(0,257,8):ax.axvline(n-.5,c='0.8',lw=.4)
            ax.set_title(f'{"K0..15" if width==256 else f"K{k}..{k+7}"}; lane xor {xor}')
            ax.set_ylabel('pre-store phase (cycles)');ax.set_xlabel('B column')
    fig.suptitle('Single-column B perturbations: latest all-new (orange) / earliest all-old (blue)')
    fig.text(.5,.01,'Store-issue timestamps bracket input-version sensitivity; they are not physical B-fetch times.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.96));path=Path(path)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def plot_witness(xs,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    candidates=[x for x in xs if x.get('locked_before_visible') and x['n']==240 and x['select_col']==0]
    if not candidates:return
    x=min(candidates,key=lambda x:(x['phase'],x['lane_xor'],x['rep']))
    t=lambda key:x[key]-x['admit']
    checked=x.get('checked',False)
    fig,ax=plt.subplots(figsize=(11,4.2 if checked else 3.6))
    bars=[(2,0,t('done'),'#cccccc','producer completion wait'),
          (1,t('mut_start'),t('mut_done'),'#df6c24','shared B column 240: 1 → 2 + fence'),
          (0,t('read_start'),t('read_done'),'#235789','LDTM column 240: still -241 sentinel')]
    if checked:
        bars=[(3,0,t('done'),'#cccccc','producer completion wait'),
              (2,t('mut_start'),t('mut_done'),'#df6c24','shared B column 240: 1 → 2 + fence'),
              (1,t('mut_done'),t('shared_check_done'),'#369c6e','LDS + wait: modified B values read back'),
              (0,t('read_start'),t('read_done'),'#235789','LDTM column 240: still -241 sentinel')]
    for y,lo,hi,color,label in bars:
        ax.barh(y,hi-lo,left=lo,height=.35,color=color)
        ax.text(lo,y+.24,f'+{lo}',ha='center',fontsize=9);ax.text(hi,y+.24,f'+{hi}',ha='center',fontsize=9)
    ax.set_yticks([b[0] for b in bars],[b[4] for b in bars]);ax.set_xlim(-5,240);ax.set_ylim(-.7,len(bars)-.4)
    ax.text(t('read_done')+5,0,'Final D = 1 (old B)',va='center',fontsize=10)
    ax.set_xlabel('cycles relative to first post-MMA clock stamp');ax.grid(axis='x',alpha=.2)
    ax.set_title('One launch: B mutation no longer changes the result before D becomes visible')
    fig.text(.5,.01,'Bars bracket instrumented operations; they do not locate an internal buffer or exact SRAM service times.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1));path=Path(path)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--plot',type=Path);a=p.parse_args()
    _,xs=load(a.result);summarize(xs)
    if a.plot:
        plot(xs,a.plot)
        if any(x.get('joint') for x in xs):plot_witness(xs,str(a.plot)+'_witness')
if __name__=='__main__':main()
