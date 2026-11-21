"""AS reuse savings while a separate warp makes timestamped HMMA progress."""
import json
import base64
import statistics
import struct
import sys
import zlib

rows={}
for path in sys.argv[1:]:
    data=json.load(open(path))
    for line in data['stdout'].splitlines():
        if not line.startswith('{'):continue
        x=json.loads(line)
        if x.get('event')!='worker_result':continue
        if x['errors']:
            print('REJECTED AS MISMATCH',x['amount'],x['enabled'],x['count'],x['diagnostics'])
            continue
        rows[x['amount'],x['enabled'],x['reuse'],x['count']]=x
print('amount enabled MMA_D MMA_R LDS_D LDS_R advantage min_worker_coverage min_LDS_coverage min_bursts128 min_bursts512 worker_cycles_per_burst')
for amount,enabled in sorted(set(k[:2] for k in rows)):
    if not all((amount,enabled,r,n) in rows for r in (False,True) for n in (128,512)):continue
    mma=[];lds=[];wc=[];lc=[];bursts={128:[],512:[]};periods=[]
    for reuse in (False,True):
        a,b=[rows[amount,enabled,reuse,n] for n in (128,512)]
        mma.append((b['median']-a['median'])/384)
        lds.append((statistics.median(q['span'] for q in b['lds'])-
                    statistics.median(q['span'] for q in a['lds']))/384)
        for x in (a,b):
            for q in x['lds']:
                start,end=q['mma_begin'],q['mma_end']
                wc.append(max(0,min(q['worker_end'],end)-max(q['worker_begin'],start))/(end-start))
                lc.append(min(max(0,min(e,end)-max(s,start))/(end-start) for s,e in zip(q['begin'],q['end'])))
                bursts[x['count']].append(q['worker_bursts_in_mma'])
                if 'worker_trace' in q:ts=q['worker_trace']
                else:
                    raw=zlib.decompress(base64.b64decode(q['worker_trace_deltas_zlib_b64']))
                    deltas=struct.unpack(f"<{q['worker_iters']-1}I",raw)
                    ts=[q['worker_trace_first']]
                    for delta in deltas:ts.append(ts[-1]+delta)
                assert sum(start<=t<=end for t in ts)==q['worker_bursts_in_mma']
                periods.extend(t-s for s,t in zip(ts,ts[1:]) if start<=s<t<=end)
    print(amount,int(enabled),*(round(v,6) for v in mma+lds+[lds[0]-lds[1],min(wc),min(lc)]),
          min(bursts[128]),min(bursts[512]),statistics.median(periods))
print('valid cases',len(rows))
