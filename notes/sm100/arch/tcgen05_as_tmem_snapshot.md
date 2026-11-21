# Timed LDTM snapshots during one AS UTCHMMA

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-19
**Probe:** `tests/asm_construct/probe_sm100_as_tmem_snapshot.py` on Modal NVIDIA B200
**Open items:** 1
**Audit:** full coarse/fine/paired/alignment/columns/granularity payloads checked; three-warp even-column frontiers and reader timing controls

## Conclusion

**Ordinary LDTM observes spatially partial D updates from a single AS
M128 × N256 × K16 BF16 UTCHMMA.** In 211 launches, a scalar read of column 0
returns the new value and completes its scoreboard wait, then a later scalar
read of column 240 still returns the old value. Both finish before the
producer's completion-wait timestamp. All 32 lanes agree, and all three
observer warps reproduce the result. This rules out one simultaneous whole-D
visibility switch as the explanation for these ordered observations.

An every-column scalar sweep and two-warp follow-up find **64 matched-phase
adjacent old/new frontiers, all at even columns**. In the warp-1 data,
7422/7424 racing samples fit
`new iff phase >= 18 + floor(column/2)`, where phase is the pre-LDTM timestamp
relative to the first post-MMA timestamp. The last pair, columns 254/255,
switches later than that fitted rule. This narrows the observed column
grouping to pairs and suggests a frontier advancing about two columns/cycle;
it does not establish physical atomic writeback size.

Reader timing has the same two-column structure. Across all three new suites,
2658 ordered controls fit `read_interval = 24 + floor((column%2 + width-1)/2)`.
Moreover, 44 matched-phase comparisons where separate scalar reads split
new/old instead give **both new** in one x2 read. The LDTM service window is
therefore material to interpreting a returned wide vector.

Neither the coarse nor fine sweep captures a mixture inside one contiguous
x1/x2/x16 read. The positive result comes from **two explicitly ordered scalar
reads within one launch**, not from claiming an atomic wide snapshot.
A mixture within a wide LDTM is not automatically a simultaneous spatial
snapshot: the reader itself may service several columns at different times.

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

The [WS M128 comparison](tcgen05_ws_tmem_snapshot.md) changes only the target
MMA's WS mode bit and reproduces the two-column progression across three
observer warps. All 64 matched-phase adjacent frontiers are even aligned;
matched-configuration/matched-phase AS and WS confirmation snapshots agree.
WS also reproduces the x2 reader-service effect, so the physical writeback
atomicity limitation applies to both modes.

The subsequent [B-staging probe](tcgen05_as_b_staging.md) compares these output
frontiers with sparse shared-B input-version cutoffs and adds a same-launch
LDS-confirmed witness of new shared B followed by a still-sentinel D read and
an old-B final result. Its input cutoff progresses about twice as fast along
N as the output-visibility frontier; this does not locate the intervening
operand/result storage.

### Scalar scan: even-column frontiers and approximately two columns per cycle

The [columns run](data/tcgen05_as_tmem_snapshot_columns_20261119/result.json.gz)
scans every first column 0..255 with scalar LDTM from observer warp 1. Each
column has three ordered controls and 29 racing pad values, for **8192
launches** (768 controls, 7424 races). Full raw-data verification finds no
unexpected values, lane disagreements, or control/final-D errors.

Comparing independent launches with the same measured pre-read phase gives
39 adjacent new/old frontiers, and **all 39 are at even columns**. For example:

| matched pre-read phase | last new column | first old column |
|---:|---:|---:|
| +19 | 3 | 4 |
| +23 | 11 | 12 |
| +30 | 25 | 26 |
| +31 | 27 | 28 |
| +34 | 33 | 34 |
| +38 | 41 | 42 |
| +87 | 139 | 140 |
| +137 | 239 | 240 |
| +145 | 253 | 254 |

Boundaries such as 26 and 34 are incompatible with restricting the observed
frontier to 4-, 8-, 16-, or 32-column alignment. The threshold brackets of
each even/odd pair `(2j, 2j+1)` agree. The simple empirical rule
`new iff phase >= 18 + floor(column/2)` fits **7422/7424** race samples.
The two exceptions are columns 254 and 255: both are still old at +145 and
first sampled new at +148. Thus the final pair's transition is bracketed by
`(145,148]`, rather than accepting the fitted +145 threshold as exact.

Equivalently, 38/39 observed adjacent frontiers follow
`first_old_column = 2 * (phase - 17)`; the exception is the final pair.
This is a **two-column observable grouping with a roughly two-columns/cycle
moving frontier**, not yet a proof of two-column physical atomic writeback.
Clock quantization, LDTM service, and different launch times remain part of
the observable. In particular, the same-phase map is assembled from separate
launches; the earlier distant-column paired test supplies the same-launch
partial-visibility evidence independently.

[Analysis](data/tcgen05_as_tmem_snapshot_columns_20261119/analysis.txt) ·
[all-column threshold brackets](data/tcgen05_as_tmem_snapshot_columns_20261119/columns.svg) ·
[matched-phase frontier map](data/tcgen05_as_tmem_snapshot_columns_20261119/columns_frontiers.svg).

### Cross-warp and x2 confirmation; reader timing follows two-column beats

The accepted [granularity rerun](data/tcgen05_as_tmem_snapshot_granularity_recovered_20261119/result.json.gz)
adds scalar reads from warps 2 and 3 at columns 0..31, 112..143, and 224..255,
plus warp-1 x2 reads starting at **every column 0..254**. Each configuration
has three ordered controls and 29 racing pads. All **14304 launches** pass:
1341 controls and 12963 races, with no unexpected values, lane disagreements,
or control/final-D errors. The 12 kernel sources are identical to their
previously accepted fine-suite variants; only launch parameters change.

| scalar observer | racing reads | adjacent matched-phase frontiers | odd-column frontiers | violations of fitted pair rule |
|---|---:|---:|---:|---:|
| warp 1, full columns suite | 7424 | 39 | 0 | 2 |
| warp 2, confirmation subset | 2784 | 11 | 0 | 0 |
| warp 3, confirmation subset | 2784 | 14 | 0 | 2 |

The two warp-3 exceptions are columns 250 and 251 at phase +143, still old
where the simple fitted rule predicts new. Warp 1's exceptions are columns
254/255 at +145 as above. These tail-region deviations stay paired; the
measurements do not distinguish tail scheduling from fine timing variation.
Warp 2's tail grid does not sample those exact boundary phases, so its zero
exceptions do not establish different tail behavior. Overall the rule fits
12988/12992 scalar race samples, and all 64 observed adjacent frontiers remain
even aligned. Each warp samples its respective 32-row region; this does not
establish a single atomic unit covering all 128 rows.

All **7395 racing x2 reads** are entirely old or entirely new, including odd
starts that cross an even-aligned pair boundary. Their start-column rule has
one exception, start 254 at +145 (both old). There are **44 comparisons** at
matched measured phases where independent scalar reads give new at `c` and
old at `c+1`, while the x2 read at `c` returns both new. For instance:

| read configuration | measured pre-read phase | result |
|---|---:|---|
| scalar column 25 | +30 | new |
| scalar column 26 | +30 | old |
| one x2 read of columns 25/26 | +30 | both new |

These are different launches. They show reader dependence of the observation,
not simultaneous contradictory TMEM states. All 44 x2 results are both new.

The ordered/no-MMA controls independently expose a matching service pattern:

| width | even start, measured cycles | odd start, measured cycles |
|---|---:|---:|
| scalar x1 | 24 | 24 |
| x2 | 24 | 25 |
| x16 | 31 | 32 |

All **2658 controls** across alignment, columns, and granularity follow
`24 + floor((column%2 + width - 1)/2)` without exception. These intervals
include the clock and scoreboard-wait scaffold, not isolated SRAM latency.
The extra cycles are consistent with service in even-aligned two-column
beats. A reader progressing at approximately the same rate as the visible
update frontier can hide mixtures inside a wide load. This is a compatible
explanation, not a separately measured internal read/write pipeline.

[Full analysis and scalar/x2 comparison](data/tcgen05_as_tmem_snapshot_granularity_recovered_20261119/analysis.txt) ·
[warp-2 thresholds](data/tcgen05_as_tmem_snapshot_granularity_recovered_20261119/confirmation_warp2.svg) ·
[warp-3 thresholds](data/tcgen05_as_tmem_snapshot_granularity_recovered_20261119/confirmation_warp3.svg).

### Sliding x16 windows across candidate column boundaries

The [alignment run](data/tcgen05_as_tmem_snapshot_alignment_20261119/result.json.gz)
adds 61 first-column positions: every `8k` and `8k+7` that keeps all sixteen
columns within N256. Observer warp 1 uses the unchanged x16 kernels from the
earlier fine run. All 29 pad arms are scanned, with nominal delta
`16 * floor(column/32) - 32`; this is only a window-placement heuristic,
not an assumption that updates have 32-column granularity.

All **5856 launches** pass (549 controls, 5307 races). There are **zero mixed
reads**, unexpected values, or lane disagreements, including windows crossing
8-, 16-, and 32-column boundaries. Of the racing reads, 1404 return new values
completely before the producer completion stamp. Thus the earlier absence of
x16 mixtures was not merely caused by choosing starts 0/1/64/65/128/192/240.
It still does not establish x16 write atomicity: the reader's service timing
can conceal a moving write boundary.

[Analysis](data/tcgen05_as_tmem_snapshot_alignment_20261119/analysis.txt) ·
[sliding-window plot](data/tcgen05_as_tmem_snapshot_alignment_20261119/alignment.svg).

### Ordered distant-column reads: direct partial-visibility witness

The [paired run](data/tcgen05_as_tmem_snapshot_paired_20261119/result.json.gz)
completes 576 launches (54 controls, 522 races), with zero final/control errors,
unexpected values, or lane disagreements. The forward order yields 211
new-column-0 / old-column-240 samples: 74 in warp 1, 68 in warp 2, and 69 in
warp 3. Every one finishes both reads before the producer's completion stamp.

One warp-1 example (`pad=4`, phase +21) has this measured timeline relative
to the first post-MMA clock stamp:

| event | cycle | returned value |
|---|---:|---|
| pre-read column 0 | +21 | |
| first post-read instruction | +27 | |
| column-0 scoreboard wait finished | +45 | 1.0, new, all 32 lanes |
| pre-read column 240 | +50 | |
| second post-read instruction | +56 | |
| column-240 scoreboard wait finished | +75 | −241.0, old, all 32 lanes |
| producer MMA completion wait finished | +223 | |

The reader explicitly waits for the first result before issuing the second;
the measured gap +45 < +50 corroborates that ordering. This is not merely an
old sample followed later by a new sample crossing one global update point.
Column 0 is already readable as new while column 240 subsequently remains
readable as old. There are no competing D stores after initialization, and
exact final D=1 is verified for all 32768 elements in every launch.

Across all forward witnesses, the first pre-read phases are +19..+82 and
the second pre-read phases +48..+112; both results return by at most +137,
before the producer stamp +223. Swapping the order gives 258 old-column-240 /
new-column-0 pairs. That reverse sequence is a consistency control; the
forward new-then-old ordering supplies the stronger spatial distinction.

[Paired analysis](data/tcgen05_as_tmem_snapshot_paired_20261119/analysis.txt) ·
[timeline SVG](data/tcgen05_as_tmem_snapshot_paired_20261119/ordered_pair.svg) ·
[PNG](data/tcgen05_as_tmem_snapshot_paired_20261119/ordered_pair.png).

### Coarse scan

The [coarse result](data/tcgen05_as_tmem_snapshot_coarse_retry_20261118/result.json.gz)
contains all 4536 launches: 567 controls and 3969 racing reads. Independent
offline verification of full snapshots and all final D elements passes, with
zero final/control errors, unexpected values, and lane disagreements.
[Full analysis](data/tcgen05_as_tmem_snapshot_coarse_retry_20261118/analysis.txt).

The following sampled bounds for observer warp 1 hold for x1, x2, and x16:

| first column | latest all-old read-start phase | earliest all-new read-start phase |
|---:|---:|---:|
| 0, 1 | −13 | +44 |
| 64, 65, 128 | +44 | +101 |
| 192, 240 | +101 | +158 |

Warp 2's sampled grid is 3 cycles earlier and warp 3's is 4 cycles later than
warp 1's, with the same coarse old/new classification. These are sparse
observations, not exact visibility thresholds. For example, at warp-1 phase
+44 a column-0 scalar read returns new by phase +68/+69 while a column-192
read remains old. These are separate launches, not one atomic whole-D snapshot.

Producer completion-wait time is always post-MMA +223 cycles in the racing
samples. The read's measured start-to-next-instruction interval is 6 cycles;
start-to-scoreboard-waited timestamp is 24–25 for x1, 24–25 for even-start x2,
25–26 for odd-start x2, 31–32 for even-start x16, and 32–33 for odd-start x16.
Thus early issued reads do not simply block until the producer's +223 stamp.
All these intervals include the observer's clock and NOP overhead.

### Fine timing

The [fine run](data/tcgen05_as_tmem_snapshot_fine_20261119/result.json.gz) completes
6048 launches (567 controls and 5481 races), with zero final/control errors,
unexpected snapshot values, or lane disagreements. There are 4773 new-value
reads whose entire measured read interval ends before the producer's +223
completion stamp. No contiguous-read mixture occurs, including x16 and odd
starting columns.

For warp 1, combining the accepted coarse and fine samples gives the following
sampled bounds; all three read widths agree on classification at their sampled
phases. These are brackets, not exact hardware retirement timestamps:

| first column | latest observed all-old phase | earliest observed all-new phase |
|---:|---:|---:|
| 0 | +13 | +18 |
| 1 | +13 | +20 |
| 64, 65 | +44 | +56 |
| 128 | +79 | +82 |
| 192 | +101 | +134 |
| 240 | +136 | +139 |

The timing arms produce irregular measured phases; notably columns 64/65/192
still have wider unsampled gaps. Absence of a mixed x16 sample cannot establish
16-column atomic writeback or rule out a short mixed-read window.

[Fine analysis](data/tcgen05_as_tmem_snapshot_fine_20261119/analysis.txt) ·
[phase plot, SVG](data/tcgen05_as_tmem_snapshot_fine_20261119/phases.svg) ·
[PNG](data/tcgen05_as_tmem_snapshot_fine_20261119/phases.png).

All 36 kernel variants pass complete sm100a assembly and strict dependency
checking; only the pre-existing `sb_capacity` CFG upper-bound advisory is
accepted. The ordinary paths contain exactly one MMA and one timed LDTM;
the no-MMA control replaces the target instruction with a NOP. Final D is
exported by a separate scalar LDTM loop after completion and CTA rendezvous.

Related historical work is recorded in
[`utchmma.md`, single-instruction intermediate visibility](../instr/utchmma.md#单条-n128-指令的中间可见性2026-09-18).
It reports x16 mixed results and emphasizes request-order and reader-service
confounds. Those earlier measurements are context, not new validation of the
present kernels.

## Construction

The allocator, identity A, future-epoch clock waits, and ordered controls are
inherited from the validated [B-fetch probe](tcgen05_as_b_fetch_tomography.md).
B remains constant BF16 1.0 throughout this experiment. A is eight copies of
I16 in TMEM; one overwrite MMA therefore gives final D[m,n]=1.0.

Before launching the timed work, every D column n is initialized to the exact
FP32 sentinel `-(n+1)`. Each initialization STTM.x8 is followed by a completed
TMEM fence before its source registers change. These distinct negative values
make wrong-column reads, zero/residue, and new MMA values distinguishable.

Warp 0 submits MMA. One of warps 1, 2, or 3 executes one unpredicated LDTM
with width x1, x2, or x16. Columns 0, 1, 64, 65, 128, 192, and 240 test both
odd/even starts and positions across the N256 output. All 32 lanes' register
results are preserved. This first sweep covers the observer warps' respective
32-row regions; it does not claim to sample warp 0's row region independently.

The observer records clock64 immediately before LDTM, immediately after its
issue, and after explicitly waiting only on the LDTM destination scoreboard.
It does not wait on the producer's MMA completion before the racing read.
Snapshot data and observer timestamps are exported only after the final CTA
rendezvous, to keep their global stores out of the measurement window.

Producer timestamps are pre-MMA, first post-MMA instruction (admission upper
bound), and completion-wait finished. Actual read phase is
`read_start - post_MMA`. The read interval includes instruction/scoreboard
measurement overhead; it is not an exact TMEM SRAM sampling timestamp.

## Controls and scan

Every width × warp × column combination first passes three controls:

- No target MMA: snapshot and final D must retain the per-column sentinels.
- Early: the observer completes its LDTM, then all warps rendezvous at BAR 1
  before the producer may submit MMA. Snapshot is old and final D is new.
- Late: the producer finishes its completion wait, then BAR 1 releases the
  observer. Snapshot and final D are new.

There are 63 configurations, 189 control cases, and 567 control launches at
three repeats. Only after all controls pass does the coarse suite scan
nominal delays −64..256 by 16 (1323 cases, 3969 launches). Total: 4536 launches.
The 29 fine-delay arms from the timing harness are retained, but coarse runs
use pad=0. If the coarse grid skips a transition, those arms allow follow-up
sampling without shortening the validated clock-consumption gap.

The fine suite keeps all 36 generated kernels byte-for-byte at the source
level identical to the accepted coarse run and changes only launch parameters.
For columns 0/1 it uses delta=0; for 64/65/128, delta=64; for 192/240, delta=128.
Each uses all 29 pad settings (0..56 by 2). Including the same control matrix,
this is 2016 cases ×3 = 6048 launches (567 controls, 5481 races).

`--suite paired` uses two serial scalar reads: first column 0, wait for its
scoreboard result, then column 240 and wait again. The reverse order is also
tested. Both reads have issue timestamps; the first completion is recorded
before the second starts. These are two separately completed LDTMs, not a
single x2 transaction. The observed new column-0 value followed by an old
column-240 value makes the spatially partial update visible within one launch,
without attributing a wide reader's service-beat boundary to MMA.

The paired matrix has three observer warps × two orders, each with the same
three controls and 29 racing pad settings at delta=0: 192 cases ×3 = 576
launches. Twelve generated variants pass full assembly and strict dependency
checking. Both reads reuse SB2 only after the first explicit drain, preserving
three globally unused scoreboards for the TMEM allocation builtin.

Every launch checks all 32768 final D elements. Racing snapshots retain old,
new, and unexpected-value counts, full compressed raw values, and differences
between lanes. Unexpected values are diagnostic evidence, not silently mapped
to either old or new. The analyzer independently rechecks the full snapshots,
final D, clock arithmetic, control coverage, sample identities, and ordering.

Runner: `tools/modal_as_tmem_snapshot.py` (B200, 2 host CPUs).
Analyzer: `tools/analyze_tcgen05_as_tmem_snapshot.py RESULT --maps`.

## Interpretation limits

A pre-completion LDTM may stall or otherwise perturb the tensor-memory path;
its issue and completion timestamps must be considered together. A read that
starts before the producer's completion timestamp but finishes after it does
not establish an early returned result. Conversely, the producer's completion
wait may include polling overhead after physical MMA completion.

A mixed x16 output can reflect the LDTM service window crossing an update,
rather than sixteen columns coexisting in those states at one instant.
Narrow reads, odd/even starts, observer-warp comparisons, and eventually
reversed request sequences are needed before inferring a physical writeback
unit or writeback direction. This is a controlled in-flight hardware probe,
not portable program synchronization semantics.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Does the two-column observable grouping reflect physical MMA write
  atomicity, LDTM service/banking, cycle-resolution sampling, or a combination?
  Scalar frontiers and read-service controls both have two-column structure;
  x2/x16 windows do not split, and tail pairs deviate slightly from the fitted
  constant-rate rule. The atomic row extent also remains unmeasured.
  <!-- open-question: open blocked-by "needs an independently characterized read shape or subcycle-sensitive observable that separates writer granularity from LDTM service" -->
