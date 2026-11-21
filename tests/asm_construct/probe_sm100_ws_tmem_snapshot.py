"""WS M128N256K16 version of the accepted AS in-flight TMEM probe.

Only the target UTCHMMA's .WS mode bit changes; all input data, clocks,
controls, observer warps, and readback code are inherited unchanged.
"""
from probe_sm100_as_tmem_snapshot import source as as_source,main

def source(width=1,warp=1,ordering='race',paired=False):
    s=as_source(width,warp,ordering,paired)
    assert s.count('UTCHMMA.1CTA')==(0 if ordering=='none' else 1)
    return s.replace('UTCHMMA.1CTA ', 'UTCHMMA.1CTA.WS ')

if __name__=='__main__':main(source_factory=source,experiment='ws')
