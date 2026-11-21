# B200 AS A collector versus legacy HMMA

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

2026-11-18. Does register-fed `HMMA.16816.F32.BF16` interfere with the A reuse
state of activation-stationary `UTCHMMA.1CTA`?

## Conclusion

Same-warp legacy HMMA insertion reduces the AS A-reuse advantage, but the longer issue gaps confound an HMMA-specific effect. A separate HMMA warp preserves substantial reuse benefit at the measured overlap and issue density. Final tensor outputs, legacy-HMMA results, LDS checksums, and worker timestamps validate these measurements.

## Evidence

## Same-warp interleaving: complete

Probe `tests/asm_construct/probe_sm100_as_hmma.py`, runner
`tools/modal_as_hmma.py`, analyzer `tools/analyze_tcgen05_as_hmma.py`.
[Raw result, inventory, exact sources](data/tcgen05_as_hmma_20261118/result.json.gz).
App `ap-AOuPc0dPN6cY3pCvB1Lxal`; returncode0 and complete event.

The standalone legacy-HMMA check passes on B200: packed BF16 A=2, B=3,
FP32 C=5 gives101 in every one of the128 result floats. Its `@!PT` version
leaves all output registers zero. Each runs three times. This independently
confirms that this instruction and predicate configuration execute on the
allocated B200, before mixing them with UTCHMMA.

The main construction retains M128 N64 K16 AS with shared A=B=1, block128,
112 registers/thread and full SM shared residency reservation. Reuse is
A_KEEP followed by A_REUSE.A_KEEP; shared inputs are never changed and
there is no intermediate commit/wait. Insert1/2/4 legacy HMMAs between
successive UTCHMMA instructions, with separate destination register groups,
constant register A/B/C inputs and no dependence on AS operands/results.
Compare the same HMMAs predicated off, a stall1/yield0 NOP, and stall8 NOP
sequences. No filler follows the last UTCHMMA.

All configurations initialize the same HMMA registers before the timer.
Final HMMA values are saved only AFTER the LDS meters have finished, before
the scalar TMEM readback overwrites these registers. Thus the additional
observer stores do not enter either measured interval. All128x256 TMEM
output/guard entries, all four32-lane HMMA result groups, and the three LDS
warp checksums are checked. HMMA values deliberately differ from AS inputs,
so accidental propagation would also be visible as a numerical mismatch.

96 configurations, one warmup plus five retained repetitions =576 matrix
launches, plus6 standalone HMMA launches. No numerical/guard/checksum errors.
Five-sample MMA durations are identical within every case; maximum LDS span
spread is one cycle. All three LDS meters cover100% of the timed AS interval
(the identical HMMA-register initialization gives the meters a head start).

Slopes are `(T256-T64)/192`, units cycles per additional UTCHMMA. MMA columns
are without LDS meters; LDS columns are the fixed-work three-warp span
extension. LDS advantage = discard minus reuse, NOT an exact byte/hit count.

| Gap construction | MMA discard | MMA reuse | LDS discard | LDS reuse | LDS advantage |
|---|---:|---:|---:|---:|---:|
| none | 48 | 32 | 47.895833 | 15.250000 | 32.645833 |
| one stall1 NOP | 48 | 32 | 47.895833 | 15.250000 | 32.645833 |
| one `@!PT HMMA` | 77 | 69 | 47.552083 | 31.807292 | 15.744792 |
| one active HMMA | 78.5 | 70.5 | 46.000000 | 31.854167 | 14.145833 |
| two `@!PT HMMA` | 106 | 106 | 47.947917 | 47.968750 | -0.020833 |
| two active HMMA | 109 | 109 | 47.807292 | 47.984375 | -0.177083 |
| four `@!PT HMMA` | 122 | 122 | 47.593750 | 47.598958 | -0.005208 |
| four active HMMA | 125 | 125 | 47.645833 | 47.645833 | 0 |
| four stall8 NOPs | 48 | 34 | 47.864583 | 15.666667 | 32.197917 |
| six stall8 NOPs | 50 | 50 | 47.875000 | 15.953125 | 31.921875 |
| eight stall8 NOPs | 66 | 66 | 47.687500 | 31.869792 | 15.817708 |
| twelve stall8 NOPs | 98 | 98 | 47.755208 | 47.755208 | 0 |

With LDS pressure, one active HMMA gives discard/reuse MMA slopes79.5/70.5,
one predicated-off HMMA gives78/69. The sparse2/4-HMMA slopes do not change.

### What this says, and what it does not

Inserting legacy HMMA into the AS issuer's instruction stream reduces or
removes the observable reuse advantage. But it also makes that stream much
slower, even when the HMMA predicate is false. One active or predicated-off
HMMA lands in the previously observed partial-benefit interval; two or four
land beyond the NOP-only loss boundary. The
[NOP gap/yield sweep](tcgen05_as_collector_gap.md) therefore supplies a
substantial timing confound.

These results do NOT establish that HMMA overwrites the AS A collector or
that both operations share operand storage. Nor does predication prove
that no internal operand/control structures are touched. The relatively
small extra active-HMMA effect is not by itself a calibrated eviction count.
Mixed instruction issue/dispatch costs, TC contention, and ordinary AS
gap-associated loss remain possible explanations. Explicit instruction
interleaving also does not timestamp the internal asynchronous A fill/use.

## Separate HMMA warp: complete

`tests/asm_construct/probe_sm100_as_hmma_worker.py` keeps the AS producer
warp's UTCHMMA sequence continuous. Warp1 runs1024 HMMA bursts, with1 or4
active/predicated-off HMMAs per burst (plus a no-HMMA control). Warp2/3 run
the original fixed-work LDS meters. There are20 configurations, comparing
AS discard/reuse and counts128/512 at each of five worker settings.

Sixteen stall8 NOPs separate bursts to keep coupled-result/WAW handling
conservative. A timestamp after EVERY burst, with identical trace stores
in all controls, checks actual worker progress within the AS interval;
merely overlapping whole-kernel time ranges would not rule out HMMA being
starved until AS completes. Final HMMA values, AS output/guards and both LDS
checksums are checked. Extra shared residency remains fully reserved.

The two-meter slopes must be compared against their own controls, not the
absolute three-meter numbers above. This worker tests one warp/subcore
placement and finite HMMA issue density, not all possible concurrency.

The complete worker run uses lossless zlib/base64-compressed 32-bit timestamp
trace deltas. All 20 configurations returned complete results.
[Full results, inventory and exact sources](data/tcgen05_as_hmma_worker_compact_20261118/result.json.gz).
Both full interleaving kernels and short representatives of all worker
controls pass dependency checking (only existing sb_capacity advisories
are accepted); each remote full worker kernel is independently checked
again before launch.

### Validated results

All20 configurations pass:120 launches (one warmup plus five retained per
case),100 timing/trace samples. AS results/guards, HMMA result groups and
both LDS checksums are correct. All100 traces decode losslessly to1024
strictly increasing timestamps inside their worker begin/end bounds;
recomputed in-AS completion counts match the saved counts. Every resource
record confirms block128,112 registers/thread, occupancy1 and full SM shared
reservation. Maximum within-case timing spread is2 cycles for AS duration
and13 cycles for the LDS span.

Slopes use `(T512-T128)/384`, cycles per additional AS MMA. Both MMA columns
below INCLUDE the two LDS meter warps. LDS advantage is discard minus reuse.

| HMMA worker burst | Enabled | MMA discard | MMA reuse | LDS discard | LDS reuse | LDS advantage |
|---|---|---:|---:|---:|---:|---:|
| no HMMA | no | 50.229167 | 32.000000 | 45.726562 | 10.812500 | 34.914062 |
| 1 HMMA | predicate false | 52.593750 | 34.750000 | 46.750000 | 11.458333 | 35.291667 |
| 1 HMMA | active | 52.518229 | 34.875000 | 46.341146 | 11.583333 | 34.757812 |
| 4 HMMAs | predicate false | 53.500000 | 35.265625 | 41.778646 | 12.955729 | 28.822917 |
| 4 HMMAs | active | 53.419271 | 35.414062 | 45.481771 | 12.359375 | 33.122396 |

AS retains a substantial reuse advantage while HMMA executes in another
warp. Relative to the matching predicated-off worker, active HMMA raises
the AS reuse slope by only0.125 (one-HMMA burst) or0.1484375 (four-HMMA burst)
cycles/MMA. LDS savings do not collapse. Their non-monotonic change between
the four-HMMA active/off cases also cautions against treating these span
differences as a calibrated cache-miss/eviction counter.

### Actual HMMA progress is much sparser than the nominal padding suggests

The worker overlaps at least95.437% of the measured AS interval, and the
two LDS meters at least97.163%. More importantly, the trace proves actual
burst completions during that interval. For the active worker, each of the
five repetitions reports the following counts in the AS REUSE cases:

| HMMAs per burst | AS count128: completed bursts | AS count512: completed bursts | Burst-period median inside AS, count512 | Burst-period median after AS |
|---:|---:|---:|---:|---:|
| 1 | 5 | 21 | 837 | 187 |
| 4 | 1 | 6 | 2868 | 211 |

All periods are cycles. Thus512 AS MMAs overlap21 single-HMMA bursts or
6 four-HMMA bursts (24 HMMA instructions), not hundreds of densely issued
HMMAs. The four-HMMA count128 case has only one in-window completion, so
there is no wholly in-window burst-period pair for that case.

The predicated-off worker also slows markedly during AS: its reuse/count512
burst-period medians are834/2856 cycles for one/four HMMAs, versus187/211
after AS. The no-HMMA worker remains near186 cycles. This points to an
interaction involving HMMA-class issue/admission or scheduling, not simply
the arithmetic execution cost of active HMMA. The exact mechanism was not
isolated, and the periods include padding, trace traffic and loop control.

### Interpretation boundary

The cross-warp experiment rules out a wholesale loss of sustained AS reuse
under this tested HMMA load. It does NOT show that each individual HMMA
leaves collector contents untouched. An occasional invalidation followed
by a quick refill can coexist with a large aggregate reuse advantage,
especially at only21–24 HMMA instructions per512 AS operations. Nor does it
establish physically separate HMMA/AS operand stores or cover all warp
placements and issue densities.

Taken together, the same-warp and cross-warp results have NOT demonstrated
HMMA-specific A-collector flushing: the former has a strong gap confound,
and the latter preserves sustained reuse but has limited interference
density and no per-event hit/miss observation. A stronger next diagnostic
would need to associate a particular HMMA with the next AS A reload, rather
than infer that association from whole-sequence throughput alone.

Reproduce:

```
python3 tools/analyze_tcgen05_as_hmma.py notes/sm100/arch/data/tcgen05_as_hmma_20261118/result.json
python3 tools/analyze_tcgen05_as_hmma_worker.py notes/sm100/arch/data/tcgen05_as_hmma_worker_compact_20261118/result.json
```

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
