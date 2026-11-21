# WS M128 in-flight TMEM column visibility

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-19
**Probe:** `tests/asm_construct/probe_sm100_ws_tmem_snapshot.py` on Modal NVIDIA B200
**Open items:** 1
**Audit:** 22685 WS launches validated; three-warp scalar frontiers and x2 reads compared with complete AS references

## Conclusion

**WS M128N256K16 BF16 reproduces the two-column-aligned TMEM visibility
frontier previously observed in AS.** Three observer warps together yield
64 adjacent old/new frontiers, all at even columns (39/11/14 for warps 1/2/3).
All 256 warp-1 per-column latest-old/earliest-new brackets match the archived
AS run exactly; the additional warps reproduce the same progression.
The two-column progression is an observable of ordinary LDTM during MMA;
it is not independently established physical writeback atomicity.

For 7422 of 7424 WS scalar racing samples, the same AS empirical rule holds:

```text
new iff phase >= 18 + floor(column / 2)
phase = pre-LDTM clock - first post-MMA clock
```

The two exceptions are also the same: columns 254/255 remain old at +145
and are first sampled new at +148. The data therefore support the same
approximate two-columns/cycle progression, including its observed tail
exception, in this AS/WS comparison.

Across all three warps, 12988 of 12992 scalar racing samples follow this rule.
The additional exceptions are warp 3's columns 250/251 at +143, also observed
in AS. All 7395 racing x2 reads are entirely old or entirely new, and the
same reader-service effect seen in AS persists: 44 matched-phase comparisons
split new/old with separate scalar reads but return both new in an x2 read.

This experiment fixes M=128, N=256, K=16, BF16×BF16→FP32, one CTA,
TMEM A and shared B, overwrite D, and WS buffer 0 discard (no KEEP/REUSE).
It does not generalize the measured timing to WS M32/M64, other types/shapes,
or collector reuse sequences. In particular, smaller-M WS has a different
logical N-to-physical-TMEM-column mapping.

## Evidence

### Same-launch cross-region ordering follow-up

A [simultaneous-observer scan](tcgen05_tmem_cross_partition.md) now rotates
MMA production through all four warps and reads the same column from the
other three row regions in each launch. Across 4640 races per mode, all six
region pairs have 2320 co-observations each. Neither AS nor WS shows a later
pre-read timestamp returning old after an earlier read returns new; the
stronger completed-new-before-later-old criterion also has zero witnesses.
Every region/column combination crosses old and new, and each mode includes
5628 non-overlapping read pairs. This supports monotonic observed visibility
within the tested configuration without proving identical physical writeback
instants across all partitions.

### Single-bit mode comparison

The WS source delegates to the accepted AS generator and replaces only
`UTCHMMA.1CTA` with `UTCHMMA.1CTA.WS`. Identity A, constant B=1, initial
`D[m,n]=-(n+1)`, clocks, delay arms, barriers, observer read, and final
128×256 readback are otherwise unchanged.

Full sm100a assembly and strict dependency checking pass. Comparing encoded
instruction streams for the four scalar warp-1 variants gives:

| control mode | changed instructions | encoded XOR |
|---|---:|---|
| no MMA | 0 | identical streams |
| early | 1, target MMA | low64=0, high64=0x80000 |
| late | 1, target MMA | low64=0, high64=0x80000 |
| race | 1, target MMA | low64=0, high64=0x80000 |

Thus the active kernels differ only in instruction bit 83; code length and
all scheduling control fields match. The 12 additional granularity variants
also pass full assembly and strict dependency checking; only the existing
`sb_capacity` conservative CFG advisory is allowed.

### Every-column scalar sweep

The [columns run](data/tcgen05_ws_tmem_columns_run2_20261119/result.json.gz)
completes **8192 launches**: 768 controls and 7424 races. All 256 columns are
read individually by warp 1, with 29 pad settings per column. Full payload
validation finds zero final/control errors, unexpected values, or lane
disagreements. No scalar sample contains a mixture across its 32 lanes.

Comparing independent launches at the same measured phase finds:

| phase | last new column | first old column |
|---:|---:|---:|
| +19 | 3 | 4 |
| +23 | 11 | 12 |
| +30 | 25 | 26 |
| +31 | 27 | 28 |
| +34 | 33 | 34 |
| +87 | 139 | 140 |
| +137 | 239 | 240 |
| +145 | 253 | 254 |

All 39 adjacent frontiers are even aligned. A fitted intercept search selects
18 for `phase-floor(column/2)`, with two tail misclassifications; the AS
intercept was not assumed as a requirement for accepting the WS run.

The archived AS reference is
[`tcgen05_as_tmem_snapshot_columns_20261119`](data/tcgen05_as_tmem_snapshot_columns_20261119/result.json.gz).
Comparing all 8192 identical launch configurations gives:

| comparison | different samples |
|---|---:|
| complete final D payload | 0 |
| complete snapshot payload | 0 |
| old/new/other counts | 0 |
| producer completion interval | 0 |
| pre-read phase | 512 |
| measured read interval | 1 |
| per-column latest-old/earliest-new bracket | 0 of 256 |

The phase differences are 256 no-MMA controls (+5), 255 late controls (−52),
and one race (+5); that race's read interval also differs by +5. These
scheduling differences do not change any returned version or boundary.
The comparison is across runs, not two modes executed simultaneously on the
same GPU. All accepted runs report NVIDIA B200 with driver 610.57.04.

[Full analysis and AS comparison](data/tcgen05_ws_tmem_columns_run2_20261119/analysis.txt) ·
[column threshold plot](data/tcgen05_ws_tmem_columns_run2_20261119/columns.svg) ·
[matched-phase frontier map](data/tcgen05_ws_tmem_columns_run2_20261119/columns_frontiers.svg).

### Cross-warp and x2 confirmation

The preserved [granularity retry](data/tcgen05_ws_tmem_granularity_retry_20261119/result.json.gz)
completed **14304 launches**: 1341 controls and 12963 races. It adds scalar
reads by warps 2 and 3 at columns 0..31, 112..143, and 224..255, plus warp-1
x2 reads starting at every column 0..254. All final D elements, snapshots,
timestamps, control coverage, and sample identities pass offline validation.
There are no unexpected values, control/final errors, or lane disagreements.

| observer / read | racing samples | adjacent matched-phase frontiers | odd-column frontiers | exceptions to pair rule |
|---|---:|---:|---:|---:|
| warp 2, scalar | 2784 | 11 | 0 | 0 |
| warp 3, scalar | 2784 | 14 | 0 | 2 |
| warp 1, x2 | 7395 | not a simultaneous scalar map | not applicable | 1 |

Fitting the pair-rule intercept independently selects 18 in all three groups.
Warp 3's exceptions are columns 250/251 still old at +143; x2's exception is
start column 254 at +145, both values old. These are exactly the corresponding
AS exceptions. No x2 read is mixed, including odd starts crossing an
even-aligned pair boundary.

Comparing with the corresponding
[AS granularity run](data/tcgen05_as_tmem_snapshot_granularity_recovered_20261119/result.json.gz):

- All 14304 complete final D payloads and producer completion intervals agree.
- Snapshot values differ in two racing configurations, both with different
  measured read phases; all 12960 races with matched configuration **and**
  phase have identical snapshot payloads.
- The differing scalar configuration is warp 2, column 0, pad 0: AS reads
  at −22 and gets old, WS at +20 and gets new. The differing x2 configuration
  is warp 1, start 0, pad 0: AS at −20 gets both old, WS at +18 gets both new.
  Both outcomes agree with the same phase-dependent pair rule.
- A third race, warp 3 / column 0 / pad 0, moves from −13 to −34 and remains
  old. All three phase differences occur at the first race of their kernel
  variant; the data do not establish the cause of the scheduling difference.
- Warp 2 has one changed bracket: column 0 changes from (17,21] in AS to
  (17,20] in WS because of the added +20 new sample. Its other 95 brackets
  agree. All 96 warp-3 brackets agree.

The WS scalar reference supplies **44** matched-phase cases with scalar(c)
new and scalar(c+1) old, while x2(c,c+1) returns both new. This reproduces
the AS reader dependence rather than establishing a snapshot of an atomic
two-column write. All 1341 controls also fit the same measured read interval:
scalar 24 cycles for either parity; x2 24 cycles for even starts and 25 for
odd starts. Clock and wait overhead are included in those intervals.

Together with 189 ordered controls and the 8192-column suite, the accepted
WS total is **22685 launches**. The earlier signal-11 run is excluded.

[Full validation and comparisons](data/tcgen05_ws_tmem_granularity_retry_20261119/analysis.txt) ·
[exact differing configurations](data/tcgen05_ws_tmem_granularity_retry_20261119/as_comparison_details.json) ·
[warp-2 thresholds](data/tcgen05_ws_tmem_granularity_retry_20261119/confirmation_warp2.svg) ·
[warp-3 thresholds](data/tcgen05_ws_tmem_granularity_retry_20261119/confirmation_warp3.svg).

## Method and limitations

The wrapper changes only the target mode. The shared host runner accepts a
source factory and records `experiment=ws`; it otherwise uses the same
allocation, launch, snapshot export, validation, and result format as AS.
Global snapshot stores remain after final CTA rendezvous. The observer waits
on its own LDTM scoreboard, not on MMA completion during a race.

The analysis uses actual read-start and completion timestamps. A matched-phase
column map combines independent launches and is not an instantaneous matrix
snapshot. LDTM has its own service timing, and the prior AS work showed that
wide reads can conceal a moving boundary. The single-bit AS/WS equivalence
therefore establishes equivalence of this measured visibility behavior,
without removing the read-side interpretation limit.

Runner: `tools/modal_ws_tmem_snapshot.py`. Analyzer:
`tools/analyze_tcgen05_as_tmem_snapshot.py RESULT --compare-as AS_RESULT --plot STEM`.
Both referenced result files undergo full payload validation before comparison.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Does the common two-column AS/WS visibility pattern represent the physical
  writeback transaction, or a combination of producer updates and LDTM
  service/banking? How does it change for other WS shapes and collector modes?
  <!-- open-question: open blocked-by "needs independent read-side timing discrimination and explicit smaller-M or collector-reuse probes" -->
