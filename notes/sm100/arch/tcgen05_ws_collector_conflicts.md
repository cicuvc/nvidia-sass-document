# B200 WS collector buffer conflict probes (2026-11-17)

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

**Evidence:** sm100-silicon, Modal NVIDIA B200
**Probe:** `tests/asm_construct/probe_sm100_ws_throughput.py --suite conflict`
**Runner:** `tools/modal_ws_sass.py`
**Analysis:** `tools/analyze_tcgen05_ws_conflicts.py`

## Conclusion

Two distinct B collector IDs already hide the sampled discard-turnaround penalty, and all distinct pairs behave alike. Same-ID bursts follow the measured adjacent-repeat cost. The data constrain buffer scheduling without assigning IDs to physical subcores.

## Evidence

## Question and construction

The [throughput scan](tcgen05_ws_sass_throughput.md) established that four-ID
rotation hides a single-ID discard penalty. It did not establish whether all
pairs of buffer IDs behave alike, how many IDs are necessary, or whether
repeated occurrences of the same ID explain burst-pattern costs.

This scan keeps A in TMEM, N64, K16 BF16, and tests M32/64/128. Warp 0 issues a
static stream with stall1 and a single final completion wait. As in the earlier
probe, every launch checks every D output plus unused-column guards. Counts
96 and 768 are divisible by all period lengths (1/2/3/4/8). Report the slope
`(median(T768)-median(T96))/672`, with one warmup and five retained samples.
Initialization and scalar readback are outside timing.

For each M:

* Four single-ID discard baselines.
* All twelve ordered two-ID patterns (01,02,...,32). AB and BA are cyclic
  shifts, so these provide starting-phase controls, **not** separate measurements
  of directed A→B and B→A transition latency.
* All four three-ID subsets, in ascending cyclic order.
* All six four-ID cyclic permutations, fixing ID0 at the first position.
* All six unordered pairs in aabb and aaaabbbb burst patterns.
* Discard address controls for all six pairs: ID b selects B address b rather
  than all IDs selecting the same address.
* Reuse controls for each single ID and each unordered pair, also with the B
  address keyed by ID. Each ID's first occurrence fills, intermediate occurrences
  reuse+keep, and final occurrence uses without keep. No use-before-fill occurs.

B addresses 0..3 contain BF16 values 1..4. For address-varying patterns, the
reference is `16 * repetitions * sum(id+1 for id in period)`. Thus both same-
address and different-address comparisons remain numerically checked. These
values test selection and accumulation, not arbitrary-data cache capacity.

The resulting 324 configurations probe one issuing warp and one CTA. They
cannot establish cross-warp collector namespace, interference between simultaneous
issuers, or physical proximity to a subcore. All N values in this scan are 64;
lack of conflict here is not a capacity result for larger B tiles.

## Model to test

With TMEM A and N64, the earlier single-ID discard slopes were 28/28/42 for
M32/64/128; four-ID rotation gave 16/16/32. Define the latter as base B and the
difference as delta (12/12/10).

A simple local-transition model predicts a cyclic pattern P costs

`T(P) = B + delta * fraction_of_adjacent_equal_IDs(P)`.

This predicts AB=B, AABB=B+delta/2 and AAAABBBB=B+3*delta/4, independent of the
specific distinct IDs. It is a falsifiable empirical model, not an assertion
that an instruction's latency is B or that the entire delta occurs in one
particular collector pipeline stage.

## Observed pattern costs

The main scan completed **324 configurations / 1944 launches**, including
warmups, with zero errors. Every case has identical timing in its five retained
samples. [Raw main results and exact source](data/tcgen05_ws_conflict_20261117.json.gz).
Together with the mixed follow-up: **396 configurations / 2376 launches**.

Cycles/MMA, all pairs with distinct a,b:

| pattern / mode | M32 | M64 | M128 |
|---|---:|---:|---:|
| aaaa... discard, any single ID | 28 | 28 | 42 |
| abab... discard, any distinct pair | 16 | 16 | 32 |
| three-ID rings | 16 | 16 | 32 |
| four-ID rings, all six cyclic orders | 16 | 16 | 32 |
| aabb... discard, any distinct pair | 22 | 22 | 37 |
| aaaabbbb... discard, any distinct pair | 25 | 25 | 39.5 |
| abab... discard, distinct B addresses | 16 | 16 | 32 |
| single-ID or alternating-pair reuse | 9 | 16 | 32 |

The discard pair matrices have uniform diagonals and uniform off-diagonals:
M32/M64 diagonal=28, off-diagonal=16; M128 diagonal=42, off-diagonal=32.
There is no observable special pairing such as (0,2) versus (0,1). All burst
costs exactly match the adjacent-equal-ID model above. Two distinct IDs already
hide the refill penalty at these shapes; three and four do not improve it.

This constructs a repeatable **same-ID refill conflict**, but does not expose a
**distinct-ID pair-specific conflict**. The results favor a separate refill/
release state per logical ID over a model where two IDs share an unavoidable
extra turnaround penalty under this workload. They do not exclude shared
storage ports with sufficient bandwidth, banked distributed contexts, or an
ID-to-subcore correspondence invisible to this single-issuer throughput test.

## Mixed fill/read follow-up

`--suite conflict_mixed` alternates discard on ID a with reuse on distinct ID b,
for all twelve role-ordered pairs and all three M values. The b stream fills on
its first occurrence and lastuses on its final occurrence; a refills on every
occurrence. Each ID selects its own B address/value. Counts and validation match
the main scan, giving another 72 configurations. Here reversing ab **does**
exchange the discard and reuse roles, unlike the all-discard cyclic-shift control.

This probes whether writes/refills to one buffer interfere with reads from
another, potentially exposing a conflict hidden when both operands are refilled.
It still uses a single issuing warp, not independently concurrent issuers.

The mixed scan completed: **72 configurations / 432 launches**, zero errors,
and identical timing in all five retained samples of each case.
[Raw mixed results and exact source](data/tcgen05_ws_conflict_mixed_20261117.json.gz).
For every ordered pair a≠b, the slopes are **14/16/32 cycles/MMA** at
M32/64/128. No role-dependent pair asymmetry is visible.

This agrees with a per-ID refill recurrence constraint. Let U be the all-reuse
interval (9/16/32), S=16 be the B shared-service demand, and R=28/28/42 the
single-ID discard interval. A two-instruction discard/reuse period refills only
once, so a simple steady-state model gives
`T_mixed = max(U, S/2, R/2) = 14/16/32`.
For M32, the refilled ID recurs once every 28 cycles while the other ID remains
reusable. This supports independent per-ID lifetime management, but does not
locate a physical bank or prove that R is a single pipeline-stage latency.

## Reproduction

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_ws_sass.py --suite conflict --reps 5 --output /tmp/ws-sass-conflict
python3 tools/analyze_tcgen05_ws_conflicts.py /tmp/ws-sass-conflict/result.json
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_ws_sass.py --suite conflict_mixed --reps 5 --output /tmp/ws-sass-conflict-mixed
python3 tools/analyze_tcgen05_ws_conflicts.py /tmp/ws-sass-conflict-mixed/result.json
```

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
