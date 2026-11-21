"""Summarize paired timing and LDS interference; reject AS-corrupted rows."""
import json
import statistics
import sys

rows={}
for name in sys.argv[1:]:
    data=json.load(open(name))
    for line in data['stdout'].splitlines():
        if not line.startswith('{'): continue
        x=json.loads(line)
        if x.get('event')!='result': continue
        if x['errors']:
            print('REJECTED AS MISMATCH',x['kind'],x['amount'],x['count'],x['diagnostics'])
            continue
        rows[x['kind'],x['amount'],x['meter'],x['reuse'],x['count']]=x
print('kind amount MMA_D MMA_R MMA_meter_D MMA_meter_R LDS_D LDS_R advantage coverage')
for kind,amount in sorted(set(k[:2] for k in rows)):
    if not all((kind,amount,m,r,n) in rows for m in (False,True) for r in (False,True) for n in (64,256)):continue
    mma=[];lds=[];coverage=[]
    for m in (False,True):
        for r in (False,True):
            a,b=[rows[kind,amount,m,r,n] for n in (64,256)]
            mma.append((b['median']-a['median'])/192)
            if not m:continue
            lds.append((statistics.median(q['span'] for q in b['lds'])-
                        statistics.median(q['span'] for q in a['lds']))/192)
            for x in (a,b):
                for q in x['lds']:
                    start,end=q['mma_begin'],q['mma_end']
                    coverage.append(min(max(0,min(e,end)-max(s,start))/(end-start)
                                        for s,e in zip(q['begin'],q['end'])))
    print(kind,amount,*(round(x,6) for x in mma+lds+[lds[0]-lds[1],min(coverage)]))
print('valid cases',len(rows))
