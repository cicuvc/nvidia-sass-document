# H100 instruction-cache topology and runtime patch visibility

Silicon: Modal H100 (sm_90), 2026-09-21.  The probes use repository-assembled
SASS and do not depend on ptxas.  Modal does not expose usable NCU counters, so
this note distinguishes timing-derived cache geometry, directly tested IVALL
behavior, and the still unknown performance-counter target/trace capacity.

## Topology summary

The current timing model has two distinguishable frontend residency levels:

> A nominal **128 KiB, 128-byte-line instruction cache shared by all four
> subcores of one SM**, plus a smaller branch-target/fetch structure with a
> **2 KiB equal-index period, 16-way-like conflict boundary, and 128-byte
> granularity**.  The latter corresponds to a 32 KiB address footprint per
> independent stream, but timing does not establish whether it is literally a
> data-bearing L0 I-cache or a target/trace-side structure.

The economical conventional-cache interpretation of the shared level is
`64 sets x 16 ways x 128 B = 128 KiB`.  Capacity and line size are strong;
the 64-set/16-way decomposition is the best current model rather than an
NCU-confirmed fact.

## Shared 128 KiB ICC

### Sequential capacity

`probe_icache_capacity.py` executes a warmed sequential loop.  It remains at
the small-loop throughput through 127 KiB and begins a sharp transition at
127.25 KiB:

| loop size | cycles/NOP |
|---:|---:|
| 124 KiB | 2.2201 |
| 126 KiB | 2.2205 |
| 127 KiB | 2.2201 |
| 127.25 KiB | 2.3969 |
| 127.5 KiB | 2.4073 |
| 128 KiB | 2.5943 |
| 129 KiB | 2.7820 |
| 132 KiB | 3.4785 |
| 144 KiB | 5.6562 |

The absolute baseline varied between Modal allocations (about 2.02 in the
coarse run and 2.22 in this longer fine run), but the within-run 127--128 KiB
knee is unambiguous.  As on B200 and GB202, nominal capacity is slightly
larger than the conflict-free contiguous working set.

### Sharing scope

Disjoint paths assigned to warp 0+4 (same subcore), warp 0+1 (different
subcores), or warps 0--3 (all subcores) respond to aggregate footprint rather
than placement:

| placement | per-path | aggregate | cycles/NOP |
|---|---:|---:|---:|
| same subcore, 2 warps | 48 KiB | 96 KiB | 2.029 |
| same subcore, 2 warps | 64 KiB | 128 KiB | 2.607 |
| different subcores, 2 warps | 64 KiB | 128 KiB | 2.600 |
| same subcore, 2 warps | 72 KiB | 144 KiB | 2.19 / 3.37 |
| different subcores, 2 warps | 72 KiB | 144 KiB | 2.26 / 3.39 |
| four subcores | 24 KiB | 96 KiB | 2.63--2.65 |
| four subcores | 32 KiB | 128 KiB | 3.05--3.13 |
| four subcores | 36 KiB | 144 KiB | 3.45--4.12 |

The four-warp absolute floor includes normal per-SM frontend contention, but
the capacity transition still tracks the aggregate code size.  A private
128 KiB cache per subcore would keep each 64--72 KiB path resident; it does
not.  The 128 KiB level is therefore SM-wide.

### Line, sets, and ways

Exact-address victim rings distinguish line boundaries.  Sixteen targets at
2-KiB spacing fit at 30.814 cycles/visit; adding a seventeenth raises this to
32.954.  Moving the victim by 64 bytes retains the penalty (33.119), while
moving it by 128 bytes removes it (31.187).  Thus bit 6 lies within a fetch
line and bit 7 begins a new line: line size is 128 bytes.

A shuffled-one-target-per-128B-block sweep also changes regime around 1024
blocks (128 KiB): 1024 blocks cost 59.48 cycles/line, 1032 cost 61.69, 1056
cost 68.36, and 1088 cost 74.57.  Together with the 8-KiB same-index conflict
and 16-to-17 knee, this supports 64 sets x 16 ways for the shared cache.

The useful differential is that 4-KiB spacing alternates two candidate shared
sets: 32 targets cost 39.73 cycles/visit and target 33 raises this to 49.21.
At 8-KiB spacing, 16 targets cost 30.88 and target 17 raises this to 36.31;
32 targets cost 67.05.  Both spacings have the same low bits at the smaller
2-KiB-period level, so the additional 8-KiB penalty supports a 64-set shared
level.  Rings above roughly 33 targets become non-monotonic (some larger rings
fall back near 31 cycles/visit), presumably because the target/trace mechanism
changes mode.  Consequently 64x16 is a strong working model, not a pure cache
replacement-policy proof.

## Smaller target/fetch level

Address-controlled JMP rings expose an additional 2-KiB periodic conflict:

- at 1-KiB spacing, 32 targets fit and target 33 conflicts;
- at 2-KiB spacing, 16 fit and target 17 conflicts;
- offsets +0 and +64 behave alike, while +128 selects a different index.

That is geometrically equivalent to 16 sets x 16 ways x 128 B = 32 KiB for a
single stream.  It cannot simply be identified with the shared ICC because
sequential code remains full-speed far beyond 32 KiB.

Four distinct-subcore streams can each hold 16 different tags at the same
low-address index with no interference: one stream costs 30.825 cycles/visit,
two cost 30.832 each at twice the aggregate rate, and four cost 30.879 each at
four times the rate.  Thus this level is replicated/partitioned by frontend
stream or subcore, rather than one global 16-way set.

Two warps on the same subcore cost about 41--45 cycles/visit whether their
rings use the same or different low-address index.  Scheduler sharing
dominates that comparison, so the data do not yet distinguish a per-subcore
cache from finer per-warp target state.  Calling it a **32 KiB-equivalent
target/fetch level** is safer than asserting a literal 32 KiB L0 I-cache.

## Result

> H100 does **not** have an IVALL-resistant tight-loop replay behavior under
> the tested construction.  A single target-side `CCTL.I.IVALL`, with no NOP
> padding after it, makes a replacement instruction visible to a previously
> hot tight loop.

This agrees with corrected GB202 and B200 measurements.  The old claim that a
tight loop defeats IVALL came from a 4096-iteration asynchronous-patcher test
that could finish before the patcher was admitted.

## Long-running asynchronous patch test

`sassdbg/probe_patch.py exp4` executes a 128-byte loop for 262144 iterations,
performs a device-side 128-bit replacement store while it is running, and
executes `CCTL.I.IVALL` on the target SM every iteration.

- gate-time replacement plus target IVALL was visible from iteration zero;
- without target-side IVALL, the running loop remained stale;
- the first long exp4 run changed at iteration 133637 (host observed patch ack
  at 133731);
- six additional runs all changed exactly once, at iterations
  132287--136691.  Their host-observed ack points were 132389--136795;
- the roughly 100-iteration ordering difference is host polling latency: the
  target can execute the replacement before the host reads the patcher's ack.

Thus all seven long-loop samples in which the patcher ran were fresh after
IVALL.

## Frozen-warp control

`sassdbg/probe_warp_mutable.py` removes asynchronous kernel-admission timing.
One divergent group heats the tight loop; its sibling freezes the warp,
the host replaces the hot instruction, and the sibling optionally performs
the invalidate before releasing the loop group.

| Case | Invalidate sequence | Valid outcome |
|---|---|---:|
| P2 | none | 29/29 stale |
| P3 | one `CCTL.I.IVALL`, zero padding | 30/30 fresh |

One additional P2 attempt failed before establishing the freeze handshake and
was classified as SETUP, not as a visibility sample.  There were zero
visibility, freeze, timeout, or abort failures among the 59 valid samples.

This frozen result is the decisive one: the IVALL instruction itself, rather
than target preemption or a large-loop refetch, makes the hot replacement
visible.

The probe also had a latent control bug: `Case.ivall="none"` was descriptive
but ignored, so a combined P2/P3 invocation could apply the global
`--ivall-count` to P2 as well.  The probe now forces P2 to zero invalidates and
classifies its expected stale result as PASS.

## Target/trace buffer remains unknown

The GB202 target/trace structure is almost invisible in execution time and
was identified with `sm__icc_requests`: slot-0 rings cross a counter boundary
at 12--13 targets, while slot-7 rings cross at 9--10.  H100 timing-only sweeps
show no corresponding boundaries:

| construction | below/above proposed boundary | cycles/visit |
|---|---:|---:|
| slot-0 JMP | 12 / 13 targets | 30.762 / 30.782 |
| slot-7 JMP | 9 / 10 targets | 5.970 / 5.933 |

The slot-0 ring remains nearly flat through 16 targets and rises at 17
(30.825 to 33.557 cycles/visit).  The address-dependent sweeps above assign
this to the smaller indexed target/fetch level, not to a simple 16-entry
fully-associative target buffer.  The same timing method hides GB202's
counter-proven 12-entry trace structure, so H100 may have both mechanisms.

Therefore the H100 conclusions are:

- no IVALL-resistant loop replay;
- ordinary instruction fetch is non-coherent without an invalidate;
- existence and depth of a smaller IVALL-flushable target/trace buffer remain
  unknown without performance counters;
- the 32 KiB-equivalent indexed level's literal storage format and ownership
  (per-subcore versus finer per-warp state) remain unknown.

## Reproduction

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --gpu H100 --script sassdbg/probe_patch.py \
  --args 'exp1 exp2 exp4 exp6'

/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --gpu H100 --script sassdbg/probe_warp_mutable.py \
  --args '--cases P2 P3 --ivall-count 1 --ivall-nops 0 --settle 0 --repeat 30'

/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --gpu H100 --script tests/asm_construct/probe_icache_capacity.py \
  --args '--sizes-kib 124,126,127,127.25,127.5,128,129,132,144 --reps 5'

/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_b200_probe.py \
  --gpu H100 --script tests/asm_construct/probe_icache_banks.py \
  --args '--sets 0,0,0,0 --warps 0,1,2,3 --lines 16 --reps 5'
```
