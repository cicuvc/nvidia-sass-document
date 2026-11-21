# B200 AS A-collector source-erasure control

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

B200 silicon, 2026-11-17. Probe `tests/asm_construct/probe_sm100_as_retention.py`;
runner `tools/modal_as_retention.py`. [Exact source and raw results](data/tcgen05_as_retention_20261117.json.gz).
Modal app `ap-4MgjlVF3ekyoz9F1z1n5jn`.

## Conclusion

After fill completion, synchronization, and source erasure, AS reuse queries return the erased source value for both shared and TMEM A. Independent CUDA/PTX and pre-erasure full-D checks confirm this result. Continuous issue-stream reuse remains useful; these tests do not isolate which event ends its eligibility.

## Evidence

## Construction

M128 N256 K16 BF16. AS A_KEEP fill, commit/wait phase 0, CTA rendezvous,
optional source erasure, matching async-view fence and CTA rendezvous,
then AS A_REUSE or discard query, commit/wait phase 1, scalar LDTM readback.
Both MMAs overwrite D (!UPT). B is unchanged nonuniform finite BF16 input.

Shared-A control starts with all ones and erases 4 KiB shared A using all
128 threads. TMEM-A starts with repeated I16 (128 rows, eight packed-BF16
columns), so output exposes every K/N element of B. All four warps execute
STTM.x8 to overwrite all four 32-row chunks, then FENCE.VIEW.ASYNC.T with
an explicit scoreboard wait. Zeroing only issuer warp zero would be inadequate.
No-erasure controls still execute the same fences and CTA rendezvous.

## Results

| A source | Erased after fill completion | discard query | reuse query |
|---|---|---|---|
| shared | no | expected original result | expected original result |
| shared | yes | zero | zero |
| TMEM | no | expected original result | expected original result |
| TMEM | yes | zero | zero |

Eight configurations, five repetitions each: **40 successful launches**.
Every launch checks all 32768 FP32 output words, with per-chunk counts;
all four chunks agree, no mixed/other values. Numerical controls pass.

This establishes that source-erasure reuse failure is not specific to shared A.
It does not isolate whether completion, time gap, CTA synchronization, source
writes or view fences end the AS reuse opportunity. In particular, correct
unmodified-source output cannot show that a collector hit occurred. Do not infer
that TMEM-A never uses a collector, or that commit alone invalidates AS state.
The earlier continuous-sequence AS reuse throughput benefits remain valid.

## Independent CUDA/PTX replication

`tests/tcgen05_as_retention.cu` compiled unmodified by CUDA 12.8.1 nvcc/ptxas
on Modal B200 (app `ap-wO19Pyj8uaOC0yj7QPGnXO`). No custom assembler, binary
patches, or handwritten scheduling. Local CUDA 13.1 compilation also succeeds
with explicit `-gencode arch=compute_100a,code=sm_100a`; its shorthand `-arch`
executable build attempted an additional unsupported compute_100 target.

Both shared and TMEM A are repeated I16; B is nonzero exact BF16 values
`(1+(7*n+3*k)%31)/16`. Thus all old output values are distinguishable from
zero, and every K/N value is observed. Source erasure is performed after the
first commit/wait. CUDA CTA synchronization, PTX async-view fences and explicit
TMEM store/load waits replace hand schedules. All 128 threads clear their TMEM
rows. The final MMA overwrites D. This is a related independent implementation,
not an instruction-for-instruction reproduction of the SASS sequence.

Twelve configurations: shared/TMEM x intact/erased x discard/use/lastuse,
five repetitions each, **60 launches pass**. All intact cases return original
B. All erased cases return zero, including both use and lastuse. No other
values occur among the 32768 output words per launch.

Remote cuobjdump verifies fill -> A_KEEP, use -> A_REUSE.A_KEEP,
lastuse -> A_REUSE, discard -> neither. In particular the earlier handwritten
A_REUSE-only query was technically lastuse, not PTX use; testing both removes
that distinction as an explanation for the observed zero results.

[CUDA source, compiler version, complete SASS and raw results](data/tcgen05_as_retention_ptx_20261117.json.gz).
Run with the existing runner:

```
/home/cicuvc/miniconda3/envs/blkw/bin/python -m modal run tools/modal_tcgen05_ws.py --source tests/tcgen05_as_retention.cu --reps 5 --nvcc-flags '-gencode arch=compute_100a,code=sm_100a' --output /tmp/as-retention-ptx
```

The CUDA probe currently runs five repetitions internally. This confirms the
phenomenon is not specific to handwritten scheduling or the custom assembler.
It still does not isolate the invalidating event: completion/synchronization,
elapsed time, source modification and fences all remain in the sequence.

## Completion-order audit: source not cleared before initial A consumption

`tests/tcgen05_as_retention_sync.cu`, CUDA/PTX only; Modal B200 app
`ap-yYEd33iTOlvvUVXpvCZAUa`, CUDA 12.8.1. Explicit compute_100a/sm_100a target.
[Full source, disassembly and output](data/tcgen05_as_retention_sync_20261117.json.gz).

The hypothesis tested is that initial A loading is still outstanding when the
source is zeroed, because the completion wait was ineffective. Two orthogonal
controls are added, both after the original first commit/wait:

1. Initialize all D to -7 before the first MMA. Optionally read all 32768 D
   values into a separate global snapshot before ANY source erase; each LDTM
   has a wait::ld, then all source writers rendezvous. Host validates the
   snapshot against I16*B. Output buffers are reset to 0xff each launch.
2. Optionally spin on clock64 for at least 100000 SM clock cycles on the issuer,
   then release all source writers through a CTA barrier. This can be tested
   without any intervening LDTM, avoiding a readback-induced collector effect.

Matrix: shared/TMEM x intact/erased x discard/use x snapshot off/on x delay
0/100000, five repetitions = **32 configurations / 160 successful launches**.
All 80 snapshot launches have pre_bad=0: every initial output is complete and
correct before clearing A. In all four snapshot/delay combinations, intact
sources yield original B and erased sources yield zero, for both discard and
A_REUSE.A_KEEP. No unexpected values. Disassembly confirms the completion wait,
optional LDTM/STG snapshot, clock loop and CTA rendezvous precede the source
zeroing stores; TMEM clear writes eight A columns in all four warp chunks.

This rules out clearing A before the first MMA consumed it as an explanation
for these controlled zero-result cases. It does not independently prove every
original wait-only execution was race-free, nor isolate the AS invalidation
mechanism. Snapshot readback changes the instruction stream, but the separate
no-readback long-delay control gives the same final result. Completion fences,
source writes, time gaps and synchronization remain candidate causes of loss
of reuse. No conclusion that B200 lacks A-collector hardware follows; prior
continuous AS reuse throughput and shared-traffic controls still show benefits.

Reproduce using `tools/modal_tcgen05_ws.py` with
`--source tests/tcgen05_as_retention_sync.cu`,
`--nvcc-flags '-gencode arch=compute_100a,code=sm_100a'`.
The probe uses five repetitions internally.

## Commit boundary versus issue gap

[Immutable-source timing and LDS controls](tcgen05_as_collector_commit.md)
show that per-MMA commit without waiting preserves AS reuse benefits, while
a 32-NOP issue gap removes those benefits even without intermediate commit.
This favors short-lived pipeline retention over a strict commit-group lifetime.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
