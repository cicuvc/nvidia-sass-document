#!/usr/bin/env python3
"""Analyze validated bare-SASS WS completion slopes and independent controls."""
import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(path):
    raw = json.loads(Path(path).read_text())
    events = [json.loads(line) for line in raw['stdout'].splitlines() if line.startswith('{')]
    rows = [r for r in events if r['event'] == 'result']
    complete = [r for r in events if r['event'] == 'complete']
    if raw['returncode'] or len(complete) != 1 or len(rows) != complete[0]['cases']:
        raise ValueError('Incomplete or unsuccessful run')
    if any(r['errors'] or len(r['cycles']) != complete[0]['reps'] for r in rows):
        raise ValueError('Invalid samples')

    if raw.get('suite') == 'focus':
        groups=defaultdict(list)
        fields=('m','n','mode','stall','unroll','drotate')
        defaults=(128,128,'discard',1,0,False)
        for row in rows:
            if not row.get('atmem'): raise ValueError('Expected TMEM A focus control')
            groups[tuple(row.get(k,d) for k,d in zip(fields,defaults))].append(row)
        print('M N mode stall unroll D-rotation ; cycles/MMA')
        for key, group in sorted(groups.items()):
            if len(group)!=2: raise ValueError('Expected two lengths per focus control')
            lo,hi=sorted(group,key=lambda r:r['count'])
            rate=(statistics.median(hi['cycles'])-statistics.median(lo['cycles']))/(hi['count']-lo['count'])
            print(*key, ';', f'{rate:.4f}')
        print(f'{len(rows)} configurations, {len(rows)*(complete[0]["reps"]+1)} launches including warmups; zero errors')
        return

    def key(r):
        return tuple(r.get(k, d) for k, d in (
            ('m',128),('n',128),('mode','discard'),('count',256),
            ('stall',1),('unroll',0),('atmem',False),('ws',True)))
    data = {key(r): r for r in rows}
    if len(data) != len(rows): raise ValueError('Duplicate configurations')
    def med(m,n,mode,count,stall=1,unroll=0,atmem=False,ws=True):
        return statistics.median(data[(m,n,mode,count,stall,unroll,atmem,ws)]['cycles'])
    def slope(m,n,mode,**kw):
        return (med(m,n,mode,1024,**kw)-med(m,n,mode,64,**kw))/960
    modes = ('discard','refill','reuse','buffers','addresses','both','reuse_buffers','reuse_both')
    print('M N ' + ' '.join(modes) + ' ; reuse MAC/cycle')
    for m in (32,64,128):
        for n in (64,128,256):
            vals=[slope(m,n,mode) for mode in modes]
            print(m,n,' '.join(f'{v:.4f}' for v in vals),';',f'{m*n*16/vals[2]:.2f}')
    print('\nA-from-TMEM: discard/reuse slope')
    for m in (32,64,128):
        for n in (64,128,256):
            print(m,n,*(f'{slope(m,n,mode,atmem=True):.4f}' for mode in ('discard','reuse')))
    print('\nN128 scheduling controls, T1024/1024 (includes fixed overhead):')
    for m in (32,64,128):
        for mode in ('discard','reuse'):
            print(m,mode,*(f'stall{s}={med(m,128,mode,1024,stall=s)/1024:.4f}' for s in (0,1,4,12)))
    print('\nN128 loops: (T4096-T1024)/3072, cycles/MMA:')
    for m in (32,64,128):
        for mode in ('discard','reuse'):
            print(m,mode,*(f'U{u}={(med(m,128,mode,4096,unroll=u)-med(m,128,mode,1024,unroll=u))/3072:.4f}' for u in (16,64)))
    print('\nAS M128 controls: discard/A-reuse slopes:')
    for n in (64,128,256):
        print(n,*(f'{slope(128,n,mode,ws=False):.4f}' for mode in ('discard','reuse')))
    print('\nMiddle-length slope agreement: max absolute difference vs 64->1024:')
    diffs=[]
    for m in (32,64,128):
        for n in (64,128,256):
            for mode in modes:
                v=slope(m,n,mode)
                diffs.append((abs((med(m,n,mode,256)-med(m,n,mode,64))/192-v),m,n,mode))
    print(max(diffs))
    print(f'{len(rows)} configurations, {len(rows)*(complete[0]["reps"]+1)} launches including warmups; zero errors')

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('result_json')
    summarize(p.parse_args().result_json)
