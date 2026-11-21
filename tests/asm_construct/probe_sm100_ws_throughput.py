#!/usr/bin/env python3
"""Bare SASS B200 WS throughput with independent buffer/address controls.

Reuses the V1 allocator + naked U-path + single UTCBAR construction of the
AS probes. All 128 lanes' D output and unused-column sentinels are checked.
"""
from __future__ import annotations
import argparse
import contextlib
from collections import Counter
import io
import itertools
import re
import random
import hashlib
import json
import statistics
import signal
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble_kernel

MODES = {
    # collector operation, rotate buffer ID, rotate shared B address
    'discard': ('discard', False, False),
    'refill': ('fill', False, False),
    'reuse': ('reuse', False, False),
    'buffers': ('discard', True, False),
    'addresses': ('discard', False, True),
    'both': ('discard', True, True),
    'reuse_buffers': ('reuse', True, False),
    'reuse_both': ('reuse', True, True),
}
OUT_SIZE = 64 + 128 * 256 * 4


def group(r, n):
    return '{' + ','.join(f'R{i}' for i in range(r, r+n)) + '}'


def source(m=128, n=128, count=256, mode='discard', stall=1, unroll=0,
           atmem=False, ws=True, drotate=False, pattern=None, pattern_addresses=False, mixed=False, random_b=False, lds_iters=0, meter_only=False):
    if meter_only and not lds_iters: raise ValueError('meter_only requires LDS meter')
    if random_b and (not pattern_addresses or not atmem or drotate):
        raise ValueError('random B uses explicit ID-address patterns, TMEM A, one D')
    if m not in (32,64,128) or n not in (64,128,256):
        raise ValueError('unsupported shape')
    if count < 8 or count % 4 or unroll % 4 or not 0 <= stall <= 12:
        raise ValueError('count>=8 and count/unroll multiple of four; stall 0..12')
    if not ws and (m != 128 or mode not in ('discard','reuse')):
        raise ValueError('AS controls use M128 discard/A-reuse only')
    if drotate and (m*n//128 > 128 or mode not in ('discard','reuse')):
        raise ValueError('D rotation requires disjoint 128-column tiles and fixed B')
    if mixed and (pattern is None or len(pattern)!=2 or pattern[0]==pattern[1] or mode!='discard'):
        raise ValueError('mixed requires two distinct IDs, first discard and second reuse')
    if pattern is not None:
        if not pattern or any(b not in '0123' for b in pattern):
            raise ValueError('pattern must contain collector IDs 0..3')
        if not ws or unroll or drotate or count % len(pattern) or mode not in ('discard','refill','reuse'):
            raise ValueError('patterns require static WS, whole periods, one D and direct collector mode')
        bids=[int(pattern[i % len(pattern)]) for i in range(count)]
        first_use={b:bids.index(b) for b in set(bids)}
        last_use={b:count-1-bids[::-1].index(b) for b in set(bids)}
    elif pattern_addresses:
        raise ValueError('pattern_addresses requires pattern')
    op, rotate_buffer, rotate_address = MODES[mode]
    name = 'ws_throughput'
    lines = [f'#fn {name}(out<8>) {{',
        '#pragma MAXREG_COUNT(112)', f'#pragma SHARED({0x10000 if lds_iters else 0xa000:#x})',
        '#pragma NUM_MBARRIERS(1)', '#pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)',
        'LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]',
        'S2R R4, SR_TID.X;[1:7:{}:2:0]',
        'SHR R5, R4, 0x5;[7:7:{1}:5:1]',
        'LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]',
        'IMAD.WIDE.U32 {R8,R9}, R4, 0x400, {R2,R3};[7:7:{0}:5:1]',
        'SHL R12, R4, 0x4;[7:7:{}:5:1]',
    ]
    # Contiguous buffers filled by 128 threads in 2-KiB stripes. K-major
    # LBO=128/SBO=256, exactly the validated CUDA probe's descriptor/layout.
    for start, size, val in [(0x1000,0x1000,0x3f803f80)] + [
            (0x2000+i*0x2000,0x2000,v) for i,v in enumerate(
                (0x3f803f80,0x40004000,0x40404040,0x40804080))] + ([(0xa000,0x4800,0x3f803f80)] if lds_iters else []):
        if random_b and 0x2000 <= start < 0xa000: continue
        lines += ['NOP;[7:7:{1}:8:1]']
        for r in range(24,28):
            lines += [f'MOV32I R{r}, {val:#x};[7:7:{{}}:5:1]']
        for off in range(start,start+size,0x800):
            lines += [f'STS.128 [R12+{off:#x}], {{R24,R25,R26,R27}};[7:1:{{1}}:8:1]']
    if random_b:
        lines[0]=f'#fn {name}(out<8>, inputs<8>) {{'
        lines += ['LDC.64 {R70,R71}, #param(inputs);[2:7:{}:1:0]',
                  'NOP;[7:7:{2}:8:1]',
                  'NOP;[7:7:{}:8:1]',
                  'NOP;[7:7:{}:8:1]',
                  'NOP;[7:7:{}:8:1]',
                  'IMAD.WIDE.U32 {R72,R73}, R4, 0x10, {R70,R71};[7:7:{2}:5:1]']
        lines += ['NOP;[7:7:{}:8:1]']*4
        for off in range(0,0x8000,0x800):
            lines += [f'LDG.E.128.STRONG.GPU {{R24,R25,R26,R27}}, [{{R72,R73}}+{off:#x}];[2:7:{{1}}:1:0]',
                      'NOP;[7:7:{2}:8:1]', 'NOP;[7:7:{}:8:1]',
                      'NOP;[7:7:{}:8:1]', 'NOP;[7:7:{}:8:1]',
                      f'STS.128 [R12+{0x2000+off:#x}], {{R24,R25,R26,R27}};[7:1:{{2}}:8:1]']
    lines += [
        'FENCE.VIEW.ASYNC.S;[7:7:{1}:5:1]',
        'S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]',
        'UMOV UR4, 0x400;[7:7:{}:1:0]',
        'ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]',
        'ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]',
        '@P0 BRA #label(setup_done);[7:7:{}:5:0]',
        '#!tmem_alloc_1cta(UR5, 512)',
        'UMOV UR18, 0x600;[7:7:{}:5:1]',
        '#!mbarrier_init(UR18, 1)',
        '#def_label(setup_done)',
        'WARPSYNC.ALL;[7:7:{}:5:0]', 'BAR.SYNC 0;[7:7:{}:5:1]',
        'LDS R10, [UR5];[0:7:{}:1:0]',
        'R2UR UR10, R10;[7:7:{0}:13:1]',
        'UIADD3 UR12, UPT, UPT, UR10, 0x100, URZ;[7:7:{}:5:1]',
    ]
    # Zero-initialize all D columns; outside the logical footprint must stay 0.
    for r in range(24,32):
        lines += [f'MOV R{r}, RZ;[7:7:{{}}:5:1]']
    for c in range(0,256,8):
        lines += [f'STTM.x8 tmem[UR10+{c:#x}], {group(24,8)};[7:7:{{}}:1:0]']
    lines += ['FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]', 'NOP;[7:7:{0}:5:1]']
    if atmem:
        for r in range(24,32):
            lines += [f'MOV32I R{r}, 0x3f803f80;[7:7:{{}}:5:1]']
        lines += [f'STTM.x8 tmem[UR12], {group(24,8)};[7:7:{{}}:1:0]',
                  'FENCE.VIEW.ASYNC.T;[0:7:{}:2:0]', 'NOP;[7:7:{0}:5:1]']
    descriptors = [(20,0x1000)] + [(22+2*i,0x2000+i*0x2000) for i in range(4)]
    for ur, addr in descriptors:
        lines += [f'UMOV UR{ur}, {((8<<16)|(addr>>4)):#x};[7:7:{{}}:5:1]',
                  f'UMOV UR{ur+1}, 0x4010;[7:7:{{}}:5:1]']
    lines += ['UMOV UR14, 0;[7:7:{}:5:1]',
              f'UMOV UR15, {((m//16)<<24 | (n//8)<<17 | 0x490):#x};[7:7:{{}}:5:1]',
              'UMOV UR16, 0;[7:7:{}:5:1]', 'UMOV UR18, 0x600;[7:7:{}:5:1]',
              'WARPSYNC.ALL;[7:7:{}:5:0]', 'BAR.SYNC 0;[7:7:{}:5:1]',
              'ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]',
              '@P0 BRA #label(mma_done);[7:7:{}:5:0]',
              '#def_label(timer_begin)',
              'CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:1]']

    if drotate:
        # Outside the timer: prepare second D base before timer_begin.
        pos=lines.index('#def_label(timer_begin)')
        lines.insert(pos, 'UIADD3 UR30, UPT, UPT, UR10, 0x80, URZ;[7:7:{}:5:1]')

    def mma(i):
        bid = bids[i] if pattern is not None else (i%4 if rotate_buffer else 0)
        breg = 22+2*(bid if pattern_addresses else (i%4 if rotate_address else 0))
        mods = '.WS' if ws else ''
        if ws and bid:
            mods += f'.BUFFER{bid}'
        this_op = 'reuse' if mixed and bid==bids[1] else op
        if this_op == 'fill':
            mods += '.B_KEEP'
        elif this_op == 'reuse':
            letter = 'B' if ws else 'A'
            first = i < (4 if rotate_buffer else 1)
            last = i >= count-(4 if rotate_buffer else 1)
            if pattern is not None:
                first, last = i == first_use[bid], i == last_use[bid]
            if not first:
                mods += f'.{letter}_REUSE'
            if not last:
                mods += f'.{letter}_KEEP'
        a = 'tmem[UR12]' if atmem else 'gdesc[{UR20,UR21}]'
        dreg = 30 if drotate and i%2 else 10
        return (f'UTCHMMA.1CTA{mods} {a}, gdesc[{{UR{breg},UR{breg+1}}}], '
                f'tmem[UR{dreg}], tmem[UR14], idesc[{{UR15,UR16}}], URZ, UPT;'
                f'[7:0:{{}}:{stall}:1]')

    if meter_only:
        pass
    elif not unroll:
        lines += [mma(i) for i in range(count)]
    else:
        lines += [mma(i) for i in range(4)]
        loops,tail=divmod(count-8,unroll)
        if loops:
            lines += [f'MOV32I R32, {loops};[7:7:{{}}:5:1]', '#def_label(mma_loop)']
            lines += [mma(4+i) for i in range(unroll)]
            lines += ['IADD3 R32, R32, -0x1, RZ;[7:7:{}:5:1]',
                      'ISETP.NE.AND P2, PT, R32, RZ, PT;[7:7:{}:13:1]',
                      '@P2 BRA #label(mma_loop);[7:7:{}:5:0]']
        lines += [mma(4+i) for i in range(tail)]
        lines += [mma(i) for i in range(count-4,count)]
    lines += ['UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]',
              '#!mbarrier_wait(UR18, 0)', 'WARPSYNC.ALL;[7:7:{}:5:0]',
              'CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:1]']
    lines += ['NOP;[7:7:{}:8:1]']*4
    lines += ['ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]',
              '@P1 STG.E.64.STRONG.GPU [{R2,R3}], {R16,R17};[7:0:{0}:8:1]',
              '@P1 STG.E.64.STRONG.GPU [{R2,R3}+8], {R18,R19};[7:1:{}:8:1]',
              'NOP;[7:7:{0,1}:5:1]',
              '#def_label(mma_done)', 'WARPSYNC.ALL;[7:7:{}:5:0]',
              'BAR.SYNC 0;[7:7:{}:5:1]']
    # Keep the first U-path load away from the CTA barrier's issue boundary.
    # This is outside the timed region; direct BAR -> LDTM readback is probed
    # separately because the first x8 read observed early values on other warps.
    lines += ['NOP;[7:7:{}:8:1]']*4
    # Scalar readback with an explicit dependency wait and a reusable address.
    # Keep this conservative observer entirely outside the timing window.
    lines += ['UIADD3 UR11, UPT, UPT, UR10, 0, URZ;[7:7:{}:5:1]',
              'MOV32I R33, 256;[7:7:{}:5:1]', '#def_label(readback_loop)',
              'LDTM R40, tmem[UR11];[0:7:{1}:1:0]',
              'NOP;[7:7:{0}:8:1]',
              'STG.E.STRONG.GPU [{R8,R9}+64], R40;[7:1:{}:8:1]',
              'IADD3 R8, P5, R8, 0x4, RZ;[7:7:{1}:5:1]',
              'IADD3.X R9, R9, RZ, RZ, P5, !PT;[7:7:{}:5:1]',
              'UIADD3 UR11, UPT, UPT, UR11, 0x1, URZ;[7:7:{0}:5:1]',
              'IADD3 R33, R33, -0x1, RZ;[7:7:{}:5:1]',
              'ISETP.NE.AND P2, PT, R33, RZ, PT;[7:7:{}:13:1]',
              '@P2 BRA #label(readback_loop);[7:7:{}:5:0]']
    lines += ['NOP;[7:7:{0,1}:5:1]', 'WARPSYNC.ALL;[7:7:{}:5:0]',
              'BAR.SYNC 0;[7:7:{}:5:1]',
              'ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]',
              '@P0 BRA #label(dealloc_done);[7:7:{}:5:0]',
              '#!tmem_dealloc_1cta(UR5, 512)', '#!tmem_relinquish_alloc_permit_1cta()',
              '#def_label(dealloc_done)', 'WARPSYNC.ALL;[7:7:{}:5:0]',
              'BAR.SYNC 0;[7:7:{}:5:1]', 'EXIT;[7:7:{}:5:0]', '}']
    if lds_iters:
        pos=lines.index('#def_label(mma_done)')+2
        lines[pos:pos]=meter_lines(lds_iters)
    return '\n'.join(lines)+'\n'


def random_b_data():
    rng=random.Random(20261117)
    data=bytearray(0x8000)
    sums=[]
    for b in range(4):
        cols=[]
        for n in range(256):
            bits_values=[0x3f00 | rng.randrange(256) | (rng.randrange(2)<<15) for _ in range(16)]
            values=[struct.unpack('<f',struct.pack('<I',bits<<16))[0] for bits in bits_values]
            cols.append(sum(values))
            for k,v in enumerate(values):
                off=(n//8)*128+(k//8)*64+(n%8)*8+k%8
                bits=struct.unpack('<I',struct.pack('<f',v))[0]>>16
                struct.pack_into('<H',data,b*0x2000+off*2,bits)
        sums.append(cols)
    return bytes(data),sums


def meter_lines(iters):
    # Three non-producer warps; 12 LDS.128 = 48 logical 128-byte wavefronts/iteration.
    a=['ISETP.EQ.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]',
       '@P0 BRA #label(meter_done);[7:7:{}:5:0]',
       'SHL R34, R6, 0x4;[7:7:{}:5:1]',
       'IMAD R34, R5, 0x1800, R34;[7:7:{}:5:1]',
       'IADD3 R34, R34, 0x8800, RZ;[7:7:{}:5:1]',
       'IMAD.WIDE.U32 {R104,R105}, R5, 0x10, {R2,R3};[7:7:{}:5:1]',
       'IMAD.WIDE.U32 {R106,R107}, R5, 0x8, {R2,R3};[7:7:{}:5:1]',
       f'MOV32I R33, {iters};[7:7:{{}}:5:1]',
       'MOV R96, RZ;[7:7:{}:5:1]',
       'CS2R {R100,R101}, SR_CLOCKLO;[7:7:{}:5:1]', '#def_label(meter_loop)']
    for j in range(12):
        a += [f'LDS.128 {group(40+4*j,4)}, [R34+{j*512:#x}];[2:7:{{}}:1:0]']
    a += ['NOP;[7:7:{2}:8:1]']
    for j in range(0,12,2):
        a += [f'IADD3 R96, R96, R{40+4*j}, R{44+4*j};[7:7:{{}}:5:1]']
    a += ['IADD3 R33, R33, -0x1, RZ;[7:7:{}:5:1]',
          'ISETP.NE.AND P2, PT, R33, RZ, PT;[7:7:{}:13:1]',
          '@P2 BRA #label(meter_loop);[7:7:{}:5:0]',
          'CS2R {R102,R103}, SR_CLOCKLO;[7:7:{}:5:1]']
    a += ['NOP;[7:7:{}:8:1]']*4
    a += ['MOV R97, RZ;[7:7:{}:5:1]']
    for r in range(40,88):
        a += [f'IADD3 R97, R97, R{r}, RZ;[7:7:{{}}:5:1]']
    a += ['ISETP.EQ.AND P1, PT, R6, RZ, PT;[7:7:{}:13:1]',
          '@P1 STG.E.64.STRONG.GPU [{R104,R105}], {R100,R101};[7:0:{}:8:1]',
          '@P1 STG.E.64.STRONG.GPU [{R104,R105}+8], {R102,R103};[7:1:{}:8:1]',
          f'@P1 STG.E.64.STRONG.GPU [{{R106,R107}}+{OUT_SIZE:#x}], {{R96,R97}};[7:2:{{}}:8:1]',
          'NOP;[7:7:{0,1,2}:5:1]', '#def_label(meter_done)']
    return a


def configurations(suite):
    if suite in ('capacity','capacity_smoke'):
        cases=[]
        for n in ((64,) if suite=='capacity_smoke' else (64,128,256)):
            for pattern in (('0','0123') if suite=='capacity_smoke' else ('0','01','012','0123')):
                for mode in ('discard','reuse'):
                    for lds in (0,2048):
                        for count in ((96,) if suite=='capacity_smoke' else (96,768)):
                            cases.append(dict(m=32,n=n,count=count,mode=mode,stall=1,atmem=True,
                                              pattern=pattern,pattern_addresses=True,random_b=True,lds_iters=lds))
        if suite=='capacity':
            for m in (64,128):
                for n in (64,128,256):
                    for lds in (0,2048):
                        for count in (96,768):
                            cases.append(dict(m=m,n=n,count=count,mode='reuse',stall=1,atmem=True,
                                              pattern='0123',pattern_addresses=True,random_b=True,lds_iters=lds))
        cases += [dict(m=32,n=64,count=96,mode='discard',stall=1,atmem=True,pattern='0',
                       pattern_addresses=True,random_b=True,lds_iters=2048,meter_only=True)]
        return cases
    if suite == 'conflict_mixed':
        return [dict(m=m,n=64,count=count,mode='discard',stall=1,atmem=True,
                     pattern=''.join(pair),pattern_addresses=True,mixed=True)
                for m in (32,64,128) for pair in itertools.permutations('0123',2)
                for count in (96,768)]
    if suite == 'conflict':
        cases=[]
        singles=list('0123')
        directed=[''.join(p) for p in itertools.permutations('0123',2)]
        triples=[''.join(p) for p in itertools.combinations('0123',3)]
        quads=['0'+''.join(p) for p in itertools.permutations('123')]
        pairs=[''.join(p) for p in itertools.combinations('0123',2)]
        bursts=[a*k+b*k for a,b in pairs for k in (2,4)]
        def add(m, mode, pattern, addresses=False):
            for count in (96,768):
                cases.append(dict(m=m,n=64,count=count,mode=mode,stall=1,atmem=True,
                                  pattern=pattern,pattern_addresses=addresses))
        for m in (32,64,128):
            for pattern in singles+directed+triples+quads+bursts:
                add(m,'discard',pattern)
            for pattern in pairs:
                add(m,'discard',pattern,True)
            for pattern in singles+pairs:
                add(m,'reuse',pattern,True)
        return cases
    if suite == 'focus':
        cases=[]
        for m in (32,64,128):
            for n in (64,128,256):
                for count in (64,1024):
                    cases.append(dict(m=m,n=n,count=count,mode='buffers',stall=1,atmem=True))
            for count in (64,1024):
                cases.append(dict(m=m,n=64,count=count,mode='addresses',stall=1,atmem=True))
        for count in (64,1024):
            cases.append(dict(m=32,n=64,count=count,mode='reuse_buffers',stall=1,atmem=True))
            for stall in (0,4,12):
                cases.append(dict(m=32,n=64,count=count,mode='reuse',stall=stall,atmem=True))
            for stall in (0,1):
                cases.append(dict(m=32,n=64,count=count,mode='reuse',stall=stall,atmem=True,drotate=True))
        for unroll in (16,64):
            for count in (1024,4096):
                cases.append(dict(m=32,n=64,count=count,mode='reuse',stall=1,atmem=True,unroll=unroll))
        return cases
    if suite == 'smoke':
        return [dict(m=m,n=128,count=64,mode=mode,stall=12)
                for m in (32,64,128) for mode in ('discard','reuse','reuse_both')]
    cases=[]
    for m in (32,64,128):
        for n in (64,128,256):
            for mode in MODES:
                for count in (64,256,1024):
                    cases.append(dict(m=m,n=n,count=count,mode=mode,stall=1))
    # Independent A-source and scheduling controls, still no PTX wrappers.
    for m in (32,64,128):
        for n in (64,128,256):
            for mode in ('discard','reuse'):
                for count in (64,1024):
                    cases.append(dict(m=m,n=n,count=count,mode=mode,stall=1,atmem=True))
    for m in (32,64,128):
        for mode in ('discard','reuse'):
            for stall in (0,4,12):
                cases.append(dict(m=m,n=128,count=1024,mode=mode,stall=stall))
            for unroll in (16,64):
                for count in (1024,4096):
                    cases.append(dict(m=m,n=128,count=count,mode=mode,stall=1,unroll=unroll))
    for n in (64,128,256):
        for mode in ('discard','reuse'):
            for count in (64,1024):
                cases.append(dict(m=128,n=n,count=count,mode=mode,stall=1,ws=False))
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',choices=('smoke','full','focus','conflict','conflict_mixed','capacity','capacity_smoke'),default='smoke')
    p.add_argument('--reps',type=int,default=5)
    p.add_argument('--build-only',action='store_true')
    p.add_argument('--artifacts',type=Path)
    args=p.parse_args()
    if args.reps<1: p.error('reps must be positive')
    print(json.dumps({'event':'start','suite':args.suite,'generator_sha256':
          hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}),flush=True)
    for index,config in enumerate(configurations(args.suite)):
        src=source(**config)
        # The checker models a no-progress upper bound for repeated rd=SB0
        # claims. Native MMA admission releases those claims while the stream
        # runs (validated by the AS probes and numerical readback here).
        # Keep depcheck enabled, retain/count this specific advisory, and fail
        # on any other diagnostic instead of relying on its strict flag.
        diagnostic_output=io.StringIO()
        with contextlib.redirect_stderr(diagnostic_output):
            assembled=assemble_kernel(src,arch='sm100a',check_deps=True,strict_deps=True)
        diagnostics=diagnostic_output.getvalue()
        codes=re.findall(r'\[depcheck\].*? \[([a-z_]+)\]',diagnostics)
        if set(codes)-{'sb_capacity'}:
            raise RuntimeError(diagnostics)
        meta=dict(config,source_sha256=hashlib.sha256(src.encode()).hexdigest(),
                  cubin_sha256=hashlib.sha256(assembled.code).hexdigest(),instructions=len(assembled.encoded),
                  depcheck_capacity_advisories=len(codes),meter_loads=12 if config.get('lds_iters') else 0)
        if args.artifacts:
            args.artifacts.mkdir(parents=True,exist_ok=True)
            (args.artifacts/f'case_{index:03}.sass').write_text(src)
            (args.artifacts/f'case_{index:03}.cubin').write_bytes(assembled.code)
        if args.build_only:
            print(json.dumps(dict(event='build',**meta)),flush=True)
            continue
        print(json.dumps(dict(event='launch',index=index,**config)),flush=True)
        mod=CudaModule(assembled.code)
        out_size=OUT_SIZE+(128 if config.get('lds_iters') else 0)
        out=mod.devmem_alloc(out_size)
        inputs=None
        if config.get('random_b'):
            input_bytes,dot_sums=random_b_data()
            inputs=mod.devmem_alloc(len(input_bytes));mod.device_write(inputs,input_bytes)
        width=config['m']*config['n']//128
        expected=float(config['count']*(40 if MODES[config['mode']][2] else 16))
        if config.get('pattern_addresses'):
            pattern=config['pattern']
            expected=float(16 * (config['count']//len(pattern)) * sum(int(b)+1 for b in pattern))
        if config.get('drotate'): expected /= 2
        ref_word=struct.unpack('<I',struct.pack('<f',expected))[0]
        def expected_word(col):
            return ref_word if col<width or (config.get('drotate') and 128<=col<128+width) else 0
        reference=[expected_word(i%256) for i in range(32768)]
        if config.get('random_b'):
            mult=Counter(config['pattern'])
            factors=[mult[str(b)]*(config['count']//len(config['pattern'])) for b in range(4)]
            for i in range(32768):
                warp=i//(256*32);col=i%256
                ncol=col+(0 if config['m']==128 else (warp//2 if config['m']==64 else warp)*width)
                value=sum(factors[b]*dot_sums[b][ncol] for b in range(4)) if col<width else 0
                reference[i]=struct.unpack('<I',struct.pack('<f',value))[0]
        if config.get('meter_only'): reference=[0]*32768
        samples=[];meter_samples=[]
        try:
            for rep in range(args.reps+1):
                mod.devmem_set(out,0,out_size//4)
                signal.alarm(30)  # OS terminates a genuinely stuck CUDA launch.
                mod.launch('ws_throughput',grid=(1,),block=(128,),args=[out]+([inputs] if inputs is not None else []))
                mod.synchronize()
                raw=mod.device_read(out,out_size)
                signal.alarm(0)
                start,end=struct.unpack_from('<QQ',raw)
                words=struct.unpack_from('<32768I',raw,64)
                bad=[(i//256,i%256,hex(v),hex(reference[i]))
                     for i,v in enumerate(words) if v!=reference[i]]
                if bad or end<=start:
                    raise AssertionError((config,rep,start,end,len(bad),bad[:12],
                        dict(Counter((row//32,col,value) for row,col,value,_ in bad))))
                if config.get('lds_iters'):
                    times=[struct.unpack_from('<QQ',raw,16*w) for w in (1,2,3)]
                    checks=[struct.unpack_from('<II',raw,OUT_SIZE+8*w) for w in (1,2,3)]
                    expected_check=((config['lds_iters']*12*0x3f803f80)&0xffffffff,(48*0x3f803f80)&0xffffffff)
                    assert all(c==expected_check for c in checks),(checks,expected_check)
                    assert all(e>s for s,e in times),times
                    if rep: meter_samples.append(dict(mma_begin=start,mma_end=end,begin=[s for s,e in times],end=[e for s,e in times],span=max(e for s,e in times)-min(s for s,e in times)))
                if rep: samples.append(end-start)
        finally:
            mod.devmem_free(out)
            if inputs is not None: mod.devmem_free(inputs)
        print(json.dumps(dict(event='result',device=mod.device_name,index=index,
              **meta,cycles=samples,median=statistics.median(samples),meter=meter_samples,errors=0)),flush=True)
    print(json.dumps({'event':'complete','cases':len(configurations(args.suite)),
                      'reps':args.reps}),flush=True)

if __name__=='__main__':
    main()
