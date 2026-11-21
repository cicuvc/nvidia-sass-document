# WS M32 visibility ordering across four N chunks

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-19
**Probe:** `tests/asm_construct/probe_sm100_ws32_tmem_cross_partition.py`
**Open items:** 1
**Audit:** 28640 raw payloads validated; 63 repeatable overlapping start-order candidates, zero post-issue/completion/non-overlapping inversions

## Conclusion

**WS M32 exhibits repeatable pre-read timestamp inversions, but no
non-overlapping visibility inversion in these scans.** The initial three
and focused 60 candidates all have the same
measured timeline: chunk 3 starts at +45 and returns new at +81; chunk 0
starts at +47 and returns old at +79. Their reads overlap and their
post-issue/completion ordering is the reverse of their pre-read ordering.
This is not yet evidence of independently delayed physical writeback.
Six focused configurations reproduce the pattern in all ten repetitions
each. Across 28640 validated launches, the stronger post-issue, completion,
and non-overlapping inversion counts remain zero. All sampled chunks can
share one old/new threshold per local column when classified by the
post-issue timestamp, making read-side timing a viable explanation.

Unlike M128, comparing
the same physical column offset across chunks does **not** compare the same
logical output column: M32 partitions N across the chunks. A positive result
would therefore demonstrate different N-chunk progress, not automatically
an architectural memory-order violation.

The [matched WS shape follow-up](tcgen05_ws_shape_visibility.md) reproduces
this exact clock pattern in M32, M64, and M128, each in 119/120 racing
launches, by choosing columns with aligned visibility frontiers. The
pre-read inversion is therefore not unique to M32 or to comparisons across
different logical N bands: the M128 witnesses compare row regions of the
same logical column. The overlapping-read limitation remains unchanged.

## Method

Shape: one CTA, WS M32N256K16 BF16 to FP32, TMEM A, shared B, overwrite D,
buffer 0 discard without KEEP/REUSE. The established WS mapping is
`logical_m=lane`, `logical_n=64*warp+c`, where `0<=c<64`. Physical columns
64..255 in each chunk are outside the output footprint and must retain
their initialized sentinels. See [verified WS mapping](tcgen05_ws_behavior.md).

The source derives from the accepted [M128 simultaneous-observer
probe](tcgen05_tmem_cross_partition.md). Changes to the timed MMA are its M
descriptor field; observer scheduling, timestamp collection, dependency
waits, and producer-role rotation are retained. Input setup gives the four
shared B N64 bands exact BF16 values 1,2,3,4. Repeated I16 blocks in A make
each active output in physical chunk w equal to `w+1`, independently of its
row and local column. These tags check that all four chunks contain the
expected logical N bands. Initial D is `-(c+1)` across all 256 physical
columns. All 32768 physical D values are validated after each launch.

Every launch has one producer and three observer warps. Producer rotates
through 0..3, covering all six chunk pairs. Each observer reads one scalar
LDTM at the same local column c and retains all 32 lane values. Each records
pre-read, first post-issue, and post-dependency-wait clock stamps, plus epoch,
delay arithmetic, all four requested skew parameters, and its selected skew.
Snapshots are exported only after final CTA rendezvous. No new observer
communication is introduced during the race.

The scan has local columns `0,1,16,31,32,47,62,63`, four producer choices,
five skew assignments `(0,0,0),(-8,0,8),(8,0,-8),(-32,0,32),(32,0,-32)`,
four base delays `-64,0,64,128`, and 29 fine pads `0..56 step 2`. This gives
18560 racing launches. First, 480 controls cover every column, producer, and
skew assignment with no-MMA, completed-read-before-MMA, and
completed-MMA-before-read ordering. One repetition totals 19040 launches.

The analyzer compares freshness categories (sentinel versus chunk-specific
new value), not numerical magnitudes across chunks. For new observation A
and old observation B in the same launch/local column:

- `start(A)<start(B)` is an apparent start-order inversion, which can still
  include read-service differences.
- `done(A)<start(B)` is the stronger non-overlapping visibility difference:
  one chunk has returned new before another starts reading and returns old.

Actual timestamps determine these relations, not requested delays. Any
candidate must pass tagged final-output and control checks before being
interpreted. Negative results require both old/new transition coverage and
ordered comparisons in both directions for every chunk pair.

## Evidence

All four none/early/late/race variants pass full sm100a assembly with strict
dependency checking; only the inherited `sb_capacity` advisory is accepted.
The common runner/inspector were parameterized with default-preserving
hooks; the archived 10240-launch M128 result passes full offline regression.

### Initial scan, verified 2026-11-19

The [result](data/tcgen05_ws32_tmem_cross_partition_scan_20261119/result.json.gz)
contains all 19040 launches (480 controls, 18560 races), with zero control,
final-output, unexpected-value, row-disagreement, or parameter/timestamp
validation errors. First allocation started in 7.01 seconds, app
`ap-7jI6bs2teeiHRxZk1xFQRa`. Every chunk/local-column combination has both
old and new observations. Each of the six chunk pairs has 9280 simultaneous
co-observations and non-overlapping reads in both directions.

| observation | count |
|---|---:|
| all observers old | 5711 |
| all observers new | 9797 |
| mixed old/new launches | 3052 |
| pre-read timestamp inversion pairs | 3 |
| post-issue timestamp inversion pairs | 0 |
| completion timestamp inversion pairs | 0 |
| non-overlapping new then old | 0 |
| non-overlapping old then old | 6309 |
| non-overlapping old then new | 4902 |
| non-overlapping new then new | 11291 |

The three candidates all use producer warp 2, local column 32, base delay 0,
pad 28, and the observer-skew triples `(0,0,0)`, `(-8,0,8)`, `(8,0,-8)`.
The actual measured timestamps are identical despite the different requested
skews; these are three configurations, not three independent timing windows.

| observer | logical n | pre-read | post-issue | result wait complete | value |
|---|---:|---:|---:|---:|---|
| warp 1 | 96 | +33 | +47 | +65 | old, −33 |
| warp 3 | 224 | +45 | +63 | +81 | new, 4 |
| warp 0 | 32 | +47 | +61 | +79 | old, −33 |

The actual LDTM issue is bracketed by the first two timestamps: `[45,63]`
for the new observation and `[47,61]` for the old observation. These windows
overlap, so pre-read timestamps alone do not establish the LDTM issue or
TMEM sampling order. In particular, the new observation's post-issue and
completion timestamps are both later than the old observation's. Read-side
timing remains a viable explanation; zero strong witnesses does not prove
physical writeback simultaneity.

[Timeline](data/tcgen05_ws32_tmem_cross_partition_scan_20261119/overlapping_candidate.svg)
· [raw-derived summary](data/tcgen05_ws32_tmem_cross_partition_scan_20261119/summary.json).

The focused follow-up keeps the kernel generator unchanged, selects local
columns 31/32/33 and producer warps 1/2 (both permit observing chunks 0 and
3), scans all five skews and 29 pads at base delay 0, and repeats every
configuration ten times: 900 controls plus 8700 races, 9600 launches total.

### Focused repeats, verified 2026-11-19

The [accepted follow-up](data/tcgen05_ws32_tmem_cross_partition_focus_recovery_20261119/result.json.gz)
completed all 9600 launches on driver 610.57.04, app
`ap-iP62dDU8vkKTS9fuIEWPfq` (9.01-second allocation). Every full raw payload
passes control/final-output/value/timing validation. No within-warp row
disagreement occurs. All sampled chunk/column combinations include old and
new observations.

The six candidate configurations are producer 2, local column 32 **or 33**,
base delay 0, pad 28, and each of the three small-skew assignments above.
Every configuration reproduces the same timestamp/freshness pattern in
**10/10 repetitions**, for 60 candidates. Their post-issue and completion
orders remain old before new. Local column 33 changes the old sentinel to
−34 and the logical columns to 33/97/225, preserving the same timing.

| measured quantity | initial scan | focused repeats | combined |
|---|---:|---:|---:|
| validated launches | 19040 | 9600 | 28640 |
| controls | 480 | 900 | 1380 |
| races | 18560 | 8700 | 27260 |
| pre-read timestamp inversion pairs | 3 | 60 | 63 |
| post-issue timestamp inversion pairs | 0 | 0 | 0 |
| completion timestamp inversion pairs | 0 | 0 | 0 |
| non-overlapping new then old | 0 | 0 | 0 |
| non-overlapping read pairs | 22502 | 10528 | 33030 |

The focused run contains 5399 mixed-old/new launches, 1570 all-old launches,
and 1731 all-new launches. Its non-overlapping pairs are 1639 old→old,
7859 old→new, and 1030 new→new. Across both scans there are 12321
non-overlapping new→new pairs and no new→old pair.

### Common thresholds using the post-issue timestamp

Pool all observer chunks, producer roles, requested delays, and repetitions
within each local column. The post-issue timestamp minus the post-MMA stamp
has disjoint old/new ranges:

| local column | latest old | earliest new |
|---|---:|---:|
| 0, 1 | +29 | +30 |
| 16 | +45 | +46 |
| 31 | +56 | +57 |
| 32, 33 | +61 | +62 |
| 47 | +72 | +73 |
| 62, 63 | +89 | +90 |

Column 33 is supplied by the focused run; columns 31/32 have identical
bounds in both runs. Thus the candidates do not require chunk-specific
visibility thresholds under this measured clock convention. The timestamp
still brackets instruction issue rather than identifying the SRAM sample
or physical writeback cycle, so this consistency does not prove that all
partitions write simultaneously. In particular, overlapping reads cannot
exclude a small physical lag shorter than the observation windows.

Focused [summary](data/tcgen05_ws32_tmem_cross_partition_focus_recovery_20261119/summary.json)
and all candidate records are retained for further interpretation.

Probe: `tests/asm_construct/probe_sm100_ws32_tmem_cross_partition.py`.
Remote runner: `tools/modal_ws32_tmem_cross_partition.py`. Full raw-buffer
validator: `tools/analyze_tcgen05_ws32_tmem_cross_partition.py`.
The runner retains the minimal/accepted/new loader preflight and durable
spawned call plus source/dependency snapshots.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Can a tighter issue/sample-time observation distinguish a small physical inter-chunk lag from read-service timing within the overlapping candidate windows? <!-- open-question: open blocked-by "blocker (inferred): requires a probe that bounds sampling more tightly than the current pre/post-issue clocks" -->
