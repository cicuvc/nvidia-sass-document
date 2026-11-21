# WS M32 four-region B capture under one conflict-free 128-byte store

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** `tests/asm_construct/probe_sm100_ws32_b_singlebeat.py`
**Open items:** 1
**Audit:** 35584 full raw payloads validated; only NNNN/ONNN/OONN/OOON/OOOO; all five K8/nbase0 repeat states reproduce 320/320 across 16 writer mappings

## Conclusion

**The four-region old/new boundary follows logical region order0,1,2,3.**
Across35584 validated launches, the only racing states are NNNN, ONNN,
OONN, OOON, OOOO. The full scan has240 ONNN,208 OONN,256 OOON witnesses;
repetitions add640,640,320 respectively. There are no non-prefix states,
internally mixed selected sets, or I16 replica disagreements.

In a fixed nbase0/K8..15 comparison, five selected write timings yield all
five states. Each state reproduces in20/20 trials under each of16 writer
mappings, totaling320/320 per state. Changing bank grouping, XOR tile
assignment, or lane order does not change the observed direction. The
scan's1856 fixed K-half/nbase/delta/pad groups likewise agree across all16
mappings, beyond mere agreement of aggregate counts.

This extends the [M64 single-store experiment](tcgen05_ws_b_singlebeat.md)
and supports successive B-version fixation for the four N64 bands. The
comparison is of completed outputs under one bank-conflict-free128B store;
in-flight LDTM service and D writeback order do not determine these masks.
Only the modified elements reveal their version. The experiment does not
directly establish physical read-transaction size, a precise two-cycle
inter-tile gap, or the internal buffer topology.

## Method

One CTA, WS M32 N256 K16 BF16 to FP32, repeated I16 in TMEM A, shared B
initially1, selected values changed to2, overwrite D, buffer0 discard.
Warp0 issues one MMA and warp1 executes one scalar STS with32 active lanes,
4 bytes each. Every final D read occurs after MMA completion and CTA
rendezvous; no LDTM is used during the race.

For q=lane XOR lane_xor, let group=q AND3 (interleaved banks) or group=q>>3
(contiguous bank quarters). Logical N band b=group XOR tile_swap, with
lane_xor0/31 and tile_swap0/1/2/3. These are four XOR bijections, not all24
permutations. The shared byte address is
`0x2000 + 32*nbase + 2048*b + 16*k + 4*q`, where nbase is an aligned local
N8 start0..56 and k=0/8 selects the K8 half.

Bank index is exactly q. Thus there is one word in each of32 different
banks,32 total words, and8 words (32 bytes) in each requested B tile at
N=nbase+64*b. Interleaved groups select one K pair across all eight N
columns in each tile. Quarter groups select all eight K values in two N
columns. XOR reassignment exchanges these subsets among logical tiles;
lane reversal preserves the write set. Addresses are independently checked
against the established no-swizzle K-major descriptor mapping.

Region w corresponds to logical row=lane, N=64*w+c, active local c<64.
Each region exposes16 selected B elements plus a second I16 row replica.
O/N mean all selected elements in that region used old/new B; M records
an internally mixed set. Unselected active D must remain1 and unused
physical columns must remain0. No same-logical-B pairs exist across these
four regions, so the prior M64 within-pair equality check is inapplicable.

All32768 D floats,128 writer shared bytes, six runtime parameter echoes,
five timestamps, and epoch/wait arithmetic are archived and validated.
There are256 writer configurations:8 local blocks x2 K halves x2 bank
partitions x4 XOR permutations x2 lane orders. All768 ordered controls
(no mutation, completed-before, completed-after) precede29696 races,
using four nominal delays(-128,-64,0,64) and29 fine pads. Total30464.

## Evidence

### Full scan, verified 2026-11-21

The [accepted result](data/tcgen05_ws32_b_singlebeat_phdr_20261121/result.json.gz)
and [summary](data/tcgen05_ws32_b_singlebeat_phdr_20261121/summary.json)
validate30464 launches:768 controls plus29696 races. Driver610.57.04;
app `ap-NEV9ec5ywGQsgMeehLJsI1`, start8.51 seconds. Original cubins load
without the optional compatibility adapter (`loader_compat=false`).

| selected B versions, regions0/1/2/3 | racing launches |
|---|---:|
| NNNN | 16368 |
| ONNN | 240 |
| OONN | 208 |
| OOON | 256 |
| OOOO | 12624 |
| any other state | 0 |

Every selected element has both old and new coverage in all16384
configuration/region/element cells. Every full D payload, unselected value,
outside-footprint value, shared patch, parameter echo, clock, and wait
calculation passes. There are no region-local I16 replica disagreements.

Each of16 writer mappings has7 ONNN,7 OONN,8 OOON cases for K0..7,
and8 ONNN,6 OONN,8 OOON for K8..15. More strongly, all1856 fixed
K/nbase/delta/pad groups give identical states across the16 mappings.
Measured phases differ across mappings in three groups without affecting
states. Every race has an11-cycle pre-STS-to-post-fence interval; this is
not a direct physical store-service latency.

[Mapping comparison](data/tcgen05_ws32_b_singlebeat_phdr_20261121/mapping_comparison.json)
retains these checks separately from the full raw archive.

### Fixed-block repetitions, verified 2026-11-21

The [repeat result](data/tcgen05_ws32_b_singlebeat_repeat_20261121/result.json.gz)
and [summary](data/tcgen05_ws32_b_singlebeat_repeat_20261121/summary.json)
validate5120 launches:1920 controls plus3200 races. Driver610.57.04;
app `ap-7puZRzMV77CYMpV74bZd7o`, start11.76 seconds. The compatibility
adapter is again disabled. All12 measured device sources and the original
scan matrix exactly match the frozen accepted scan request.

nbase=0; both K halves; two bank partitions x four XOR tile assignments x
two lane orders; five timing selections;20 repetitions. Every configuration
reproduces its final state in20/20 observations. The measured phases below
are pre-STS minus first post-MMA, not physical bus timestamps:

| delta / pad | usual phase | K0..7 state (320 trials) | K8..15 state (320 trials) |
|---|---:|---|---|
| -64 / 36 | -10 | NNNN | NNNN |
| 0 / 2 | -7 | ONNN | ONNN |
| 0 / 8 | -5 | OONN | OONN |
| 0 / 14 | -2 | OOOO | OOON |
| 0 / 0 | +32 | OOOO | OOOO |

Each K half's first row includes two samples at phase-19 instead of-10;
their state is still NNNN. All observations are retained. Totals are640
NNNN,640 ONNN,640 OONN,320 OOON,960 OOOO. All sampled selected elements
have both old and new coverage, and no selected set or I16 replica splits.
The K0 half's missing OOON at these five selected timings does not imply
its absence: the full scan has128 K0 OOON witnesses at other configurations.

### Boundary picture, verified 2026-11-21

[Five-state figure](data/tcgen05_ws32_b_singlebeat_phdr_20261121/region_boundary_patterns.svg)
and [underlying records](data/tcgen05_ws32_b_singlebeat_phdr_20261121/region_boundary_patterns.json)
show each observed boundary at nbase0/K8..15. Each plotted column is a
separate launch; its four-region comparison is simultaneous within that
launch. This is not a continuous trace of one MMA. The figure distinguishes
old/new input versions of the modified elements, not completion of entire
output regions or exact internal read beats.

All12 K-half/bank-partition/ordering variants pass full sm100a assembly with
strict dependency checking; only the inherited sb_capacity advisory is
permitted. Every scatter configuration passes unique-address,32-bank,
32-byte-per-tile, and exact logical-coordinate checks. The generated timed
mutation contains exactly one predicated scalar STS and no wide STS.

Runner: `tools/modal_ws32_b_singlebeat.py`; offline validator:
`tools/analyze_tcgen05_ws32_b_singlebeat.py`. Frozen sources, dependency
hashes, loader preflights, and durable call ID are retained per request.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Can physical store-service timing and finer perturbations distinguish the proposed two128B read beats per tile from alternative input-buffer/read organizations? <!-- open-question: open blocked-by "blocker (inferred): final sparse version masks establish ordering but do not directly timestamp or size physical reads" -->
