# Same-launch AS/WS TMEM visibility across row regions

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-19
**Probe:** `tests/asm_construct/probe_sm100_tmem_cross_partition.py`
**Open items:** 1
**Audit:** 10240 full raw payloads validated; all six same-launch region pairs covered in both timing directions

## Conclusion

**Neither AS nor WS shows a same-column cross-region visibility inversion in
this simultaneous-observer scan.** Each mode has 4640 racing launches and
13920 pairwise co-observations, with zero start-order inversion candidates
and zero non-overlapping inversions. All six row-region pairs are covered,
including region 0, and every pair has non-overlapping reads in both orders.
Every region/column combination observes both old and new values.

This supports the current model's monotonic visibility prediction for the
tested M128N256K16 BF16 configuration. It does not prove identical physical
writeback instants across partitions or exclude unsampled timing windows.
The earlier separate-launch AS and WS scalar archives
each contain 12992 racing reads with no same-column cross-warp inversion or
equal-phase disagreement, but those comparisons do not establish synchrony
within one MMA execution.

The later [matched WS shape study](tcgen05_ws_shape_visibility.md) finds
pre-read timestamp inversions in **119/120** M128 races at columns 76/77,
with consecutive launches of the same shape. Thus the zero count here is
specific to this scan, not a general M128 exclusion. Those later candidates
still overlap and preserve old-before-new post-issue/completion ordering;
they do not establish physical writeback asynchrony. AS was not retested in
that shape comparison.

## Method

The shape remains one-CTA M128N256K16 BF16 to FP32, TMEM identity A, shared
B=1, overwrite D, initial `D[m,n]=-(n+1)`. WS uses buffer 0 discard without
KEEP/REUSE. All 32768 final D values are exported and validated on every
launch after completion. The probe derives from the accepted single-observer
snapshot generator and preserves its allocator, operand setup, epoch wait,
LDTM scoreboard wait, and conservative final readback.

Three observer warps read the **same column in the same launch**, each in its
own 32-row region. The fourth warp issues MMA. Producer role rotates through
warps 0..3, covering all six pairs of row regions, including region 0. The
TMEM allocation owner and epoch publisher remain warp 0. Warp/row-region
identities are observed; the experiment does not independently identify
physical tensor-core partition numbering.

Each observer preserves one scalar LDTM result for all 32 lanes and three
64-bit clock stamps: before LDTM, first instruction after LDTM issue, and
after the dependency wait. Results remain in registers until the final CTA
rendezvous. No observer-to-observer communication is inserted during the
timed window. Each observer also exports the common epoch, its target,
observed polling clock, and wait arithmetic for independent validation.

The first scan covers columns `0,1,64,128,192,240,250,254`, four producer
roles, AS and WS, and five skew assignments to the ordered observer list:
`(0,0,0),(-8,0,8),(8,0,-8),(-32,0,32),(32,0,-32)`. The target-time skews are
not asserted actual issue gaps: analysis uses the measured clock stamps.
There are 29 common fine pads (0..56 step 2) with nominal base delay
`16*floor(column/32)-32`. All 960 ordered controls (including every skew assignment) run before 9280
racing launches, for 10240 launches at one repetition.

### Falsification criteria

Comparisons use only one launch, one column, and equal scalar read widths.
For an all-new observation A and an all-old observation B:

1. `start(A) < start(B)` is a **start-order inversion candidate**. Read-side
   queuing/service can still reverse the actual sampling order.
2. `done(A) < start(B)` is a **non-overlapping visibility inversion**: A has
   returned new before B begins, yet B returns old. This is the stronger
   counterexample to common monotonic cross-region visibility.

Same-launch mixed old/new results without either ordering are ordinary
boundary crossings and are not automatically inversions. The analyzer also
counts ordered observations in both directions for each region pair;
absence of violations is meaningful only with adequate transition and
timing coverage. It does not infer physical writeback order solely from
LDTM issue order.

Controls: `none` replaces MMA with NOP and requires sentinel snapshots and
final D; `early` waits for all observers before MMA and requires old
snapshots; `late` waits for MMA completion before releasing observers and
requires new snapshots. Both enabled controls require final D=1 everywhere.

## Evidence

A [WS M32 follow-up](tcgen05_ws32_tmem_cross_partition.md) finds repeatable
pre-read timestamp inversions in overlapping reads, while post-issue,
completion, and non-overlapping inversion criteria remain negative. Its
same-local-column comparisons cross distinct logical N bands, unlike M128's
same-logical-column row-region comparisons here.

All eight AS/WS × none/early/late/race kernels pass full sm100a assembly with
strict dependency checking (only the inherited `sb_capacity` advisory is
accepted). The none variants are byte-identical. Each enabled AS/WS pair
differs at exactly one instruction, high-word XOR `0x80000` (mode bit 83),
with unchanged length and scheduling. The accepted revision has 1109
instructions for none/race and 1115 for early/late; it retains and exports
all four skew operands plus the selected value for exact per-warp validation.

### B200 scan, verified 2026-11-19

The [accepted result](data/tcgen05_tmem_cross_partition_scan_v2_20261119/result.json.gz)
was collected on driver 610.57.04, app `ap-kDJ34cNnvlTLfhirXXcuAs`, which
started after 9.76 seconds. All 10240 launches (960 controls and 9280 races)
pass complete raw-buffer validation: zero final-D errors, control errors,
unexpected snapshot values, or within-warp row disagreements. Every epoch,
delay selection, target-clock calculation, and ordered-control relation
also passes.

| measured quantity | AS | WS |
|---|---:|---:|
| racing launches | 4640 | 4640 |
| all three observers old | 1516 | 1516 |
| all three observers new | 572 | 572 |
| mixed old/new observers in one launch | 2552 | 2552 |
| pairwise co-observations | 13920 | 13920 |
| start-order inversion candidates | 0 | 0 |
| non-overlapping inversions | 0 | 0 |
| equal-start old/new disagreements | 0 | 0 |
| non-overlapping read pairs | 5628 | 5628 |
| non-overlapping old then new | 3953 | 3953 |
| non-overlapping old then old | 1366 | 1366 |
| non-overlapping new then new | 309 | 309 |

The 2552 mixed launches per mode demonstrate transition coverage, rather
than observations only before or after the update. All mixed observations
have old at the earlier pre-read timestamp and new at the later timestamp.
The 309 non-overlapping new-then-new comparisons per mode directly exercise
the stronger criterion: a new value has already returned before the other
region starts reading, and the later read also returns new.

Each region pair has 2320 co-observations per mode. The following counts are
identical in AS and WS; A/B denote the lower/higher warp index in each pair.

| row-region pair | mixed old/new | done(A) < start(B) | done(B) < start(A) |
|---|---:|---:|---:|
| 0–1 | 832 | 740 | 143 |
| 0–2 | 1007 | 745 | 301 |
| 0–3 | 1072 | 683 | 573 |
| 1–2 | 535 | 273 | 387 |
| 1–3 | 978 | 294 | 736 |
| 2–3 | 680 | 192 | 561 |

For all 5120 matched AS/WS configurations (including controls), snapshot
values, all three read-start phases, and all three read durations match
exactly. Absolute clock values differ across launches as expected.

One common AS/WS example uses column 128, producer warp 0, pad 40, and
skews `[0,32,0,-32]`. Relative to the first post-MMA timestamp:

| observer | pre-read | post-issue | result wait complete | value |
|---|---:|---:|---:|---|
| warp 3 | +44 | +50 | +69 | old (−129) |
| warp 2 | +91 | +97 | +115 | new (1) |
| warp 1 | +144 | +150 | +168 | new (1) |

Warp 2 has returned new before warp 1 starts; warp 1 also sees new. The
earlier warp-3 old value is consistent with a monotonic update, not an
inversion. [Timeline](data/tcgen05_tmem_cross_partition_scan_v2_20261119/ordered_example.svg)
· [example records](data/tcgen05_tmem_cross_partition_scan_v2_20261119/ordered_example.json)
· [complete summary](data/tcgen05_tmem_cross_partition_scan_v2_20261119/summary.json).

Runner: `tools/modal_tmem_cross_partition.py`, with durable spawned call,
source snapshots, dependency hashes, faulthandler, and compressed complete
raw device buffers. Analyzer: `tools/analyze_tcgen05_tmem_cross_partition.py`.
Each result includes the producer clock stamps, three observer records,
per-launch comparisons, and compressed raw output for offline revalidation.

Related: [AS snapshots](tcgen05_as_tmem_snapshot.md),
[WS snapshots](tcgen05_ws_tmem_snapshot.md).

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Does this monotonic visibility result extend to unsampled columns, finer timing windows, other shapes/types, or collector reuse sequences? <!-- open-question: open blocked-by "blocker (inferred): requires additional same-launch scans beyond this M128N256K16 BF16 buffer-0-discard experiment" -->
