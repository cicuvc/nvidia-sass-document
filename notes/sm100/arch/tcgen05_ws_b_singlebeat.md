# WS M64 B capture under a conflict-free 128-byte shared store

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** `tests/asm_construct/probe_sm100_ws_b_singlebeat.py`
**Open items:** 1
**Audit:** 33024 full raw payloads validated; 886 OONN witnesses across both runs; anchor reproduces 320/320 across both K halves and all eight writer mappings

## Conclusion

**The predicted final-version split is observed robustly:** a single
128-byte scalar STS, with one distinct bank per lane, can leave the modified
B elements old in regions0/1 and new in regions2/3. The broad scan has248
`OONN` witnesses; the repeat run has638. There are no `NNOO` witnesses,
no internally mixed selected sets, and no same-logical-B or repeated-row
disagreements. All ordered controls and full raw payload checks pass.

Unlike the prior wide-store experiment, the direction survives both bank
partitions, exchange of the bank subsets between tiles, and lane reversal.
At local nbase0 and measured mutation phase-7, both K8 halves and all eight
writer mappings reproduce `OONN` in20/20 trials each, totaling320/320.
This supports earlier B-version fixation for the first logical N band,
followed by the second, independently of the in-flight LDTM/writeback-order
observable. Only the modified elements reveal their input version.

The proposed model assigns two128-byte read beats to each N8xK16 tile and
four beats to the pair. The result supports its directional version-split
prediction, but does not by itself establish an exact two-cycle gap,
physical broadcast topology, or absence of finer B-read granularity.

The [M32 four-tile follow-up](tcgen05_ws32_b_singlebeat.md) distributes the
same128-byte conflict-free store across four N64 bands,32 bytes each.
It observes all three intermediate boundaries ONNN/OONN/OOON, invariant
under16 writer mappings and repeatable20/20 per selected configuration.
The version-fixation order follows logical regions0,1,2,3.

## Method

One CTA, WS M64 N256 K16 BF16 to FP32, repeated I16 in TMEM A, shared B
initially 1, overwrite D, buffer0 discard. Warp0 produces one MMA; warp1
changes selected B elements to2 using exactly ONE scalar `STS [R36], R24`.
All 32 lanes are active when enabled, each storing one aligned 32-bit word.
No wide STS instruction or multiple store instruction is used in the timed
mutation. All final D reads follow MMA completion and CTA rendezvous.

Let q=lane XOR lane_xor, with lane_xor=0 or31; nbase is an aligned local
N8 start in0..120; k=0 or8 selects the K8 half. Two complementary bank
partitions select logical band b:

- alternating: b=(q AND1) XOR tile_swap;
- halves: b=(q>>4) XOR tile_swap.

The byte address is `0x2000 + 32*nbase + 4096*b + 16*k + 4*q`.
Its bank index `(address/4) mod32` is exactly q. Thus the 32 words touch
32 distinct banks, no word is duplicated, and each N8xK16 tile receives
64 bytes of the total128. All addresses are inside the two requested tiles.
The mapping is also checked against the validated no-swizzle K-major
B descriptor formula. Conflict-free here describes the established bank
mapping; the probe does not separately timestamp physical bank writes or
assume cross-bank atomic visibility.

For alternating bank assignment each tile receives complementary K pairs
in all eight N columns. For halves assignment each receives all eight K
entries in complementary four-column subsets. tile_swap exchanges these
subsets between the two N bands without changing bank utilization;
lane_xor reverses which lane serves which bank, preserving the write set.
These controls test whether a difference follows logical tile order or the
chosen bank/element/lane subset. Unmodified elements are checked to remain1.

The final matrix has logical N=c for regions0/1 and N=128+c for regions2/3.
Each region's selected32 BF16 elements are exposed directly in D by I16,
with a second identical row copy checked separately. O/N denote all selected
elements using old/new B; M denotes an internally mixed selected set and
is retained, not discarded. Strict witnesses are `OONN` or `NNOO`.
Same-logical-B pairs0/1 and2/3 are checked element by element.

All32768 physical D values, all128 written shared bytes, runtime parameter
echoes, five clocks, and epoch/wait arithmetic are archived in raw form.
Outside the M64 footprint must remain0. Controls cover no mutation,
mutation completed before MMA, and mutation after MMA completion.

The scan contains256 writer configurations:16 N8 blocks x2 K halves x2
bank partitions x2 tile swaps x2 lane orders. All768 controls precede29696
races (four coarse delays -128/-64/0/64 x29 fine pads). Total30464 launches.
The same-half two-cycle inter-tile capture gap is a prediction, not a
validation condition; pre-store clocks are not physical read timestamps.

## Evidence

### Full scan, verified 2026-11-21

[Raw result](data/tcgen05_ws_b_singlebeat_scan_20261121/result.json.gz) and
[validated summary](data/tcgen05_ws_b_singlebeat_scan_20261121/summary.json):
30464 launches =768 controls +29696 races, driver610.57.04,
app `ap-A3DaZxLCxNRAqiB66ditDz`, startup8.76 seconds. Every full D matrix,
shared patch, runtime parameter echo, and timing check passes.

| selected final versions, regions0/1/2/3 | race count |
|---|---:|
| NNNN | 16592 |
| OOOO | 12856 |
| OONN | 248 |
| NNOO or any internally mixed set | 0 |

Each of the eight bank-partition/tile-swap/lane-order combinations has15
witnesses in K0..7 and16 in K8..15. More strongly, all3712 fixed
K-half/nbase/delta/pad groups give **identical version states across their
eight writer mappings**, not just equal totals. Measured phases differ
across mappings in three groups; state agreement still holds. The pre-STS
to post-fence interval is11 cycles in every racing sample; this interval
does not measure pure STS latency or physical store atomicity.

All32768 configuration/region/selected-element coverage cells observe both
old and new values. All physical D values outside the selected patch or
active M64 footprint pass their independent expected-value checks.

[Mapping comparison](data/tcgen05_ws_b_singlebeat_scan_20261121/mapping_comparison.json)
and the full raw archive retain the comparisons above.

### Repetition, verified 2026-11-21

[Raw repeat result](data/tcgen05_ws_b_singlebeat_repeat_20261121/result.json.gz)
and [summary](data/tcgen05_ws_b_singlebeat_repeat_20261121/summary.json):
2560 launches =960 controls +1600 races, driver610.57.04,
app `ap-0gC3Pkp0YhbuGgNyHSxSlH`, startup8.26 seconds. All checks pass.
The follow-up fixes nbase0 and repeats five timing selections20 times each,
retaining both K halves and all eight writer mappings. All12 measured
device sources and the original scan matrix exactly match the frozen
first request; only host case selection changes.

| K half | delta / pad | usual measured phase | version outcomes across 8 mappings x20 |
|---|---|---:|---|
| 0..7 | -64 / 36 | -10 | 158 NNNN; 2 OOOO at phase0 |
| 0..7 | -64 / 42 | -6 | 160 OOOO |
| 0..7 | -64 / 56 | -6 | 160 OOOO, including2 at phase-3 |
| 0..7 | 0 / 2 | -7 | **160 OONN** |
| 0..7 | 0 / 8 | -5 | 160 OOOO |
| 8..15 | -64 / 36 | -10 | 158 NNNN; 2 OOOO at phase0 |
| 8..15 | -64 / 42 | -6 | **160 OONN** |
| 8..15 | -64 / 56 | -6 | 158 OONN; 2 OOOO at phase-3 |
| 8..15 | 0 / 2 | -7 | **160 OONN** |
| 8..15 | 0 / 8 | -5 | 160 OOOO |

No observations are removed. The total is638 OONN,646 OOOO,316 NNNN.
Eight samples have shifted measured phases relative to their configuration's
usual phase; two of them change a usual split to all-old. The anchor
delta0/pad2 is unaffected:320/320 OONN across both K halves and eight maps.
Every sampled selected element again has both old and new coverage.

### Single-launch witness and interpretation, verified 2026-11-21

For K0..7, nbase0, alternating banks, tile_swap0, lane_xor0, delta0/pad2:
the first N band writes K pairs0/1 and4/5 at N0..7; the second writes
K pairs2/3 and6/7 at N128..135. This is64 bytes per tile,128 bytes total.
Final selected outputs in regions0/1 are all1 (old), while those in2/3
are all2 (new). Swapping the bank subsets also swaps the modified K pairs,
yet the OONN direction persists. The halves partition instead changes
complementary N subsets and gives the same direction.

[Witness figure](data/tcgen05_ws_b_singlebeat_scan_20261121/single_store_witness.svg)
and [record](data/tcgen05_ws_b_singlebeat_scan_20261121/single_store_witness.json)
show a single launch, with unmodified elements explicitly distinguished.

This establishes the requested observable without a wide-store multi-beat
or bank-conflict construction. It remains a sparse perturbation experiment,
not a direct view of the physical read bus. In particular, the pre-STS
timestamp is not an exact service timestamp: at K8/nbase56, delta0/pad16
gives phase19/OONN, while delta0/pad22 gives phase20/NNNN. These separate
launches prohibit interpreting every phase as a strict capture threshold
or fitting an exact two-cycle inter-tile delay from this sweep alone.
The robust same-launch split and mapping invariance do not depend on such
a timing fit.

All12 K-half/bank-partition/ordering kernels pass full sm100a assembly with
strict dependency checks; only the inherited sb_capacity advisory is allowed.
For every writer configuration, host enumeration verifies32 distinct banks,
128 total bytes,64 bytes per tile, exact logical K/N addresses, and absence
of overlapping words. The generated timed store is checked to be scalar.

Runner: `tools/modal_ws_b_singlebeat.py`. Full-payload validator:
`tools/analyze_tcgen05_ws_b_singlebeat.py`. Sources, dependency hashes,
loader preflights, driver information, and durable call ID are preserved.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Can an independently constrained physical store-service time determine the inter-tile capture interval and distinguish full-128B reads from finer transactions? <!-- open-question: open blocked-by "blocker (inferred): pre-STS clock does not uniquely timestamp service, and sparse final versions do not directly expose transaction size" -->
