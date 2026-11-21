#!/usr/bin/env python3
"""Analyze legal-N WS reuse working-set and shared-contention evidence."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def summarize(path):
    raw=json.loads(Path(path).read_text())
    events=[json.loads(l) for l in raw['stdout'].splitlines() if l.startswith('{')]
    rows=[r for r in events if r['event']=='result']
    done=[r for r in events if r['event']=='complete']
    starts=[r for r in events if r['event']=='start']
    if raw['returncode'] or raw['suite']!='capacity' or len(done)!=1 or len(rows)!=done[0]['cases']:
        raise ValueError('Incomplete capacity scan')
    if len(starts)!=1 or starts[0]['generator_sha256']!=hashlib.sha256(raw['generator_source'].encode()).hexdigest():
        raise ValueError('Source provenance mismatch')
    for r in rows:
        if r['errors'] or len(r['cycles'])!=done[0]['reps']: raise ValueError('Invalid samples')
        if r['lds_iters'] and len(r['meter'])!=done[0]['reps']:raise ValueError('Missing meter samples')
    baseline=[r for r in rows if r.get('meter_only')]
    if len(baseline)!=1:raise ValueError('Missing LDS-only baseline')
    baseline=baseline[0];span=statistics.median(x['span'] for x in baseline['meter'])
    wavefronts=3*baseline['lds_iters']*baseline['meter_loads']*4
    print(f'LDS-only span={span}; {wavefronts} logical 128B wavefronts; {wavefronts/span:.6f} wavefronts/cycle')
    groups=defaultdict(list)
    for r in rows:
        if not r.get('meter_only'):groups[r['m'],r['n'],r['mode'],r['pattern'],r['lds_iters']].append(r)
    slopes={}
    for k,g in groups.items():
        if len(g)!=2:raise ValueError('Expected two lengths')
        lo,hi=sorted(g,key=lambda r:r['count'])
        if (lo['count'],hi['count'])!=(96,768):raise ValueError('Unexpected lengths')
        mma=(statistics.median(hi['cycles'])-statistics.median(lo['cycles']))/672
        meter=(statistics.median(x['span'] for x in hi['meter'])-statistics.median(x['span'] for x in lo['meter']))/672 if k[-1] else None
        slopes[k]=(mma,meter)
    print('\nM32: N slots footprint_KiB; discard MMA(no/with LDS), reuse MMA(no/with LDS); LDS-span slope discard/reuse:')
    for n in (64,128,256):
        for p in ('0','01','012','0123'):
            d0=slopes[32,n,'discard',p,0][0];d1,dt=slopes[32,n,'discard',p,2048]
            u0=slopes[32,n,'reuse',p,0][0];u1,ut=slopes[32,n,'reuse',p,2048]
            print(n,len(p),32*n*len(p)/1024,';',f'{d0:.4f}/{d1:.4f}',f'{u0:.4f}/{u1:.4f}',';',f'{dt:.4f}/{ut:.4f}')
    print('\nM32 uncontended reuse intercepts T96-96*slope (1/2/3/4 IDs):')
    for n in (64,128,256):
        values=[]
        for p in ('0','01','012','0123'):
            row=min(groups[32,n,'reuse',p,0],key=lambda r:r['count'])
            values.append(statistics.median(row['cycles'])-row['count']*slopes[32,n,'reuse',p,0][0])
        print(n,values,'extra vs one ID:',[v-values[0] for v in values])
    print('\nM64/M128 four-buffer reuse: N MMA(no/with LDS); LDS-span slope:')
    for m in (64,128):
        for n in (64,128,256):
            u0=slopes[m,n,'reuse','0123',0][0];u1,ut=slopes[m,n,'reuse','0123',2048]
            print(m,n,f'{u0:.4f}/{u1:.4f}',f'{ut:.4f}')
    cover=[];long_cover=[];head=[];tail=[]
    for r in rows:
        if not r['lds_iters'] or r.get('meter_only'):continue
        for x in r['meter']:
            a,b=x['mma_begin'],x['mma_end']
            cover.append(max(0,min(b,min(x['end']))-max(a,max(x['begin'])))/(b-a))
            if r['count']==768:long_cover.append(cover[-1])
            head.append(max(x['begin'])-a);tail.append(min(x['end'])-b)
    print('\nMinimum fraction of MMA interval overlapped by ALL three meter warps:',min(cover))
    print('Minimum overlap fraction for 768-MMA streams:',min(long_cover))
    print('Largest meter start lag:',max(head),'cycles; smallest meter end margin:',min(tail),'cycles')
    print('Maximum within-case MMA / LDS timing ranges:',max(max(r['cycles'])-min(r['cycles']) for r in rows),max(max(x['span'] for x in r['meter'])-min(x['span'] for x in r['meter']) for r in rows if r['meter']))
    print(f'{len(rows)} configurations, {len(rows)*(done[0]["reps"]+1)} launches; all output/guard/meter checks pass')
    return slopes

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('result_json')
    summarize(p.parse_args().result_json)
