"""Paired A-reuse advantage and issue-rate summary for gap/yield sweeps."""
import json,sys,statistics
rows={}
for path in sys.argv[1:]:
 r=json.load(open(path))
 for line in r['stdout'].splitlines():
  if not line.startswith('{'):continue
  x=json.loads(line)
  if x.get('event')=='result':
   pt=tuple(x[k] for k in ('filler','nops','stall','nop_yield','mma_yield'))
   rows[pt,x['meter'],x['reuse'],x['count']]=x
print('filler nops stall nop_yield mma_yield MMA_D MMA_R LDS_D LDS_R advantage coverage')
for pt in sorted(set(k[0] for k in rows)):
 metrics=[];coverage=[]
 complete=all((pt,m,r,n) in rows for m in (False,True) for r in (False,True) for n in (64,256))
 if not complete:continue
 for meter in (False,True):
  for reuse in (False,True):
   a,b=[rows[pt,meter,reuse,n] for n in (64,256)]
   if not meter:v=(b['median']-a['median'])/192
   else:
    v=(statistics.median(q['span'] for q in b['lds'])-statistics.median(q['span'] for q in a['lds']))/192
    for x in (a,b):
     for q in x['lds']:
      start,end=q['mma_begin'],q['mma_end']
      coverage.append(min(max(0,min(e,end)-max(s,start))/(end-start) for s,e in zip(q['begin'],q['end'])))
   metrics.append(v)
 print(*pt,*(round(v,6) for v in metrics),round(metrics[2]-metrics[3],6),round(min(coverage),6))
print('cases',len(rows))
