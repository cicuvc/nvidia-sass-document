"""Validate full final D and summarize timed in-flight LDTM snapshots."""
import argparse,base64,collections,json,struct,zlib
from pathlib import Path

def decode(encoded,count):
    raw=zlib.decompress(base64.b64decode(encoded));assert len(raw)==count*4
    return struct.unpack(f'<{count}f',raw)

def load(path):
    data=json.loads(Path(path).read_text())
    events=[json.loads(line) for line in data['stdout'].splitlines() if line.startswith('{')]
    xs=[x for x in events if x.get('event')=='result']
    complete=[x for x in events if x.get('event')=='complete']
    assert data['returncode']==0 and len(complete)==1,'failed/incomplete probe'
    end=complete[0];expected={'smoke':189,'coarse':1512,'fine':2016,'paired':192,'alignment':1952,'columns':8192,'granularity':14304}[data['suite']]
    assert end['cases']==expected and not end['build_only'] and end['reps']==data['reps']
    assert len(xs)==expected*data['reps']
    ids=[tuple(x[k] for k in ('width','warp','column','mode','delta','pad','rep')) for x in xs]
    assert len(ids)==len(set(ids)),'duplicate samples'
    patches=({(1,warp,c) for warp in (2,3) for c in list(range(32))+list(range(112,144))+list(range(224,256))}|
             {(2,1,c) for c in range(255)} if data['suite']=='granularity' else
             {(1,1,c) for c in range(256)} if data['suite']=='columns' else
             {(16,1,c) for c in set(range(0,241,8))|set(range(7,241,8))} if data['suite']=='alignment' else
             {(2,warp,c) for warp in (1,2,3) for c in (0,240)} if data['suite']=='paired'
             else {(w,warp,c) for w in (1,2,16) for warp in (1,2,3) for c in (0,1,64,65,128,192,240)})
    controls=collections.Counter((x['width'],x['warp'],x['column'],x['mode']) for x in xs if x['mode']!='race')
    assert set(controls)=={(*p,m) for p in patches for m in ('none','early','late')}
    assert all(v==data['reps'] for v in controls.values())
    return data,xs

def validate(xs):
    for x in xs:
        w,c=x['width'],x['column'];v=decode(x['snapshot_zlib_b64'],32*w)
        columns=(c,x['second_column']) if x.get('paired') else tuple(range(c,c+w))
        old=sum(t==-float(columns[i%w]+1) for i,t in enumerate(v));new=sum(t==1. for t in v)
        assert (old,new,len(v)-old-new)==(x['old'],x['new'],x['other'])
        assert sum(t!=v[i%w] for i,t in enumerate(v))==x['row_disagreements']
        final=decode(x['d_zlib_b64'],32768)
        assert sum(t!=(1. if x['enabled'] else -float(i%256+1)) for i,t in enumerate(final))==x['final_errors']==0
        assert not x['control_errors']
        if x['mode'] in ('early','none'):assert old==len(v)
        if x['mode']=='late':assert new==len(v)
        assert x['pre']<x['admit']<x['done']
        assert x['read_start']<x['read_admit']<=x['read_done']
        assert x['phase']==x['read_start']-x['admit']
        assert x['read_interval']==x['read_done']-x['read_start']
        assert x['read_issue_interval']==x['read_admit']-x['read_start']
        assert x['completion_interval']==x['done']-x['admit']
        if x.get('paired'):
            assert w==2 and x['second_column']==240-c
            assert x['read_admit']<=x['first_read_done']<x['second_read_start']<x['second_read_admit']<=x['read_done']
            assert sum(t==1. for t in v[::2])==x['first_new']
            assert sum(t==1. for t in v[1::2])==x['second_new']
        epoch,delta,target,observed,diff=x['wait_debug']
        assert target==(epoch+512+delta)&0xffffffff and diff==(observed-target)&0xffffffff and diff<0x80000000
        if x['mode']=='early':assert x['read_done']<x['pre']
        if x['mode']=='late':assert x['read_start']>x['done']

def span(xs):return f'{min(xs)}..{max(xs)} ({len(xs)})' if xs else '-'

def column_patterns(x):
    w=x['width'];c=x['column'];v=decode(x['snapshot_zlib_b64'],32*w)
    return [''.join('N' if t==1. else 'O' if t==-float(c+j+1) else '?'
                    for j,t in enumerate(v[lane*w:(lane+1)*w])) for lane in range(32)]

def alignment_summary(xs):
    boundaries=collections.Counter();relative=collections.Counter();patterns=collections.Counter()
    for x in xs:
        # Count each lane-identical pattern once per launch; retain differing
        # lane patterns rather than silently assuming agreement.
        for pat in set(column_patterns(x)):
            if 'N' not in pat or 'O' not in pat:continue
            patterns[pat]+=1
            for j in range(1,len(pat)):
                if pat[j]!=pat[j-1]:
                    direction=pat[j-1:j+1]
                    boundaries[x['column']+j,direction]+=1
                    relative[j,direction]+=1
    print('MIXED PATTERNS (one count per distinct lane pattern per launch)',dict(sorted(patterns.items())))
    print('ABSOLUTE BOUNDARIES (first column on right, direction)',dict(sorted(boundaries.items())))
    print('READ-RELATIVE BOUNDARIES',dict(sorted(relative.items())))
    for alignment in (2,4,8,16,32,64):
        residues=collections.Counter()
        for (col,direction),n in boundaries.items():residues[col%alignment,direction]+=n
        print('boundary residues modulo',alignment,dict(sorted(residues.items())))

def column_thresholds(xs):
    rows=[]
    for c in sorted({x['column'] for x in xs}):
        rs=[x for x in xs if x['column']==c]
        old=[x['phase'] for x in rs if x['old']==32]
        new=[x['phase'] for x in rs if x['new']==32]
        rows.append((c,max(old) if old else None,min(new) if new else None))
    return rows

def column_summary(xs):
    rows=column_thresholds(xs)
    print('SCALAR THRESHOLD BRACKETS: column latest-all-old earliest-all-new (pre-read clocks)')
    for c,lo,hi in rows:print(c,lo,hi,'OVERLAP' if lo is not None and hi is not None and lo>=hi else '')
    for group in (4,8,16,32,64):
        brackets=[]
        for start in range(0,256,group):
            chunk=[(lo,hi) for c,lo,hi in rows if start<=c<start+group]
            old=[lo for lo,hi in chunk if lo is not None];new=[hi for lo,hi in chunk if hi is not None]
            brackets.append((start,max(old) if old else None,min(new) if new else None))
        print('POOLED group',group,'(start, latest old, earliest new)',brackets)

def frontiers(xs):
    by=collections.defaultdict(list)
    for x in xs:by[x['phase']].append(x)
    rows=[]
    for phase,rs in sorted(by.items()):
        old=[x['column'] for x in rs if x['old']==32]
        new=[x['column'] for x in rs if x['new']==32]
        if old and new:rows.append((phase,max(new),min(old)))
    return rows

def granularity_summary(xs):
    by=collections.defaultdict(list)
    for x in xs:by[x['width'],x['warp']].append(x)
    for key,rs in sorted(by.items()):
        w,warp=key
        old=[x['phase']-x['column']//2 for x in rs if x['old']==32*w]
        new=[x['phase']-x['column']//2 for x in rs if x['new']==32*w]
        failures=sum(x['new']!=(32*w if x['phase']-x['column']//2>=18 else 0) or x['other']>0 for x in rs)
        print('PAIR MODEL width/warp',key,'normalized phase = phase - floor(column/2)',
              'latest old',max(old) if old else None,'earliest new',min(new) if new else None,
              'violations of new iff normalized phase >= 18',failures,'/',len(rs))
        bins=collections.defaultdict(lambda:[0,0])
        for x in rs:
            if x['old']==32*w:bins[x['phase']-x['column']//2][0]+=1
            elif x['new']==32*w:bins[x['phase']-x['column']//2][1]+=1
        thresholds=sorted(bins)
        if thresholds:
            total_old=sum(v[0] for v in bins.values());left_new=0;scores=[]
            for threshold in thresholds+[thresholds[-1]+1]:
                scores.append((total_old+left_new,threshold))
                old_n,new_n=bins[threshold];total_old-=old_n;left_new+=new_n
            best=min(s for s,t in scores)
            print('BEST-FIT pair intercept(s)',[t for s,t in scores if s==best],
                  'all-old/all-new misclassifications',best,'mixed/other excluded',
                  sum(x['old']!=32*w and x['new']!=32*w for x in rs))
        if w==1:
            bounds=frontiers(rs)
            print('SAME-PHASE frontiers (phase, last new col, first old col)',bounds)
            adjacent=[(p,hi) for p,lo,hi in bounds if hi==lo+1]
            print('ADJACENT frontier count',len(adjacent),'odd boundaries',sum(c%2 for p,c in adjacent),
                  'violations of boundary = 2*(phase-17)',sum(c!=2*(p-17) for p,c in adjacent))
        else:alignment_summary(rs)

def service_summary(xs):
    controls=[x for x in xs if x['mode']!='race']
    by=collections.defaultdict(collections.Counter)
    for x in controls:by[x['width'],x['warp'],x['mode'],x['column']%2][x['read_interval']]+=1
    print('CONTROL read intervals (width, warp, mode, column parity -> cycle histogram)')
    for key,counts in sorted(by.items()):print(key,dict(sorted(counts.items())))
    failures=[x for x in controls if x['read_interval']!=24+(x['column']%2+x['width']-1)//2]
    print('Control violations of read interval = 24 + floor((column%2 + width - 1)/2):',len(failures),'/',len(controls))

def compare_scalar_reference(xs,reference):
    _,base=load(reference);validate(base)
    by=collections.defaultdict(set)
    for x in base:
        if x['mode']=='race' and x['width']==1:
            by[x['warp'],x['column'],x['phase']].add(x['new']==32)
    witnesses=[]
    for x in xs:
        if x['width']!=2:continue
        warp,c,phase=x['warp'],x['column'],x['phase']
        if by[warp,c,phase]=={True} and by[warp,c+1,phase]=={False}:
            witnesses.append(x)
    print('MATCHED scalar-reference split N/O vs one x2 read: samples',len(witnesses),
          'x2 all-new',sum(x['new']==64 for x in witnesses),
          'x2 all-old',sum(x['old']==64 for x in witnesses),
          'x2 mixed',sum(bool(x['new'] and x['old']) for x in witnesses))
    print('Matched examples (first column, phase, x2 new values, x2 read interval)',
          [(x['column'],x['phase'],x['new'],x['read_interval']) for x in witnesses[:12]])
    print('These comparisons use different launches and read widths; they diagnose reader dependence, not a simultaneous snapshot.')

def compare_modes(xs,reference):
    _,base=load(reference);validate(base)
    key=lambda x:tuple(x[k] for k in ('width','warp','column','mode','delta','pad','rep'))
    aa={key(x):x for x in base};bb={key(x):x for x in xs}
    assert aa.keys()==bb.keys(),'mode comparison requires identical configuration matrices'
    print('AS/WS comparison with',reference)
    for field in ('old','new','other','phase','read_interval','completion_interval','d_zlib_b64','snapshot_zlib_b64'):
        changes=collections.Counter(bb[k]['mode'] for k in aa if aa[k][field]!=bb[k][field])
        print(' field',field,'different samples',sum(changes.values()),'/',len(aa),'by mode',dict(changes))
    groups=sorted({(x['width'],x['warp']) for x in xs if x['width']==1})
    for w,warp in groups:
        ar=[x for x in base if x['mode']=='race' and (x['width'],x['warp'])==(w,warp)]
        br=[x for x in xs if x['mode']=='race' and (x['width'],x['warp'])==(w,warp)]
        at,bt=column_thresholds(ar),column_thresholds(br)
        assert [c for c,lo,hi in at]==[c for c,lo,hi in bt]
        print(' scalar warp',warp,'different latest-old/earliest-new brackets',sum(a!=b for a,b in zip(at,bt)),'/',len(at))

def plot_columns(xs,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(12,4.5))
    for c,lo,hi in column_thresholds(xs):
        if lo is not None:ax.scatter(c,lo,s=8,color='#235789')
        if hi is not None:ax.scatter(c,hi,s=8,color='#df6c24')
        if lo is not None and hi is not None:ax.plot([c,c],[lo,hi],color='0.5',lw=.6)
    for c in range(0,257,8):ax.axvline(c,color='0.8',lw=.4 if c%32 else 1,zorder=0)
    ax.set(xlabel='D column',ylabel='pre-read phase (cycles)',xlim=(-1,256),
           title='Scalar LDTM: latest all-old (blue) / earliest all-new (orange) per column')
    fig.text(.5,.01,'Independent launches; brackets include scheduling jitter and LDTM timing, not exact SRAM update times.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1));path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def plot_frontiers(xs,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    by=collections.defaultdict(lambda:collections.defaultdict(set))
    for x in xs:
        if x['column']<64:by[x['phase']][x['column']].add(x['new']==32)
    selected=[(p,cols) for p,cols in sorted(by.items()) if len(cols)==64
              and all(len(v)==1 for v in cols.values())
              and {next(iter(v)) for v in cols.values()}=={False,True}]
    matrix=[[int(next(iter(cols[c]))) for c in range(64)] for p,cols in selected]
    fig,ax=plt.subplots(figsize=(12,4))
    ax.imshow(matrix,aspect='auto',interpolation='nearest',cmap=ListedColormap(['#235789','#df6c24']),vmin=0,vmax=1,
              extent=(-.5,63.5,len(selected)-.5,-.5))
    for i,((phase,cols),row) in enumerate(zip(selected,matrix)):
        b=row.index(0)
        ax.plot([b-.5,b-.5],[i-.4,i+.4],color='white',lw=2)
        ax.text(b+.5,i,str(b),color='white',va='center',fontsize=9)
    for c in range(0,65,2):ax.axvline(c-.5,color='white',alpha=.18,lw=.5)
    ax.set_yticks(range(len(selected)),[f'+{p}' for p,cols in selected])
    ax.set_xticks(range(0,64,4));ax.set(xlabel='D column',ylabel='matched pre-read phase (cycles)',
        title='Scalar reads at matched phases: new (orange) / old (blue); label = first old column')
    fig.text(.5,.01,'Each cell combines independent launches at the same measured phase; this is not one simultaneous snapshot.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1));path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def plot_alignment(xs,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True)
    points=set();boundaries=set()
    for x in xs:
        pat=column_patterns(x)[0]
        for j,t in enumerate(pat):points.add((x['column']+j,x['phase'],t=='N'))
        for j in range(1,len(pat)):
            if pat[j]!=pat[j-1]:boundaries.add((x['column']+j,x['phase'],x['column']%8))
    for new,color,label in ((False,'#235789','old'),(True,'#df6c24','new')):
        ps=[(c,p) for c,p,n in sorted(points) if n==new]
        if ps:axes[0].scatter(*zip(*ps),s=5,c=color,alpha=.5,label=label,rasterized=True)
    for offset,color in ((0,'#369c6e'),(7,'#913baa')):
        ps=[(c,p) for c,p,o in sorted(boundaries) if o==offset]
        if ps:axes[1].scatter(*zip(*ps),s=20,c=color,label=f'read start mod 8 = {offset}')
    if not boundaries:
        axes[1].text(.5,.5,'No mixed windows observed',ha='center',va='center',transform=axes[1].transAxes)
    for ax in axes:
        for c in range(0,257,8):ax.axvline(c,color='0.8',lw=.4 if c%32 else 1,zorder=0)
        ax.set_ylabel('pre-read phase (cycles)');ax.set_xlim(-1,256)
        if ax.collections:ax.legend(loc='upper left')
    axes[0].set_title('LDTM.x16 sliding windows: lane-0 returned versions (overlapping launches)')
    axes[1].set_title('Old/new transitions inside one returned window; boundary = first column on right')
    axes[1].set_xlabel('absolute D column')
    fig.text(.5,.01,'Returned versions include reader service timing; this is not an instantaneous TMEM image.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,1));path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def plot_phases(xs,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    cmap=LinearSegmentedColormap.from_list('versions',['#235789','#f7f7f7','#df6c24'])
    fig,axes=plt.subplots(3,3,figsize=(12,8),sharex=True,sharey=True)
    columns=(0,1,64,65,128,192,240)
    for row,w in enumerate((1,2,16)):
        for col,warp in enumerate((1,2,3)):
            ax=axes[row,col]
            points=sorted({(x['phase'],columns.index(x['column']),x['new']/(32*w))
                           for x in xs if x['width']==w and x['warp']==warp})
            if points:
                px,py,colors=zip(*points)
                sc=ax.scatter(px,py,c=colors,cmap=cmap,vmin=0,vmax=1,s=25,edgecolors='0.3',linewidths=.25)
            ax.axvline(223,color='0.5',linestyle='--',linewidth=.7)
            ax.set_yticks(range(len(columns)),[str(c) for c in columns]);ax.set_ylim(-.6,6.6)
            ax.grid(alpha=.15)
            if row==0:ax.set_title(f'observer warp {warp}')
            if col==0:ax.set_ylabel(f'LDTM.x{w}\nfirst column')
            if row==2:ax.set_xlabel('read-start phase (cycles)')
    fig.suptitle('B200 AS UTCHMMA: ordinary LDTM sees D updates',fontsize=14)
    fig.subplots_adjust(left=.08,right=.88,bottom=.13,top=.89,hspace=.2,wspace=.12)
    cb=fig.colorbar(sc,cax=fig.add_axes([.91,.22,.015,.55]),ticks=[0,.5,1]);cb.ax.set_yticklabels(['all old','half new','all new'])
    fig.text(.5,.035,'phase = pre-LDTM clock − post-MMA clock; dashed line = producer completion stamp (+223).\nEach point is a completed read result, not an instantaneous whole-TMEM snapshot.',ha='center',fontsize=9)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def plot_pair(xs,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    candidates=[x for x in xs if x['warp']==1 and x['column']==0
                and x['first_new']==32 and x['second_new']==0 and not x['other']]
    if not candidates:raise ValueError('No ordered new-then-old example to plot')
    x=min(candidates,key=lambda x:(x['phase'],x['pad'],x['rep']))
    t=lambda key:x[key]-x['admit']
    fig,ax=plt.subplots(figsize=(10,3.5))
    ax.barh(2,t('done'),left=0,height=.35,color='#d9d9d9')
    ax.barh(1,t('first_read_done')-t('read_start'),left=t('read_start'),height=.35,color='#df6c24')
    ax.barh(0,t('read_done')-t('second_read_start'),left=t('second_read_start'),height=.35,color='#235789')
    for y,start,end,label in ((1,t('read_start'),t('first_read_done'),'1.0 (new), all 32 lanes'),
                              (0,t('second_read_start'),t('read_done'),'-241.0 (old), all 32 lanes')):
        ax.text(end+3,y,label,va='center',fontsize=10)
        ax.text(start,y+.28,f'+{start}',ha='center',fontsize=9)
        ax.text(end,y+.28,f'+{end}',ha='center',fontsize=9)
    ax.text(t('done'),2.28,f"+{t('done')}",ha='center',fontsize=9)
    ax.annotate('',xy=(t('second_read_start'),.25),xytext=(t('first_read_done'),.75),
                arrowprops=dict(arrowstyle='->',color='0.3'))
    ax.set_yticks([0,1,2],['second: column 240','first: column 0','producer completion wait'])
    ax.set_xlim(0,t('done')+12);ax.set_ylim(-.5,2.6);ax.grid(axis='x',alpha=.2)
    ax.set_xlabel('cycles relative to first post-MMA clock stamp')
    ax.set_title('One launch: new column 0 returns before the old column 240 read starts')
    fig.text(.5,.015,'Read bars end after their own scoreboard wait. The producer bar is a measured wait interval, not an exact execution latency.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.05,1,1));path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('.svg','.png'):fig.savefig(path.with_suffix(ext),dpi=180)
    plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('result');p.add_argument('--maps',action='store_true')
    p.add_argument('--reference-columns',type=Path,help='validated scalar sweep to compare with x2 at matched phases')
    p.add_argument('--compare-as',type=Path,help='AS reference with exactly the same configuration matrix')
    p.add_argument('--plot',type=Path,help='SVG/PNG output stem; requires matplotlib');a=p.parse_args()
    data,xs=load(a.result);validate(xs)
    race=[x for x in xs if x['mode']=='race']
    print('ACCEPTED: complete control matrix, full final D, snapshot values and timing validated')
    print('samples',len(xs),'controls',len(xs)-len(race),'races',len(race))
    print('mixed',sum(x['old']>0 and x['new']>0 for x in race),'unexpected_values',sum(x['other'] for x in race),
          'row_disagreements',sum(x['row_disagreements'] for x in race))
    print('new-value reads fully returned before producer completion timestamp',sum(x['new']>0 and x['read_done']<x['done'] for x in race))
    if data['suite']=='paired':
        print('Paired suite: width=2 means two serial scalar LDTMs, in [column, second_column] order; not one LDTM.x2.')
        forward=[x for x in race if x['column']==0 and x['first_new']==32 and x['second_new']==0 and not x['other']]
        print('ORDERED col0 new then col240 old:',len(forward),'samples; first-read phases',span([x['phase'] for x in forward]),
              '; second-read phases',span([x['second_read_start']-x['admit'] for x in forward]),
              '; both complete before producer stamp',sum(x['read_done']<x['done'] for x in forward))
    if a.plot:
        if data['suite']=='granularity':
            for warp in (2,3):plot_columns([x for x in race if x['width']==1 and x['warp']==warp],str(a.plot)+f'_warp{warp}')
        else:
            (plot_columns if data['suite']=='columns' else plot_alignment if data['suite']=='alignment' else plot_pair if data['suite']=='paired' else plot_phases)(race,a.plot)
            if data['suite']=='columns':plot_frontiers(race,str(a.plot)+'_frontiers')
    if data['suite']=='alignment':alignment_summary(race)
    if data['suite']=='columns':column_summary(race)
    if data['suite'] in ('columns','granularity'):granularity_summary(race)
    if data['suite'] in ('alignment','columns','granularity'):service_summary(xs)
    if a.reference_columns:compare_scalar_reference(race,a.reference_columns)
    if a.compare_as:compare_modes(xs,a.compare_as)
    by=collections.defaultdict(list)
    for x in race:by[x['width'],x['warp'],x['column']].append(x)
    print('width warp column | all-old phase | mixed phase | all-new phase | read interval | issue interval | MMA completion interval')
    for key,rs in sorted(by.items()):
        phases=[[x['phase'] for x in rs if (x['old']==32*x['width'] if mode==0 else x['old']>0 and x['new']>0 if mode==1 else x['new']==32*x['width'])] for mode in range(3)]
        print(*key,'|',' | '.join(map(span,phases)),'|',span([x['read_interval'] for x in rs]),
              '|',span([x['read_issue_interval'] for x in rs]),'|',span([x['completion_interval'] for x in rs]))
        if a.maps:
            patterns=collections.defaultdict(list)
            for x in rs:
                if not (x['old']>0 and x['new']>0) and not x['other']:continue
                v=decode(x['snapshot_zlib_b64'],32*x['width'])
                # Full lane/column state, so lane-specific transitions are retained.
                cols=(x['column'],x['second_column']) if x.get('paired') else tuple(range(x['column'],x['column']+x['width']))
                pat=tuple('N' if t==1. else 'O' if t==-float(cols[i%x['width']]+1) else '?' for i,t in enumerate(v))
                patterns[pat].append(x)
            for pat,ps in patterns.items():
                print(' snapshot phases',span([x['phase'] for x in ps]),'read-done phases',span([x['read_done']-x['admit'] for x in ps]))
                rows=collections.defaultdict(list);w=key[0]
                for lane in range(32):rows[''.join(pat[lane*w:(lane+1)*w])].append(lane)
                for row,lanes in rows.items():print('  lanes',','.join(map(str,lanes)),'O=old N=new ?=other:',row)

if __name__=='__main__':main()
