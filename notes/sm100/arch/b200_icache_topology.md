# B200 instruction cache and tight-loop replay

Silicon: Modal B200 (sm_100a), 2026-09-21.  All kernels were emitted by the
repository assembler; no ptxas or NCU was used.  The timing evidence supports
the following B200 model:

> The main SM-local ICC is **32 KiB with 128-byte fetch lines**, shared by all
> four subcores.  In front of it, address-controlled branch rings expose a
> separate **32 KiB-equivalent target/fetch level** with a 2-KiB equal-index
> period and 16-way-like boundary.  This smaller level is replicated or
> partitioned across subcores/independent fetch streams.  A tight loop does not
> remain hidden from per-iteration `CCTL.I.IVALL`.

The last statement is intentionally narrower than "there is no loop/target
buffer."  Timing alone cannot see the roughly 12-target structure found on
GB202 with ICC performance counters, and Modal currently provides no usable
NCU on B200.

## Capacity

`probe_icache_capacity.py` executes a warmed sequential loop whose requested
size is exactly known.  The fine sweep around the knee was:

| loop size | cycles/NOP |
|---:|---:|
| 30 KiB | 2.0214 |
| 31 KiB | 2.0207 |
| 31.25 KiB | 2.0206 |
| 31.5 KiB | 2.0680 |
| 31.75 KiB | 2.1205 |
| 32 KiB | 2.1232 |
| 33 KiB | 2.2861 |
| 36 KiB | 2.6968 |
| 40 KiB | 3.0838 |
| 48 KiB | 3.0819 |

Thus the nominal capacity is 32 KiB, with conflict-free sequential use through
about 31.25 KiB and the transition beginning at 31.5 KiB.  This is analogous
to GB202's nominal 64 KiB versus roughly 62.5 KiB conflict-free boundary.
Larger-loop timing has further bandwidth steps (about 3.39 cycles/NOP at
128 KiB and 5.98 at 192--256 KiB); without counters these are not assigned to
additional cache capacities.

## Set count and associativity

`probe_icache_hash.py` installs heap-resident branch targets at exact virtual
addresses.  With 128-byte address units, the relevant knees are:

| target spacing | targets | cycles/visit | interpretation |
|---:|---:|---:|---|
| 1 KiB | 32 | 31.256 | 16 targets in each of two sets fit |
| 1 KiB | 33 | 37.914 | 17th target in one set conflicts |
| 2 KiB | 16 | 30.818 | 16 targets in one set fit |
| 2 KiB | 17 | 33.447 | 17th same-set target conflicts |
| 4 KiB | 16 | 30.839 | 16 targets fit |
| 4 KiB | 17 | 33.889 | 17th conflicts |

For one branch stream this gives 16 ways and a 2 KiB equal-index period.
Combined with the independent line-size test below, its address footprint is
16 sets x 16 ways x 128 B = 32 KiB.  The observed low-bit mapping is consistent
with index `VA[10:7]`; higher virtual-address hash inputs were not scanned.
The multi-stream results below show that this cannot be treated as one global
16-way set shared by the whole SM.

## Independent 128-byte line-size test

Capacity and equal-set period alone only determine
`line_size * set_count = 2 KiB`.  To distinguish 64, 128, and 256-byte lines,
one victim target was followed by 16 targets separated by 2048 bytes:

| victim offset | total targets | cycles/visit |
|---:|---:|---:|
| 0 B | 16 | 30.815 |
| 0 B | 17 | 34.364 |
| 64 B | 16 | 30.816 |
| 64 B | 17 | 34.426 |
| 128 B | 17 | 31.301 |

The 17-target ring has a small target-count timing cost even without ICC
conflict (about 31.3 versus 30.8 cycles/visit), so the comparison is against
that baseline.  Offsets 0 and 64 conflict equally with the 2-KiB-spaced set,
whereas offset 128 selects the adjacent set and removes the additional ICC
penalty.  Therefore bit 6 is within a line and bit 7 begins the set index:
the line is 128 bytes.

The exact-byte construction is exposed as `probe_icache_hash.py
--offset-bytes` so this distinction can be reproduced without counters.

## Sharing scope

`probe_icache_partition.py` gives disjoint sequential paths to warp 0 and 4
(same subcore), warp 0 and 1 (different subcores), or warps 0--3 (all four
subcores).  Same-subcore and cross-subcore placement have the same aggregate
capacity boundary:

| placement | per-path | aggregate | cycles/NOP |
|---|---:|---:|---:|
| same subcore, 2 warps | 12 KiB | 24 KiB | 2.055 |
| different subcores, 2 warps | 12 KiB | 24 KiB | 2.052 |
| same subcore, 2 warps | 16 KiB | 32 KiB | 2.169 |
| different subcores, 2 warps | 16 KiB | 32 KiB | 2.127 |
| same subcore, 2 warps | 20 KiB | 40 KiB | 2.750 |
| different subcores, 2 warps | 20 KiB | 40 KiB | 2.745 |
| four subcores, 4 warps | 6 KiB | 24 KiB | 2.110 |
| four subcores, 4 warps | 10 KiB | 40 KiB | 3.10--3.14 |

The main capacity-bearing ICC is therefore one SM-wide 32 KiB structure, not
four private 32 KiB caches.  This does not include the smaller replicated or
partitioned branch-target/fetch state exposed below.

## Per-subcore/stream target-fetch structure

`probe_icache_banks.py` installs different 16-line rings at virtual addresses
whose low bits all select index zero.  If the 16-way structure above were one
global SM set, two or four rings would immediately overfill it.  Instead:

| streams | warp placement | cycles/visit per stream | aggregate visits/cycle |
|---:|---|---:|---:|
| 1 | warp 0 | 30.827 | 0.03244 |
| 2 | warps 0,1, different subcores | 30.831 / 30.831 | 0.06487 |
| 4 | warps 0--3, one per subcore | 30.870--30.877 | 0.12953 |

All rings use different tags but the same low-address index.  Throughput scales
almost exactly 1x/2x/4x, proving that the indexed structure is replicated or
partitioned across independent subcore fetch streams rather than globally
sharing 16 ways.

Warps 0 and 4 on the same subcore cost 42.9 cycles/visit for equal indices;
using indices 0 and 1 costs 49.0/51.7 rather than improving.  Thus their
difference is dominated by same-scheduler issue and relative-index fetch-port
effects, not a clean capacity oracle.  The measurements cannot yet distinguish
a literal per-subcore 32 KiB L0 I-cache from finer per-warp target/trace state.
The safe statement is that B200 has the same **per-subcore/stream 32
KiB-equivalent target/fetch level** observed on H100.

## Tight-loop self-modification result

The `sassdbg/probe_patch.py` experiment patches the payload instruction of a
running 128-byte loop.  The target optionally executes `CCTL.I.IVALL` every
iteration.  A gate-time patch first verifies that the store and target-side
invalidate path work.  Long runs are required: the old 4096-iteration probe
could finish before the asynchronous patcher was admitted, falsely looking
like an unflushable loop buffer.

Results:

- gate-time patch + target IVALL: the replacement is visible from iteration 0;
- 262144-iteration tight loop without IVALL: no transition, confirming the
  ordinary non-coherent ICC behavior;
- tight loop with per-iteration IVALL: in five trials where the patcher acked
  before target completion, all five produced exactly one transition, around
  iterations 133207--137013.  The transition preceded host observation of the
  ack by about 106--122 iterations.  A sixth trial was invalid because the
  patcher did not ack until iteration 262144, after the target had finished.

Consequently B200 has no *IVALL-resistant* loop/fetch buffer under this
construction.  A GB202 rerun subsequently found the same result: its old
contrary conclusion came from a target that finished before the patcher ran.
This does not rule out a small target/trace buffer that IVALL does flush. Rings
of 4--16 targets all cost roughly 30.3--30.85 cycles/visit, and timing has no
counterpart to GB202's counter-only 12-to-13-target request jump.  An NCU-capable
B200 is needed to determine whether such a buffer exists and its entry count.

## Reproduction

On Modal, use `tools/modal_b200_probe.py` (the `blkw` environment supplies the
Modal CLI):

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --script tests/asm_construct/probe_icache_capacity.py \
  --args '--sizes-kib 30,31,31.25,31.5,31.75,32,33,36,40,48 --reps 5'

/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --script tests/asm_construct/probe_icache_hash.py \
  --args '--stride-lines 8,16,32 --counts 16,17,32,33 --reps 4'

/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --script sassdbg/probe_patch.py --args 'exp1 exp2 exp4'

/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --gpu B200 --script tests/asm_construct/probe_icache_banks.py \
  --args '--sets 0,0,0,0 --warps 0,1,2,3 --lines 16 --reps 5'
```
