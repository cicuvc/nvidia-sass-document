#!/usr/bin/env python3
"""Summarize CUDA/PTX WS probe samples; never treats loop timing as peak by fiat."""
import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path


def summarize(path):
    raw = json.loads(Path(path).read_text())
    groups = defaultdict(list)
    for line in raw['stdout'].splitlines():
        if not line.startswith('SAMPLE '):
            continue
        sample = {k: int(v) for k, v in re.findall(r'\b(\w+)=(-?\d+)(?= |$)', line)}
        if sample['errors']:
            raise ValueError(f'Invalid result: {line}')
        if sample['rep'] >= 0:
            key = tuple(sample[k] for k in ('m', 'n', 'mode', 'unroll', 'ops', 'lds'))
            groups[key].append(sample)
    if not groups or raw.get('returncode') != 0:
        raise ValueError('Missing samples or unsuccessful run')
    med = lambda key, field='mma': statistics.median(s[field] for s in groups[key])
    print('Completion slopes: (T4096-T256)/3840, cycles/MMA; modes discard/refill/reuse/rot-discard/rot-reuse')
    for m in (32, 64, 128):
        for n in (64, 128, 256):
            values = [(med((m,n,mode,8,4096,0))-med((m,n,mode,8,256,0)))/3840 for mode in range(5)]
            print(f'M{m} N{n}: ' + ' / '.join(f'{x:.3f}' for x in values) +
                  f' ; MAC/cyc discard={m*n*16/values[0]:.1f} reuse={m*n*16/values[2]:.1f}')
    print('\nLength controls (median cycles/MMA):')
    for m in (32,64,128):
        for mode in (0,2):
            print(f'M{m} N128 mode{mode}: ' + ' '.join(f'{ops}: {med((m,128,mode,8,ops,0))/ops:.4f}' for ops in (256,1024,4096)))
    print('\nUnroll controls at N128, 4096 ops (median cycles/MMA):')
    for m in (32,64,128):
        for mode in (0,2):
            print(f'M{m} mode{mode}: ' + ' '.join(f'U{u}: {med((m,128,mode,u,4096,0))/4096:.4f}' for u in (4,8,16,32)))
    print('\nLDS contention (baseline span; MMA time / LDS span / excess per MMA):')
    for m in (32,64,128):
        for n in (64,128,256):
            base=med((m,n,0,8,0,2048),'lds_span')
            print(f'M{m} N{n} LDS baseline={base} (~{131072/base:.3f} wavefront/cycle)')
            for mode in range(5):
                key=(m,n,mode,8,1024,2048)
                span=med(key,'lds_span')
                vals=[s['lds_span'] for s in groups[key]]
                print(f'  mode{mode}: MMA={med(key)} LDS={span} delta/MMA={(span-base)/1024:.3f}, LDS range={min(vals)}..{max(vals)}')
    print('\n' + raw['stdout'].splitlines()[-1])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_json')
    summarize(parser.parse_args().result_json)
