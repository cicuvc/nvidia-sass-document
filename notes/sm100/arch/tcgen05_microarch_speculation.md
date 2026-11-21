# Blackwell tcgen05: current model and B200 evidence

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** AS/WS BF16 probes linked below; Modal NVIDIA B200
**Open items:** 3
**Audit:** synthesis of output-validated throughput, source-mutation, and TMEM-readback experiments

## Conclusion

The current model separates **B input-version fixation**, **compute**, and
**TMEM output visibility**. The experiments establish the logical distribution
of output regions and ordered B-version fixation; they do not directly expose
physical tensor-core partition wiring or individual SRAM transactions.

For one-CTA dense BF16 N256 K16, an N8×K16 B tile contains two K8×N8
128-byte halves. The working model reads those halves and supplies the
following logical output regions:

| mode / M | B tiles per local N8 step | region use | evidence |
|---|---:|---|---|
| AS / 128 | 1 | same B version in all four regions | complete final-D comparison after shared-B mutation |
| WS / 128 | 1 | same logical N tile in regions 0..3 | all tested final-version masks agree |
| WS / 64 | 2 | first N band → regions 0/1; second → 2/3 | one conflict-free 128B store produces OONN across writer mappings |
| WS / 32 | 4 | consecutive N bands → regions 0,1,2,3 | one such store produces ONNN, OONN, OOON in logical region order |

Here O/N denotes the old/new B version of the **modified elements**, read
from final D after MMA completion. Two physical read beats per tile and
broadcast to the listed regions remain a compatible model, not an exact
transaction-size or cycle-count measurement. In particular, pre-STS clocks
do not uniquely timestamp shared-store service.

## Evidence

### Logical output mapping, verified 2026-11-17

Let w be a physical 32-row TMEM region, l its lane, and c its local column.
For WS N256:

| M | active local width | logical M row | logical N column |
|---|---:|---|---|
| 32 | 64 | l | 64w+c |
| 64 | 128 | 32(w mod 2)+l | 128 floor(w/2)+c |
| 128 | 256 | 32w+l | c |

The [CUDA/PTX behavior study](tcgen05_ws_behavior.md) checks all nine legal
M32/64/128 × N64/128/256 combinations, nonuniform signed inputs,
overwrite/accumulate, four B IDs, and untouched TMEM guards. These are
logical mappings; no experiment independently numbers physical TC partitions.

### Input staging and four-region ordering, verified 2026-11-21

- [AS B-fetch tomography](tcgen05_as_b_fetch_tomography.md): identity A exposes
  individual B elements in all four regions. Wide-writer masks depend on lane
  assignment, so mask grouping alone does not establish physical fetch size.
- [AS B staging](tcgen05_as_b_staging.md): sparse columns share N8 input
  sensitivity groups; the two K8 halves have distinct sampled cutoffs.
  In 318 same-launch cases, LDS confirms new shared bytes before an LDTM
  still returns D sentinels, while final D uses old B. Input version is
  therefore fixed before output becomes visible.
- [WS shape comparison](tcgen05_ws_b_versions.md): completed-output version
  differences occur in M32 and cross-N M64 groups; M128 regions agree.
- [M64 single-store probe](tcgen05_ws_b_singlebeat.md): a scalar STS writes
  128B across 32 distinct banks, 64B per B tile. The anchor gives OONN in
  320/320 repetitions across both K halves and eight writer mappings.
- [M32 single-store probe](tcgen05_ws32_b_singlebeat.md): the same total write
  contributes 32B to each of four B tiles. Only NNNN/ONNN/OONN/OOON/OOOO
  appear. At fixed local N8 and K8..15, each of five selected timing states
  reproduces 320/320 across 16 writer mappings.

These final-output tests remove in-flight LDTM and D writeback ordering from
the version comparison. Mapping invariance strengthens the input-order
interpretation, while sparse perturbations still leave physical transaction
size and buffer topology unresolved.

### TMEM visibility, verified 2026-11-19

[AS snapshots](tcgen05_as_tmem_snapshot.md) and
[WS snapshots](tcgen05_ws_tmem_snapshot.md) expose partial D during one MMA,
with predominantly even-column boundaries and roughly two columns per cycle.
LDTM service itself has a matching two-column pattern, so these observations
are not an independent physical writeback-atomicity measurement.

[Matched WS M32/M64/M128 reads](tcgen05_ws_shape_visibility.md) each show
119/120 pre-read timestamp inversions at aligned frontier positions. The
reads overlap and preserve old-before-new post-issue/completion order.
This observable does not establish asynchronous physical writeback.

### Throughput and collectors, verified 2026-11-18

The [handwritten SASS study](tcgen05_ws_sass_throughput.md) reaches
4096 MAC/cycle/SM for M32N128/N256 and every tested M64/M128 shape with TMEM A
and B reuse. Collector-ID rotation independently removes discard penalties;
[all distinct ID pairs](tcgen05_ws_collector_conflicts.md) behave alike in
the tested conflict matrix. These timings do not assign IDs to subcores.

[WS source erasure](tcgen05_ws_collector_retention.md) demonstrates retention
of four complete distinct 8-KiB logical B tiles. The
[working-set study](tcgen05_ws_collector_capacity.md) adds throughput and
shared-contention checks; this is effective retained payload, not a direct
physical SRAM-size measurement.

[AS source erasure](tcgen05_as_collector_retention.md) instead returns the
erased source after completion/synchronization. Continuous AS reuse remains
beneficial across [intermediate commits without waits](tcgen05_as_collector_commit.md),
but its observable benefit decreases with [issue gaps](tcgen05_as_collector_gap.md).
[Residency isolation](tcgen05_as_collector_isolation.md) and
[legacy-HMMA controls](tcgen05_as_collector_hmma.md) constrain interference
explanations. [Cross-mode probes](tcgen05_collector_crossmode.md) show AS
instructions make retained WS B versions unavailable without identifying
physical storage aliasing.

## Reproduction and primary records

Each linked note preserves the accepted construction, numerical controls,
measured counts, interpretation limits, probe/runner/analyzer, and primary
record links. Compressed JSON records are lossless; see
[data/README.md](data/README.md) for extraction and provenance checks.
Timing claims are configuration-specific, and units are SM cycles unless
otherwise stated. No new GPU runs were needed for this editorial consolidation.

## History / retracted hypotheses

Consolidated on 2026-11-21 from the November B200 experiments. This edition
retains current findings and primary evidence.

## Open questions

- What physical read granularity and inter-tile capture interval implement the observed version ordering? <!-- open-question: open blocked-by "needs a physical store-service timing constraint or an independent transaction observable" -->
- Where are the staged B values and retained WS payload stored, and which regions share that storage? <!-- open-question: open blocked-by "logical version agreement and retained payload do not identify physical topology" -->
- What is the physical TMEM writeback granularity independent of LDTM service? <!-- open-question: open blocked-by "current in-flight reads conflate reader service with writeback visibility" -->
