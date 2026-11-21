#!/usr/bin/env python3
"""Summarize validated WS buffer-ID cycles, rings, and burst controls."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def summarize(path):
    raw=json.loads(Path(path).read_text())
    events=[json.loads(l) for l in raw['stdout'].splitlines() if l.startswith('{')]
    done=[r for r in events if r['event']=='complete']
    rows=[r for r in events if r['event']=='result']
    if raw['returncode'] or raw.get('suite') not in ('conflict','conflict_mixed') or len(done)!=1 or len(rows)!=done[0]['cases']:
        raise ValueError('Incomplete conflict scan')
    starts=[r for r in events if r['event']=='start']
    if len(starts)!=1 or starts[0]['generator_sha256']!=hashlib.sha256(raw['generator_source'].encode()).hexdigest():
        raise ValueError('Generator provenance mismatch')
    groups=defaultdict(list)
    for r in rows:
        if r['errors'] or len(r['cycles'])!=done[0]['reps']:
            raise ValueError('Invalid result')
        groups[r['m'],r['mode'],r['pattern'],r['pattern_addresses']].append(r)
    slopes={}
    for key, group in groups.items():
        if len(group)!=2: raise ValueError('Expected two lengths')
        lo,hi=sorted(group,key=lambda r:r['count'])
        if (lo['count'],hi['count'])!=(96,768): raise ValueError('Unexpected lengths')
        slopes[key]=(statistics.median(hi['cycles'])-statistics.median(lo['cycles']))/672
    if raw['suite']=='conflict_mixed':
        if not all(r.get('mixed') and r['pattern_addresses'] for r in rows):
            raise ValueError('Expected mixed discard/reuse controls')
        for m in (32,64,128):
            print(f'\nM{m} N64: row=discard ID, column=reuse ID, different B addresses:')
            print('       b0       b1       b2       b3')
            for a in '0123':
                print('b'+a,*(f'{slopes[m,"discard",a+b,True]:8.4f}' if a!=b else '       -' for b in '0123'))
        print(f'\n{len(rows)} configs; {len(rows)*(done[0]["reps"]+1)} launches including warmups; zero errors')
        print('Maximum within-case timing range:',max(max(r['cycles'])-min(r['cycles']) for r in rows))
        return slopes
    for m in (32,64,128):
        print(f'\nM{m} N64, TMEM A. Fixed-address discard pair matrix:')
        print('      b0       b1       b2       b3')
        for a in '0123':
            print('b'+a,*(f'{slopes[m,"discard",a if a==b else a+b,False]:8.4f}' for b in '0123'))
        print('AB and BA are cyclic shifts: matrix entries measure pair averages, not isolated directed edges.')
        print('Three/four-ID rings:')
        for (mm,mode,p,addr),rate in sorted(slopes.items()):
            if mm==m and mode=='discard' and not addr and len(p)==len(set(p)) and len(p)>2:
                print(p,f'{rate:.4f}')
        print('Bursts: observed / simple adjacent-same-ID prediction / residual:')
        base=16 if m<128 else 32
        delta=12 if m<128 else 10
        for (mm,mode,p,addr),rate in sorted(slopes.items()):
            if mm==m and mode=='discard' and not addr and len(p)>len(set(p)):
                fraction=sum(a==b for a,b in zip(p,p[1:]+p[:1]))/len(p)
                pred=base+fraction*delta
                print(p,f'{rate:.4f} / {pred:.4f} / {rate-pred:+.4f}')
        print('Distinct addresses keyed by ID: discard / reuse:')
        for (mm,mode,p,addr),rate in sorted(slopes.items()):
            if mm==m and mode=='discard' and addr:
                print(p,f'{rate:.4f} / {slopes[m,"reuse",p,True]:.4f}')
        print('Single-ID reuse:', ' '.join(f'b{b}={slopes[m,"reuse",b,True]:.4f}' for b in '0123'))
    print(f'\n{len(rows)} configs; {len(rows)*(done[0]["reps"]+1)} launches including warmups; zero errors')
    print('Maximum within-case timing range:',max(max(r['cycles'])-min(r['cycles']) for r in rows))
    return slopes

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('result_json')
    summarize(p.parse_args().result_json)
