# B200 AS collector residency-isolation probe

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

2026-11-18. Hypothesis: another kernel on the same SM overwrites collector
state during long MMA issue gaps. Probe `tests/asm_construct/probe_sm100_as_isolation.py`,
runner `tools/modal_as_isolation.py`, analyzer `tools/analyze_tcgen05_as_isolation.py`.

## Conclusion

The continuous AS reuse benefit and its loss across long issue gaps persist when application shared memory plus driver reservation exhausts SM shared capacity. Ordinary concurrent CTA residency is therefore unnecessary for this effect; this is not a guarantee against preemption or other system-level activity.

## Evidence

## Device resources

Driver attributes: 65536 registers/SM, 233472 B shared/SM, 232448 B maximum
opt-in shared/CTA, 1024 B driver-reserved shared/CTA. Thus maximal application
shared plus per-CTA reservation exactly exhausts SM shared capacity. Occupancy
of the original probe was already reported as one active block/SM; alone that
does not exclude co-residency with a different smaller kernel.

## Current construction

Retain the exact original 128-thread/112-register SASS. Ordinary and isolated
source pairs are identical in all 16 comparisons. Isolated launches set the
maximum dynamic shared size and preferred shared carveout, and pass enough
dynamic shared to bring static+dynamic to 232448 B. With 1024 B driver overhead,
no shared residency capacity remains for another ordinary CTA on the same SM.
This reserves residency resources; it does not keep every execution unit busy
and does not prohibit a driver/hypervisor context switch.

The existing 512-column TMEM allocation is unchanged. Extra shared is reserved,
not accessed. Probe A/B are immutable. Matrix: ordinary/isolated, gap 0/32 NOPs,
discard/use, no LDS/three LDS meters, count64/256; warmup plus five retained runs.
Runtime assertions require actual shared+reservation == per-SM capacity,
REGCOUNT=112 and occupancy=1 for isolation. Full D/guard/meter checks are required
before accepting timings.

## Completed result

[Primary record: complete recovered stdout](data/tcgen05_as_isolation_20261118.json.gz)
contains all 32 launch/resource/result triplets and the completion event.
This record was recovered from app logs; the original return object and
historical source snapshot are unavailable. Device/resource attributes below
come from the successful run's logged results. The repository probe and runner
describe the construction.

App `ap-Tx773h5UkrOB68VHd2SsFE`, call `fc-01M7NDDJS74B6TWTFFMXMNM2XQ`
completed all **32 configurations**. One warmup plus five retained repetitions
per case = **192 launches / 160 retained timing samples**. All result events
report errors=0; full D, guard columns and LDS checksums passed. The ordinary
and isolated cases were executed within the same remote function call.

Every isolated case reports block128, REGCOUNT112, active_blocks_per_sm=1,
232448 B total application shared and 1024 B reserved shared against a 233472 B
SM capacity. Without the LDS meter: 40960 B static + 191488 B dynamic. With the
meter: 65536 B static + 166912 B dynamic. Both sum to the full 227 KiB application
allowance; driver overhead accounts for the remaining 1 KiB.

Slopes are `(T256-T64)/192`, units cycles/MMA. MMA columns have no LDS pressure;
LDS columns are fixed-work meter-span extensions, not exact byte counts.

| Residency | Gap NOPs | MMA discard | MMA reuse | LDS discard | LDS reuse |
|---|---:|---:|---:|---:|---:|
| ordinary | 0 | 48 | 32 | 47.828125 | 15.250000 |
| maximal shared | 0 | 48 | 32 | 47.828125 | 15.250000 |
| ordinary | 32 | 258 | 258 | 47.432292 | 47.421875 |
| maximal shared | 32 | 258 | 258 | 47.421875 | 47.432292 |

With the meter enabled, continuous MMA slopes are also identical: discard
49.864583, reuse32. Gap MMA slopes remain258. Each case's five MMA timings are
identical; LDS span spreads are 1 or 5 cycles. Minimum simultaneous coverage
by the three meter warps is 96.196% of the MMA interval.

Thus eliminating spare shared residency capacity does not restore AS reuse
benefits across the issue gap. Ordinary concurrent CTA/kernel residency on
the same SM is not necessary to reproduce the loss. This strengthens the
short-lived-reuse interpretation, while NOT proving its internal mechanism.
Driver/hypervisor preemption is not prohibited by this construction. Nor does
this isolate possible effects of our own LDS meter warps; the same internal
workload is retained on both sides of the residency comparison.


## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
