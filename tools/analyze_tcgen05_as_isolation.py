"""Summarize paired AS collector resource-isolation experiments."""
import json,sys,statistics
r=json.load(open(sys.argv[1]));rows={}
for line in r['stdout'].splitlines():
    if not line.startswith('{'):continue
    x=json.loads(line)
    if x.get('event')=='result':rows[(x['isolated'],x['gap'],x['meter'],x['reuse'],x['count'])]=x
coverage=[]
print('isolated gap meter reuse MMA_slope LDS_span_slope')
for c,g in ((False,0),(True,0),(False,32),(True,32)):
 for meter in (False,True):
  for reuse in (False,True):
   if (c,g,meter,reuse,256) not in rows:continue
   a,b=[rows[c,g,meter,reuse,n] for n in (64,256)]
   slope=(b['median']-a['median'])/192
   ls=None
   if meter:
    ls=(statistics.median(x['span'] for x in b['lds'])-statistics.median(x['span'] for x in a['lds']))/192
    for q in (a,b):
     for x in q['lds']:
      start,end=x['mma_begin'],x['mma_end']
      coverage.append(min(max(0,min(e,end)-max(s,start))/(end-start) for s,e in zip(x['begin'],x['end'])))
   print(int(c),g,int(meter),int(reuse),round(slope,6),None if ls is None else round(ls,6))
print('cases',len(rows),'minimum_three_warp_coverage',min(coverage,default=0))
