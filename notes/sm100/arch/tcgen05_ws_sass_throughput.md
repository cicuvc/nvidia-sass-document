# B200 WS throughput: handwritten SASS (2026-11-17)

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

**Evidence:** sm100-silicon, Modal NVIDIA B200
**Probe:** `tests/asm_construct/probe_sm100_ws_throughput.py`
**Runner:** `tools/modal_ws_sass.py`
**Analysis:** `tools/analyze_tcgen05_ws_sass.py`

## Conclusion

With TMEM A and B reuse, M32N128/N256 and all tested M64/M128 shapes reach the 4096 MAC/cycle/SM BF16 baseline. Buffer-ID rotation independently removes discard penalties; rotating only B addresses does not. M32N64 reuse remains a 9-cycle case in the tested controls.

## Evidence

## Construction and validation

This extends the naked U-path construction in
`tests/asm_construct/utchmma_issue_base_sm100.sass` and the AS admission probes.
Dense BF16×BF16→FP32, K16, one CTA of 128 threads, warp 0 issues all MMAs.
The timed MMA stream contains no ELECT, PTX retry wrapper, or per-MMA GPR
address arithmetic (the allocator outside timing still uses ELECT).
Descriptors and TMEM addresses are fixed uniform registers. All MMAs accumulate
into one zero-initialized D. The primary stream is statically expanded, with
`[7:0:{}:1:1]` on each MMA; controls vary stall and add compact loops.

CS2R timing covers the MMA stream and a single UTCBAR completion/mbarrier wait.
Shared initialization, allocation, readback and deallocation are outside timing.
Report `(median(T1024)-median(T64))/960` cycles/MMA; T256 is a linearity check.
Each case has one warmup and five retained repetitions. Full output is checked
on every launch, including unused TMEM columns which must remain zero. With
shared A=1, one-address B=1 gives D=16×count; four B addresses contain 1/2/3/4
and give D=40×count. All four collector buffers have the same number of uses.

The modes independently rotate collector ID and B address:

| mode | collector | B address | operation |
|---|---|---|---|
| discard | b0 | fixed | discard every op |
| refill | b0 | fixed | fill every op |
| reuse | b0 | fixed | fill, use, lastuse |
| buffers | b0–b3 | fixed | discard every op |
| addresses | b0 | four-way | discard every op |
| both | b0–b3 | four-way | discard every op |
| reuse_buffers | b0–b3 | fixed | fill each, use, lastuse each |
| reuse_both | b0–b3 | four-way | fill each, use, lastuse each |

Additional controls use A from TMEM, stalls 0/4/12, loops with 16/64 MMAs per
iteration at lengths 1024/4096, and M128 AS with discard/A reuse. The AS controls
share this probe's initialization, timing and scalar observer.

Dependency checking remains enabled. The probe fails on every checker diagnostic
except `sb_capacity`: its static no-progress accounting over repeated SB0 read
claims does not model native MMA backpressure/draining. The exact advisory count
is recorded per kernel. Passing output checks does not validate arbitrary
scoreboard conventions outside these instruction streams.

## Shared-A results and collector separation

Cycles/MMA, completion slope from 64 to 1024 instructions:

| M | N | discard / refill | B reuse | rotate buffer only | rotate address only | rotate both |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 64 | 28 | 15 | 24 | 28 | 24 |
| 32 | 128 | 44 | 18 | 40 | 44 | 40 |
| 32 | 256 | 76 | 32 | 72 | 76 | 72 |
| 64 | 64 | 32 | 23 | 32 | 32 | 32 |
| 64 | 128 | 48 | 32 | 48 | 48 | 48 |
| 64 | 256 | 80 | 64 | 80 | 80 | 80 |
| 128 | 64 | 48 | 39 | 48 | 48 | 48 |
| 128 | 128 | 74 | 64 | 64 | 74 | 64 |
| 128 | 256 | 138 | 128 | 128 | 138 | 128 |

Four-buffer reuse, with either one or four B addresses, has exactly the same
slope as single-buffer reuse for all nine shapes. Refill equals discard.

The previous PTX rotate-discard experiment changed both buffer ID and address.
The independent SASS controls now locate that benefit in **buffer ID rotation**:
it saves 4 cycles for M32, and 10 for M128 with N≥128; changing B address alone
does not help. This is consistent with a per-buffer turnaround/reuse hazard
which can overlap across buffers, but does not identify the collector's physical
ports, banking, or precise release event. Only one versus four buffers is tested.

With four-buffer discard, all nine shapes fit
`max((M+N)/4, M*N/256)` cycles: the first term is logical BF16 K16 A+B bytes
at 128 bytes/cycle; the second is 4096 MAC/cycle. This is a compact empirical
service model, **not** a direct measurement of physical bytes or broadcast
multiplicity. Small shared-A reuse shapes retain additional overhead: N64 gives
`M/4 + 7`, and M32N128 gives 18 rather than the compute-only 16 cycles.

Compared with explicit-election PTX, small shared-A reuse drops from
16.594→15 (M32N64), 19.031→18 (M32N128), and 23.531→23 (M64N64).
The larger reuse cases retain their previous slopes.

## A-from-TMEM control

Same stream and B collector, with A stored at TMEM column 256 outside D:

| M | N | single-buffer discard | B reuse | reuse MAC/cycle |
|---:|---:|---:|---:|---:|
| 32 | 64 | 28 | 9 | 3641 |
| 32 | 128 | 44 | 16 | 4096 |
| 32 | 256 | 76 | 32 | 4096 |
| 64 | 64 | 28 | 16 | 4096 |
| 64 | 128 | 44 | 32 | 4096 |
| 64 | 256 | 76 | 64 | 4096 |
| 128 | 64 | 42 | 32 | 4096 |
| 128 | 128 | 74 | 64 | 4096 |
| 128 | 256 | 138 | 128 | 4096 |

Removing shared A service eliminates the small-shape reuse deficits except
M32N64's 9-cycle interval (8 cycles would be 4096 MAC/cycle). This directly
rules out an intrinsic factor-of-two M32 compute limit for N128/256 in the
measured WS configuration. M64/M128 reach that baseline for every tested N.
The 9-cycle case is an observed sequence limit, not proof of a 9-cycle arithmetic
wave; the primary stream repeatedly updates one D tile. The two-D control
below also retains 9 cycles.

## Scheduling, length and AS controls

The full scan passed **306 configurations / 1836 launches**, including warmups,
with zero output or guard-column errors. [Exact source, GPU information, hashes
and samples](data/tcgen05_ws_sass_full_20261117.json.gz).
For every primary case the 64→256 slope exactly equals the 64→1024 slope.
At N128, 16- and 64-MMA loop bodies at lengths 1024/4096 give the same slopes
as the static stream: discard=44/48/74, reuse=18/32/64 for M32/64/128.
Thus these rates do not depend on a large static instruction footprint.

Stalls 1/4/12 preserve the N128 rates (the completion timestamp differs by one
cycle for stall12). **Literal stall=0 is slower**, despite valid numerical
results: T1024/1024 is about 108.098/116.098/162.098 cycles for discard and
90.115/114.100/162.098 for reuse. This probe does not identify why; do not treat
stall=0 as a zero-cost or fastest scheduling control. The reported fast results
use stall1 and are supported by the stall4/12 and loop controls.

In the same harness, AS M128 discard slopes are 48/64/128 for N64/128/256;
A reuse gives 32/64/128. The larger-shape AS discard behavior agrees with
four-buffer WS discard, whereas single-buffer WS carries the additional 10
cycles. These are sequence-specific completion rates, not instruction latency
measurements.

## Focus controls: collector turnaround and the 9-cycle case

The follow-up passed **40 configurations / 240 launches**, including warmups,
with zero output or guard-column errors. Together with the full scan this is
**346 configurations / 2076 launches**. [Exact source and focus samples](data/tcgen05_ws_sass_focus_20261117.json.gz).

With A from TMEM, discard with four collector IDs and a **fixed B address**:

| M | N64 | N128 | N256 |
|---:|---:|---:|---:|
| 32 | 16 | 32 | 64 |
| 64 | 16 | 32 | 64 |
| 128 | 32 | 64 | 128 |

All nine points fit `max(N/4, M*N/256)` cycles/MMA: the shared-B payload term
and the measured compute baseline, without a shared-A term. Compared with
single-buffer TMEM-A discard, rotation removes 12 cycles for M32/M64 and 10
for M128. Rotating **only B address**, tested at N64 for all three M values,
retains 28/28/42 cycles, exactly matching the fixed-address single-buffer case.
This strengthens the interpretation of an overlapable per-buffer turnaround
cost. It does not establish whether that cost is collector fill, release,
scoreboarding, or another buffer-associated resource.

M32N64, A from TMEM, B reuse:

| control | cycles/MMA |
|---|---:|
| single buffer, single D, static stream, stall1 (full scan) | 9 |
| four collector buffers, same B address | 9 |
| alternating D at columns 0 and 128, stall1 | 9 |
| 16-MMA loop, 1024→4096 slope | 9 |
| 64-MMA loop, 1024→4096 slope | 9 |
| single D, stall4 | 9 |
| single D, stall12 | 12 |
| stall0, either single or alternating D | 74 |

Each alternating-D tile receives half the MMAs and is separately checked;
unused columns remain zero, and A at column 256 is disjoint. These controls
exclude a benefit from this particular two-D alternation and from four-way
collector reuse. They do **not** exclude a shared physical bank/port conflict,
A-read service floor, or U-path admission limit. The minimum established here
is 9 cycles, about 3641 MAC/cycle (8/9 of the 4096 baseline), not half-rate.
No precise physical cause for the remaining cycle is claimed.

## Buffer-ID conflict follow-up

[All-ID pair/ring/burst and mixed discard/reuse probes](tcgen05_ws_collector_conflicts.md)
now show that two distinct IDs already hide the refill penalty at N64 for
M32/64/128. No particular distinct pair is slower; AABB and AAAABBBB costs
exactly track the fraction of adjacent identical IDs. Mixed discard/reuse
also has no pair-specific asymmetry. This establishes a same-ID refill hazard
under these streams, not a physical collector-to-subcore mapping.

## Capacity / working-set follow-up

[Nonuniform B and shared-contention probes](tcgen05_ws_collector_capacity.md)
now cover every legal dense N with one through four active IDs. M32 reuse stays
at 9/16/32 cycles, with no sustained LDS contention slope above 0.045 cycles/MMA
in magnitude across all reuse controls, through a 32-KiB logical B working set.
This supports effective retention but does not measure an 8-KiB physical SRAM
per collector or exclude a smaller front end backed by distributed state.

## Reproduction

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_ws_sass.py --suite full --reps 5 --output /tmp/ws-sass-full
python3 tools/analyze_tcgen05_ws_sass.py /tmp/ws-sass-full/result.json
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_ws_sass.py --suite focus --reps 5 --output /tmp/ws-sass-focus
python3 tools/analyze_tcgen05_ws_sass.py /tmp/ws-sass-focus/result.json
```

`--suite smoke` runs nine short correctness cases. Direct execution of the probe
supports `--build-only --artifacts DIR` to export each expanded SASS/cubin.
The Modal runner prints per-case progress and saves exact generator source and
all timing samples. A 30-second OS alarm bounds each GPU launch; a queued Modal
call with no container is a separate condition and must be checked before
attributing a lack of output to an on-device hang.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
