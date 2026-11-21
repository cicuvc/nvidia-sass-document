# WS M32/M64/M128 final B-version agreement across regions

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-20
**Probe:** `tests/asm_construct/probe_sm100_ws_b_versions.py`
**Open items:** 1
**Audit:** 34336 full raw payloads validated; M32 and M64 final-version differences repeat 20/20 per positive configuration; M128 agrees throughout

## Conclusion

**WS M32 and M64 can select different final B versions across physical
regions; M128 agrees in every sampled launch.** In M64, regions 0/1 agree
with each other, as do regions 2/3; differences occur only between those
groups. The full scan gives 89/3712 M32 and 58/7424 M64 differing races,
versus 0/14848 M128. A repeated N8-block scan reproduces all 13 positive
M32 configurations and all five positive M64 configurations in 20/20 trials
each, while M128 remains equal.

These are final input-version differences, independent of in-flight LDTM
service or D writeback order: all D reads follow MMA completion and CTA
rendezvous. However, **all differences occur with the reversed writer lane
assignment**; the forward assignment has none. This removes the prior
read-side ambiguity but not write-side timing. M32 and cross-group M64 read
different B addresses, so these observations do not isolate autonomous
tensor-partition skew. M128 and each same-N M64 pair use the same B elements
and agree throughout. No physical partition numbering or shared-buffer
topology is identified.

The [single-128B-STS follow-up](tcgen05_ws_b_singlebeat.md) removes the
wide-store/bank-conflict construction for M64. Complementary bank subsets
span the two B tiles in one scalar store; it reproduces OONN across both
bank partitions, tile-subset swaps, and lane orders. Thus the M64
final-version split also exists without the reversed-wide-writer condition
specific to this earlier experiment. Exact physical capture timing and
transaction granularity remain unresolved.

## Method

One CTA, N256 K16 BF16 to FP32, TMEM A containing repeated I16, shared B
initially 1, overwrite D, WS buffer 0 discard. All four regions have the same
A pattern. Old/new final values are exactly 1/2. Unused physical columns
remain zero. Warp 0 issues MMA; warp 1 modifies B. All 32768 D elements,
writer shared-byte readback, five timestamps, epoch/wait arithmetic, and
runtime parameter echoes are retained in compressed raw payloads.

For region w, local column c, and lane l:

| M | active local width | logical column | logical row |
|---|---:|---|---|
| 32 | 64 | 64w+c | l |
| 64 | 128 | 128 floor(w/2)+c | 32(w mod 2)+l |
| 128 | 256 | c | 32w+l |

Each launch modifies one aligned local N8 block, for K0..7 or K8..15.
The writer scatters one STS.128 to all distinct logical N bands represented
by the four regions. Lane q writes eight BF16 elements at
`k..k+7, n=2M*floor(q/8)+nbase+(q mod 8)`; only `q<1024/M` is active.
Thus M32 writes four K8xN8 patches (512 bytes), M64 two (256 bytes), and
M128 one (128 bytes). The shared descriptor has no swizzle. Forward and
reversed lane assignments use q=lane and q=lane XOR 31, with exactly the
same logical write set.

This follows the AS patch experiment rather than serially overwriting all
8192 B bytes. Every aligned N8 block across the entire active local width is
scanned. Each launch compares the complete 8x8 version masks, column
transition patterns, all six region pairs, and the two I16 copies per
region. No global boundary assembled from separate launches is treated as
a simultaneous observation. Nonuniform K masks are preserved, not reduced
to a misleading single boundary column.

There are 224 writer configurations (56 local blocks across the three M
values, two K halves, two lane maps). All 672 no-mutation, ordered-before,
and ordered-after controls precede races. Each writer configuration then
uses four nominal delays (-128,-64,0,64) and 29 fine pads (0..56 by 2), for
25984 races and 26656 total launches at one repetition. Measured pre-store
minus post-MMA clocks, not nominal delays, describe actual timing.

For M32 and the cross-N pairs of M64, equal local columns refer to different
B addresses. A single STS is not asserted to become visible atomically
across those addresses. Reverse lane assignment tests writer sensitivity;
it cannot alone eliminate every write-side explanation. M64 within pairs
0/1 and 2/3, and all M128 pairs, compare the same logical B elements.

## Evidence

### Full scan, verified 2026-11-20

The [scan result](data/tcgen05_ws_b_versions_scan_20261120/result.json.gz)
and [offline summary](data/tcgen05_ws_b_versions_scan_20261120/summary.json)
validate all 26656 launches, including the complete final D, shared write
readback, parameter echoes, and timing arithmetic. Driver 610.57.04;
app `ap-6sMViC4StgZbHbBhqa3qVm`, allocation/start 14.01 seconds.

| M | controls | races | region disagreement | region-local replica disagreement |
|---|---:|---:|---:|---:|
| 32 | 96 | 3712 | 89 | 0 |
| 64 | 192 | 7424 | 58 | 0 |
| 128 | 384 | 14848 | 0 | 0 |

All 3584 shape/K-half/local-column/region combinations observe both old and
new versions. Mutation phases span -136..155 cycles. Every tested K8xN8
patch within one region is uniformly old or new: there are no intra-N8
column transitions or intra-K8 splits in this data.

Writing O/N for an entire old/new K8xN8 patch, the only differing four-region
patterns are M32 `ONNN` (31 samples), `OONN` (32), and `OOON` (26); M64
`OONN` (58). All occur with lane XOR 31. Forward assignment has zero
disagreements in 1856, 3712, and 7424 races for M32, M64, and M128.
Reverse assignment has 89/1856, 58/3712, and 0/7424, respectively.

For M64 the six pair counts are `0-1:0, 0-2:58, 0-3:58, 1-2:58, 1-3:58,
2-3:0`. The two groups follow the validated logical-N mapping exactly.
No same-logical-B comparison disagrees.

### Repeated N0 block, verified 2026-11-20

The [repeat result](data/tcgen05_ws_b_versions_repeat_20261120/result.json.gz)
and [summary](data/tcgen05_ws_b_versions_repeat_20261120/summary.json) validate
7680 launches, including 720 controls. It uses local nbase=0, both K halves,
both lane assignments, delta=-64, all 29 fine pads, and 20 repetitions.
Each shape has 2320 races. Only host case selection changes; all 18 device
sources and the original scan case matrix were compared against the frozen
first request and remain identical. Driver 610.57.04;
app `ap-T2OLnpvSVyTJirM0azpggN`, start 8.26 seconds.

M32 gives 260 differing races (13 configurations x20), M64 gives 100 (five
configurations x20), and M128 gives zero. Every positive configuration
repeats its exact phase and final pattern in 20/20 trials. All occur with
reversed lane assignment. Both old and new are covered in every sampled
region/K-half/column; region-local replicas, intra-K8 and intra-N8 patterns
remain uniform. No warm-up observations are removed.

For example, with K0..7, local nbase=0, delta=-64, pad=12, and reversed
lanes, both M32 and M64 consistently give `OONN` at measured phase -14.
This is one launch's final result across four regions, not a comparison of
separately timed LDTM reads.

### Column-frontier reconstruction, verified 2026-11-20

At measured phase +4 and K0..7, collecting the separately modified N8
blocks gives the following first-new local columns:

| M | forward lanes: regions 0,1,2,3 | reversed lanes: regions 0,1,2,3 |
|---|---|---|
| 32 | 24,24,24,24 | 32,24,24,16 |
| 64 | 40,40,40,40 | 48,48,40,40 |
| 128 | 80,80,80,80 | 80,80,80,80 |

These are **cross-launch reconstructions at equal measured phase**, not
full-B snapshots from a single mutation. All observations sharing each
shape/K-half/block/lane-map/phase agree before a block is selected for the
figure. Within each block, four-region differences are simultaneous and
directly established by the full payload. This distinction matters when
interpreting a plotted global boundary.

[Frontier figure](data/tcgen05_ws_b_versions_scan_20261120/phase4_frontiers.svg)
and [case provenance](data/tcgen05_ws_b_versions_scan_20261120/phase4_frontiers.json)
are saved alongside a visually checked PNG.

All 18 shape/K-half/ordering variants pass full sm100a assembly with strict
dependency checking. Only the inherited sb_capacity advisory is permitted.
Host enumeration verifies every active scatter address against the validated
K-major B mapping, with no duplicates or omissions, for every block, shape,
K half, and lane assignment. Python syntax checks pass.

The remote runner is `tools/modal_ws_b_versions.py`; offline validator is
`tools/analyze_tcgen05_ws_b_versions.py`. The runner retains frozen sources,
dependency hashes, driver information, loader preflights, and a durable call.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Can a writer design or independent shared-visibility measurement separate inter-address store visibility from WS input-version capture timing? <!-- open-question: open blocked-by "blocker (inferred): positive cases depend on lane assignment and compare distinct B addresses" -->
