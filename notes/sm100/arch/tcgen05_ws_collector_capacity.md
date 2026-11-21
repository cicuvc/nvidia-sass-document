# B200 WS collector working-set / capacity probes (2026-11-17)

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

**Evidence:** sm100-silicon, Modal NVIDIA B200
**Probe:** `tests/asm_construct/probe_sm100_ws_throughput.py --suite capacity`
**Runner:** `tools/modal_ws_sass.py`
**Analysis:** `tools/analyze_tcgen05_ws_capacity.py`

## Conclusion

The tested WS workload retains an effective working set of four distinct 8-KiB B tiles without a reuse-throughput cliff or a growing sustained shared-contention signal. This is a logical retained working set, not a direct SRAM-capacity measurement; source-erasure tests provide the independent retention check.

## Evidence

## What can be tested legally

[PTX 8.7 Table 39](https://docs.nvidia.com/cuda/archive/12.8.1/parallel-thread-execution/index.html#tcgen05-kind-shapes)
restricts dense BF16 WS to M32/64/128, N64/128/256, K16. The N field's encoding
step of eight does not make intermediate WS shapes valid. Consequently this
probe does not sweep N136 or try an oversized N512 instruction.

The logical B payload is 32N bytes: 2/4/8 KiB per tile, and 2..32 KiB for one
through four distinct active IDs. The same table doubles K for sparse WS but
limits N to 64/128, again capping BF16 B payload at 8 KiB. TF32 and FP8 listed
shapes have the same maximum logical B payload. This is consistent with a
bounded operand footprint; it does not identify physical collector capacity.

Eight KiB per collector was previously a **conditional full-tile storage
budget**, not a measured capacity or a demonstrated lower bound on one SRAM.
Storage could be distributed, partially retained with refetch, or combined with
other operand staging. A successful N256 reuse timing alone cannot distinguish
these possibilities because arithmetic can hide operand fetch.

## Probe and independent traffic indicator

A is in TMEM and consists of BF16 ones. B consists of four distinct deterministic
nonuniform matrices (seed 20261117). Every element is drawn from 512 signed,
nonzero BF16 values of magnitude 0.5 through 1.9921875. The no-swizzle K-major
layout is populated by host-to-global-to-shared copy before timing. The CPU
sums the actual BF16 inputs; all dot products and accumulated references here
remain exactly representable in FP32. Every measured launch checks all D values
and zero guards outside the logical output footprint.

The scan varies:

* M32, all three N values, one/two/three/four active IDs, discard versus reuse.
* Reuse first fills each ID, then uses it until a final lastuse; each ID refers
  to its own B address. Counts 96/768 are divisible by all ring lengths.
* With and without three simultaneous LDS meter warps.
* M64/M128 four-ID reuse controls across all three N values.
* A meter-only control with no MMA operations (the final commit/wait remains).

Each case has one warmup and five retained repetitions. The issuing warp uses
naked static SASS, stall1, one final UTCBAR and completion wait. Report
`(median(T768)-median(T96))/672` cycles/MMA. First-fill costs are fixed per ID,
so the length difference removes them from the sustained slope.

Meter warps 1..3 each load a separate 6-KiB shared scratch region. Each loop
issues twelve LDS.128 instructions, waits for results, and updates a checksum.
The scratch regions do not overlap A/B or one another. There are 2048 iterations,
so the three warps request 294912 logical 128-byte wavefronts. All three timing
windows and checksums are recorded; the final loaded vectors are also checked.
The meter continues beyond the MMA stream and the common CTA barrier keeps all
threads alive until both activities finish. Thus its **total completion span**
can expose shared contention even if MMA itself remains compute-limited.

The additional observable is
`(median(LDS_span768)-median(LDS_span96))/672`.
A rise in this quantity with N or active IDs, especially while MMA timing stays
flat relative to compute work, would be evidence for sustained refetch or other
shared-path activity. Discard provides a positive control at each working set.
This is a contention indicator, **not a hardware read-byte counter**: phase,
arbitration and less-than-perfect saturation prevent a direct cycles→bytes
conversion or a precise SRAM-capacity lower bound.

## Results

**121 configurations / 726 launches**, including warmups, passed every output,
guard and LDS check. [Exact source, input hash, per-case SASS/cubin hashes and
samples](data/tcgen05_ws_capacity_20261117.json.gz).

The LDS-only span is 411795 cycles, or **0.716162 logical wavefront/cycle**.
All three meter warps overlap at least 91.89% of the MMA interval for short
streams and 98.875% for 768-MMA streams. They start at most 79 cycles after the
MMA timer and finish at least 313538 cycles after MMA completion. The within-case
range is zero cycles for MMA and at most one cycle for LDS across five samples.

For M32, reuse slopes with 1/2/3/4 active IDs are:

| N | B tile | four-ID footprint | reuse cycles/MMA, all four working-set sizes | LDS-span slope, reuse range | LDS-span slope, discard range |
|---:|---:|---:|---:|---:|---:|
| 64 | 2 KiB | 8 KiB | 9 | -0.0432 .. 0.0119 | 15.8170 .. 15.8467 |
| 128 | 4 KiB | 16 KiB | 16 | -0.0208 .. -0.0045 | 31.8170 .. 74.5372 |
| 256 | 8 KiB | 32 KiB | 32 | -0.0015 .. 0.0193 | 63.7247 .. 63.7976 |

MMA reuse slopes are exactly unchanged with the meter enabled. M64 four-ID
reuse gives 16/32/64 cycles, and M128 gives 32/64/128, for N64/128/256, also
unchanged under contention. Across all reuse controls the LDS-span slope has
absolute magnitude below 0.045 cycles/MMA.

**There is no observed working-set cliff or growing sustained shared-contention
signal up to four distinct 8-KiB B tiles.** The steady slopes depend on shape,
not the number of retained IDs. Discard positive controls clearly perturb the
meter, whereas reuse stays near the meter-only behavior after fixed costs are
removed. This argues against a large sustained B refetch path under these tests.
It does not prove that every byte is retained in a separately identifiable SRAM.

Cold-fill overhead does grow with working set. The unconstrained M32 reuse
intercept `T96 - 96*slope` is:

| N | 1 ID | 2 IDs | 3 IDs | 4 IDs |
|---:|---:|---:|---:|---:|
| 64 | 110 | 118 | 124 | 132 |
| 128 | 120 | 136 | 152 | 168 |
| 256 | 136 | 168 | 200 | 232 |

These intercepts include timing, launch-stream startup and final completion
costs; they are not standalone fill latencies. At N128/N256, each additional
initially filled ID adds 16/32 cycles while the long-stream reuse slope stays
constant. Thus the N-dependent cold-fill cost is distinguishable from a capacity
failure that would repeat on subsequent uses.

The N128 multi-ID discard meter slope (74.537) exceeds the nominal 32 shared
wavefronts per B tile. This is direct evidence that the meter can amplify
arbitration/phase changes and is not a linear byte counter. Tiny negative reuse
slopes are likewise timing-phase effects, not negative traffic. Partial refetch
hidden by spare service slots cannot be strictly excluded at 0.716 utilization.

The strongest supported statement is an **effective reuse working set of up to
32 KiB of logical B payload with no detected sustained penalty**, not a measured
32-KiB physical SRAM or an 8-KiB per-ID physical capacity lower bound. A smaller
collector front end plus distributed operand/PE storage remains compatible.
For example, if an M32 tile is retained by N-sharding across four chunks, an
8-KiB logical B tile is only 2 KiB per chunk per ID; that is a storage-layout
hypothesis, not an observed physical mapping. The tests do not distinguish a
systolic array from another compute fabric.

## Reproduction

```bash
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_ws_sass.py --suite capacity --reps 5 --output /tmp/ws-capacity-full
python3 tools/analyze_tcgen05_ws_capacity.py /tmp/ws-capacity-full/result.json
```

`--suite capacity_smoke` runs nine short correctness and meter controls before
the full matrix. Exact generator source and per-case SASS/cubin hashes are saved
by the runner.

## Source-erasure follow-up

[Complete-B retention after source erasure](tcgen05_ws_collector_retention.md)
now provides stronger evidence: all four IDs retain their full original tiles
after shared B is zeroed and computation drained, including late runtime query
selection and a near-full BF16 alphabet. This constrains small-store/refetch
models without identifying physical SRAM topology.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
