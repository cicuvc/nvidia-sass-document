# B200 AS A collector: issue spacing and scheduling controls

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

2026-11-18. Probe `tests/asm_construct/probe_sm100_as_gap.py`, runner
`tools/modal_as_gap.py`, analyzer `tools/analyze_tcgen05_as_gap.py`.

## Conclusion

AS A reuse depends on issue spacing: the sampled M128N64 stream retains nearly full shared-interference savings at a 50-cycle MMA slope, partial savings at 58–90, and none at 98 or above. NOP yield settings agree; equal-count and equal-stall controls constrain scheduling explanations without measuring an exact collector TTL.

## Evidence

## Completed coarse sweep

[Raw results, inventory, and source snapshots](data/tcgen05_as_gap_coarse_retry1_20261118/result.json.gz).
The complete record contains 104 configurations, each with one warmup and
five retained repetitions: 624 launches, 520 timing samples, and zero
D/guard/LDS checksum errors.

M128 N64 K16 BF16, shared A/B remain unchanged. The reuse sequence is
A_KEEP followed by A_REUSE.A_KEEP. No intermediate commit or completion wait;
the last MMA has no trailing filler and uses the common final commit/wait.
Block128, 112 registers/thread, maximal shared allocation plus driver
reservation exhausts the SM shared residency budget, as in the
[isolation probe](tcgen05_as_collector_isolation.md).

Insert 0/1/2/4/8/16/32 NOPs between UTCHMMA instructions. Each NOP has stall8;
nonzero gaps test both numeric yield settings. UTCHMMA uses stall1/yield1.
Each point has discard/reuse, with/without three LDS meter warps, and
64/256 MMAs. Slopes are `(T256-T64)/192`. The LDS measurement is the span of
fixed-work meter warps, not an exact shared-memory byte or hit counter.

The numeric yield toggle really changes the instruction: at fixed stall8,
NOP yield0/1 encodings differ only at instruction bit109
(high-word XOR `0x200000000000`). The assembler maps yield0 to
`usched_info=stall+16`, yield1 to `usched_info=stall`.

| NOPs | MMA discard | MMA reuse | LDS discard, y1 | LDS reuse, y1 | LDS advantage, y1 | LDS advantage, y0 |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 48 | 32 | 47.828125 | 15.250000 | 32.578125 | — |
| 1 | 48 | 32 | 47.828125 | 15.244792 | 32.583333 | 32.583333 |
| 2 | 48 | 32 | 47.833333 | 15.250000 | 32.583333 | 32.578125 |
| 4 | 48 | 34 | 47.942708 | 15.687500 | 32.255208 | 32.250000 |
| 8 | 66 | 66 | 47.770833 | 31.890625 | 15.880208 | 15.885417 |
| 16 | 130 | 130 | 47.791667 | 47.796875 | -0.005208 | 0.005208 |
| 32 | 258 | 258 | 47.432292 | 47.427083 | 0.005208 | -0.005208 |

All timing units are cycles per additional MMA. MMA columns are without LDS
pressure and identical between the two NOP yield settings. Advantage means
LDS discard minus LDS reuse. Minimum simultaneous three-meter coverage of
the MMA interval is 96.196%. Maximum five-sample within-configuration spread
is 12 cycles for MMA duration and 28 cycles for LDS span.
All matched NOP yield0/1 pairs have exactly equal median MMA durations,
including the LDS-pressure cases. Each of the 104 resource records independently
passes the full shared-budget reservation check.

## What this establishes

Changing the NOP scheduling yield bit alone does not produce the loss under
this construction. Almost full observable reuse savings remain at four NOPs
(reuse issue/completion slope34), about half remain at eight (slope66), and
none remain at sixteen (slope130). Thus reuse does not simply disappear upon
encountering any NOP or upon toggling that NOP yield bit.

The intermediate result is particularly useful: identical gap-limited MMA
throughput at66 does NOT imply no reuse; the LDS meter still distinguishes
reuse from discard strongly. Conversely, the approximately half-sized LDS
advantage does not prove a 50% hardware hit rate. Arbitration and traffic
timing can alter the meter response.

These are steady sequence slopes, not timestamps at individual MMA issue or
physical A-buffer release. The coarse sweep alone cannot identify a fixed
buffer timeout, distinguish expiry from pipeline/queue drain, or determine
whether partial savings represent partial tiles or alternating instructions.
It tests the NOP yield bit, not all possible scheduling control fields or
all competing warp configurations.

## Follow-up matrix

The fine/yield follow-up contributes232 output-validated configurations,
1392 launches and1160 retained samples. Only these completed cases are
used here; later uncompleted configurations contribute no measurements.
[Primary record](data/tcgen05_as_gap_followup_20261118/result.json.gz).

### Fine sweep

The following uses NOP yield1 / UTCHMMA yield1. Yield0 NOP pairs give the
same MMA slopes and the same qualitative LDS response.

| NOPs, stall8 | MMA reuse slope | LDS discard | LDS reuse | LDS advantage |
|---:|---:|---:|---:|---:|
| 5 | 42 | 47.906250 | 15.062500 | 32.843750 |
| 6 | 50 | 47.994792 | 15.963542 | 32.031250 |
| 7 | 58 | 47.671875 | 26.656250 | 21.015625 |
| 8 (coarse run) | 66 | 47.770833 | 31.890625 | 15.880208 |
| 9 | 74 | 47.192708 | 31.869792 | 15.322917 |
| 10 | 82 | 47.953125 | 31.750000 | 16.203125 |
| 11 | 90 | 47.734375 | 39.791667 | 7.942708 |
| 12 | 98 | 47.750000 | 47.750000 | 0 |
| 13 | 106 | 47.927083 | 47.927083 | 0 |
| 14 | 114 | 47.000000 | 47.000000 | 0 |
| 15 | 122 | 47.588542 | 47.588542 | 0 |

Near-full savings persist at slope50; partial savings appear at58, remain
near half of the continuous-control advantage at66–82, decrease further
at90, and vanish at98 and above in the sampled sequence. These are multiple
observable regimes, not evidence of a single all-or-nothing buffer TTL.
The start of substantial loss is bracketed by50/58 and its disappearance
by90/98 for this workload and diagnostic, not for arbitrary shapes or
physical fill-to-use timestamps.

### UTCHMMA yield controls

UTCHMMA yield0 preserves continuous discard/reuse slopes48/32 and LDS
advantage32.604167. At8 stall8 NOPs, it gives MMA slope65 and LDS
advantage16.416667, versus66 and about15.88 for MMA yield1. At16/32 NOPs,
the slopes become129/257 instead of130/258 and LDS advantage remains zero.
Both NOP yield values agree within these controls. Thus changing the MMA
yield encoding does affect pacing by one cycle in the sparse stream, but
does not independently eliminate reuse or restore it across the tested
long gaps. This is not a test of every scheduling field or every warp mix.

### Alternate NOP spacing control

The `spacing` suite reissues just8×8,16×4,32×2,64×1 NOP count×stall pairs,
both yield settings, with the same eight discard/reuse/meter/count cases.
The spacing run completed64 cases and384 launches with zero validation errors.
[Raw results and exact sources](data/tcgen05_as_gap_spacing_retry1_20261118/result.json.gz).
Representative short versions of all 32 spacing/reuse/meter encodings pass
strict dependency checking; the remote probe also checks every full kernel
before launch. This does not substitute for hardware execution validation.

| Count × stall | NOP yield | MMA discard | MMA reuse | LDS advantage |
|---|---:|---:|---:|---:|
| 8 × 8 | 0 | 66 | 66 | 15.880208 |
| 8 × 8 | 1 | 66 | 66 | 15.885417 |
| 16 × 4 | 0 | 66 | 66 | 15.880208 |
| 16 × 4 | 1 | 66 | 66 | 15.880208 |
| 32 × 2 | 0 | 157.234375 | 160.125000 | -0.302083 |
| 32 × 2 | 1 | 154.177083 | 146.223958 | -0.479167 |
| 64 × 1 | 0 | 384.000000 | 384.807292 | 0.031250 |
| 64 × 1 | 1 | 385.385417 | 384.682292 | -0.046875 |

Eight long-stall and sixteen shorter-stall NOPs have the SAME measured
pacing and reuse advantage, despite different instruction counts and stall
encodings. This rules out a simple NOP-count-only loss rule for these points.
The32/64-NOP cases are NOT equal-time controls: measured pacing is much
slower than the nominal64-cycle stall budget and also variable. Their loss
of advantage is consistent with their much longer measured intervals.
The cause of their extra front-end/issue delay was not isolated here; do
not use the nominal stall sums as physical elapsed time.

[Legacy HMMA interference follow-up](tcgen05_as_collector_hmma.md) tests
another instruction type and separates same-warp interleaving from a
continuous AS issuer with another warp performing HMMA.

Reproduce the completed summary:

```
python3 tools/analyze_tcgen05_as_gap.py notes/sm100/arch/data/tcgen05_as_gap_coarse_retry1_20261118/result.json
```

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
