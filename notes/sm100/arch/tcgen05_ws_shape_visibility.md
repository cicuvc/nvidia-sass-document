# Matched WS M32/M64/M128 visibility timing

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-19
**Probe:** `tests/asm_construct/probe_sm100_ws_shape_visibility.py`
**Open items:** 1
**Audit:** 120060 full raw payloads validated; frontier-matched M32/M64/M128 each reproduce 119/120 pre-read inversions with identical timelines

## Conclusion

**All three WS shapes exhibit the same overlapping pre-LDTM timestamp
inversion when their sampled columns have aligned update frontiers.** M32
c32/33, M64 c72/73, and M128 c76/77 each give119/120 candidates. All357
share the same clocks: warp3 pre45/post63/done81 returns new; warp0
pre47/post61/done79 returns old. Post-issue and completion order remain
old before new, so the observation does not establish physical writeback
asynchrony. The targeted batch has no non-overlapping racing read pairs.

The complementary [final B-version experiment](tcgen05_ws_b_versions.md)
and [single-store M64](tcgen05_ws_b_singlebeat.md)/[M32](tcgen05_ws32_b_singlebeat.md)
probes compare completed outputs and establish input-version ordering
without relying on in-flight LDTM timestamps.

## Method

One CTA, WS M={32,64,128}, N256 K16 BF16 to FP32, TMEM A, shared B,
overwrite D, buffer 0 discard. All shapes use exactly the same source
layout and scheduling except the M field loaded into UR15. The common
input setup has repeated I16 blocks in A and B values 1/2/3/4 in successive
N64 bands. Final values therefore identify logical N bands. Every physical
D value is checked, including sentinels outside each shape's footprint.

For warp w, lane l, physical local column c, and W=M*N/128:

| M | W | logical row | logical column |
|---|---:|---|---|
| 32 | 64 | l | 64w+c |
| 64 | 128 | 32(w mod 2)+l | 128 floor(w/2)+c |
| 128 | 256 | 32w+l | c |

Old values are `-(c+1)`; active new values are
`1+floor(logical_column/64)`. All shapes initialize all four 256-column
physical regions, and only c<W may change. Comparing chunks at the same c
has shape-dependent logical meaning: M32 crosses N bands, M64 has both row
and N-band pairs, M128 compares row regions of the same logical column.

Each launch rotates the producer among warps 0..3 and lets the other three
warps read the same c. The common scalar LDTM sequence records pre-read,
first post-issue, and result-wait-complete clocks. Observer payloads remain
in registers until the final CTA rendezvous. Exact skew-parameter, epoch,
and wait-arithmetic readbacks are retained from the corrected M128/M32 probe.

The broad scan uses common c=`0,1,16,31,32,33,47,62,63`, all four producer
choices, five observer skew patterns, base delays `-64,0,64`, and 29 fine
pads `0..56 step 2`. Shapes are interleaved for each configuration in one
remote task. All controls precede races. At one repetition, each shape has
540 controls and 15660 races; the total is 48600 launches across 12 kernel
variants. A focused suite additionally supports c=31/32/33, producer 1/2,
base delay 0, and the same skews/pads for repeated candidate verification.

The `blocked` suite has the exact same configuration set and device source
as `scan`; only host order changes to group each mode by M. All controls
still precede races. The `relative` follow-up probes c=M−1/M/M+1 in each
shape (midpoint of its 2M active physical columns), with all producers/skews,
four base delays −64/0/64/128, and 29 pads. It requests 21420 launches,
including 540 controls. All 21420 launches are now validated.

A `match` suite tested the prediction that M64 c72/73 and
M128 c76/77 have the same observed post-issue frontier interval as M32 c32/33. It fixes
producer 2, pad 28, three small-skew assignments and base delay 0, with
three ordered control modes. At 20 repetitions its 72 configurations give
1440 launches, now fully validated. The column choices and expected example
were recorded before collecting this result. The extrapolated frontier was
never a correctness requirement; actual timestamps and values determine
the outcome independently.

The analysis keeps four separate inversion criteria for a new observation A
and old observation B within the same launch and local column:

- pre-read order: start(A)<start(B);
- post-issue order: post(A)<post(B);
- completion order: done(A)<done(B);
- non-overlapping visibility: done(A)<start(B).

Positive or negative outcomes are recorded without assuming the prediction.
No finite negative scan establishes that M128 can never exhibit the pattern.

## Evidence

All 12 variants pass full sm100a assembly with strict dependency checking;
only the inherited `sb_capacity` advisory is accepted. None/race kernels
have 1129 instructions, early/late kernels 1135. For every ordering mode,
M32 versus M64 and M32 versus M128 differ at exactly instruction index 531,
the UR15 descriptor load: low-word XOR `0x600000000000000` and
`0xa00000000000000` respectively, high-word XOR zero. No MMA modifier,
observer instruction, layout, or scheduling bit changes between shapes.

Runner: `tools/modal_ws_shape_visibility.py`. Validator:
`tools/analyze_tcgen05_ws_shape_visibility.py`. These retain full compressed
raw outputs, source snapshots, dependency hashes, loader preflights, and a
durable Modal call ID. Earlier archived results are not counted as new
matched measurements.

### Scan controls, verified 2026-11-19

Two full48600-launch scans use identical case sets and SASS, varying only
host launch order. Interleaving M modules yields246/233/238 pre-read
candidate launches for M32/M64/M128; grouping launches by shape yields6/0/0.
All post-issue, completion, and non-overlapping inversion counts are zero.
This demonstrates that column choice and issue/service windows matter.

The21420-launch relative-position scan covers c=M-1/M/M+1 and supplies
8437 non-overlapping read pairs per shape, with no inversion. Every sampled
region/column sees both old and new. The measured frontiers differ by shape,
which motivates comparing aligned frontier times in the main repeated test.

Primary records: [interleaved](data/tcgen05_ws_shape_visibility_scan_20261119/result.json.gz),
[grouped](data/tcgen05_ws_shape_visibility_blocked_20261119/result.json.gz),
[relative positions](data/tcgen05_ws_shape_visibility_relative_recovery_retry_20261119/result.json.gz).

### Frontier-matched repetitions, verified 2026-11-19

The [accepted matched result](data/tcgen05_ws_shape_visibility_match_recovery2_20261119/result.json.gz)
completed on driver 610.57.04, app `ap-M6sWKUadEg5zNC0NHG1KmA`, starting
after 14.26 seconds. All 1440 raw buffers pass: 1080 controls plus 360
racing launches, with zero final-D, control, unexpected-value, row-agreement,
skew-selection, or timestamp errors. Consecutive launches reuse one shape's
kernel; the next shape is selected only after the current group finishes.

| M | local columns | pre-read inversion launches | post-issue / completion / non-overlapping inversions |
|---|---|---:|---|
| 32 | 32,33 | 119 / 120 | 0 / 0 / 0 |
| 64 | 72,73 | 119 / 120 | 0 / 0 / 0 |
| 128 | 76,77 | 119 / 120 | 0 / 0 / 0 |

Each shape has six configurations: two columns times three skew assignments,
each repeated 20 times. The first column with zero skews gives 19/20
candidates; all other five configurations give 20/20. The sole noncandidate
per shape is its first racing invocation, and all observers return new:
warp 0 clocks `64/135/153`, warp 1 `62/137/155`, warp 3 `70/141/159`
(pre-read/post-issue/post-wait, relative to post-MMA). These samples remain
in the reported totals; no warm-up observations were discarded. Their
longer clock gaps are measured, without assigning a specific frontend cause.

All remaining 119 observations per shape share this exact timeline:

| observer | pre-read | post-issue | post-wait | freshness |
|---|---:|---:|---:|---|
| warp 1 | +33 | +47 | +65 | old |
| warp 3 | +45 | +63 | +81 | new |
| warp 0 | +47 | +61 | +79 | old |

For first-column examples, M32 old is −33 and warp-3 new is 4; M64 old is
−73 and warp-3 new is 4; M128 old is −77 and new is 2. In M128 the observers
read different row regions of the **same logical column 76**, whereas the
M32 and cross-N M64 comparisons involve different logical N bands.

The sampled post-issue boundary is `(61,63]` for all six selected columns.
This is compatible with the beforehand prediction around +62, but the
matched run does not itself sample +62 and cannot establish that exact
threshold or a physical writeback cycle. It does directly establish that
the same pre-read inversion is reproducible in M128 once the selected
column's update falls between the relevant read windows.

There are 119 mixed-old/new and one all-new racing launch per shape, zero
all-old launches, and **zero non-overlapping racing read pairs**. The
ordered controls separately validate old and new for all observer regions.
This targeted test resolves the shape-exclusion prediction for the
observable; it is not a new non-overlap test of physical synchronization.

[Three-shape timeline](data/tcgen05_ws_shape_visibility_match_recovery2_20261119/matched_timeline.svg)
· [example records](data/tcgen05_ws_shape_visibility_match_recovery2_20261119/matched_timeline.json)
· [full summary](data/tcgen05_ws_shape_visibility_match_recovery2_20261119/summary.json)
· [prediction recorded before outcome](data/tcgen05_ws_shape_visibility_match_recovery2_20261119/prediction.json).

The four accepted shape-comparison batches total 120060 launches: 48600
interleaved, 48600 blocked, 21420 relative-position, and 1440 matched.
All requested analysis is complete and no remote task remains outstanding.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Can a tighter sampling-time probe distinguish a small physical writeback skew from read-side timing within the overlapping windows? <!-- open-question: open blocked-by "blocker (inferred): requires an observation that constrains TMEM sampling more tightly than the current pre/post-issue clocks" -->
