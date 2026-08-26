# Probing the L2 slice count (sm_120 / RTX 5090) — attempts & why it's hard

Goal: empirically determine how many L2 slices the crossbar+L2 model has (see
`ptx_memory_model_to_sass.md` §11 for the model). Tests:
`tests/l2_slice_probe.cu`, `tests/l2_slice_probe2.cu`, `tests/atomic_latency_test.cu`.

## Idea (that didn't work cleanly)
Since each address has one home slice, atomics to one address serialise at one
slice; atomics spread over all slices run in parallel. So naively
`throughput(spread) / throughput(single) ≈ #slices`.

## What actually happened
- **`atomic_latency_test.cu`**: a serial global-atomic chain to one address =
  **391 cyc/atomic** at every scope (one slice's RMW round trip); shared = 47 cyc.
- **`l2_slice_probe2.cu`** (one warp per distinct hot line, sweep #warps):
  aggregate atomic throughput scales **linearly to ≥1024 warps with no knee**
  (~constant per-warp increment). No saturation ⇒ the counting premise fails.

## Why it fails (the finding)
1. **A slice's atomic ALU pipelines *independent* addresses.** Only *same-address*
   atomics serialise (coherence). Different-address atomics — even to the same
   slice — pipeline. So adding warps just hides latency; we never reach a
   per-slice throughput ceiling within reach, and there is no knee at #slices.
2. **Address→slice mapping is hashed** (NVIDIA hashes address bits to pick the
   slice, specifically to defeat partition camping). So simple stride/coverage
   arguments don't map cleanly to slice indices.

Together these mean throughput-ratio / knee methods cannot count slices: the
observable ceiling is *total* L2 atomic-pipeline bandwidth (latency-hidden), not
`#slices × per-slice-serial-rate`.

## What WOULD work (not done — larger effort)
Reverse-engineer the address→slice **hash** via conflict timing: find pairs of
addresses that genuinely contend (only reliable signal = *same-address*
serialisation, or a same-slice resource conflict if one exists), build address
equivalence classes, and count them. This is the academic "dissecting the GPU
memory hierarchy" methodology (P-chase + hash recovery). Hashing + per-address
pipelining make it substantially harder than a simple microbenchmark.

## Practically
The slice/partition count is a fixed hardware fact tied to the memory subsystem
(GB202/RTX 5090: 512-bit GDDR7 ⇒ 16×32-bit channels; L2 = 96 MB; slice count is
a multiple of the channel count but NVIDIA does not publish it). For memory-model
/ ordering reasoning the *count* is irrelevant — what matters is the invariant we
did establish: **one home slice per address ⇒ per-location serialisation & single-
copy atomicity; cross-slice paths are independent ⇒ cross-location reordering**
(`ptx_memory_model_to_sass.md` §10–11).

## Incidental finding worth keeping
Global-atomic RMW latency ≈ **391 cyc** (SM→L2 slice→SM round trip), scope-
independent; shared-atomic ≈ **47 cyc** (SM-local unit). Per-slice atomic units
are **pipelined across distinct addresses** (linear throughput scaling, no
same-slice cross-address serialisation observed).

## RESOLUTION — L2 is ~1 monolithic OoO atomic backend, not many slices
Test: `tests/l2_monolithic.cu` — distinct-address atomics (no same-address
contention), sweep active lanes. Result: throughput scales linearly to ~16k lanes
then **saturates hard at ~90 Matom/s** and stays flat to 131k lanes.

~90 Matom/s **for the entire 170-SM GPU** = ~1 atomic every **~27 core cycles**
aggregate. If there were dozens of independent slice-ALUs the ceiling would be
thousands of Matom/s. So the atomic/ordering path is **one (H100: two) monolithic
backend**, matching the external claim (5090 = 1 slice, H100 = 2).

**Reframed model:** the L2 atomic/ordering path is a **single OoO memory backend**,
not N address-partitioned slices:
- pipelined/speculative OoO of independent addresses ⇒ linear scaling (latency
  hidden, ~27-cyc issue period) ⇒ good throughput from *one* unit;
- conflict-detect + rollback on same-address hazards (CPU LSQ-style violation
  replay) ⇒ coherence-per-location without partitioning.
So high atomic throughput comes from pipeline depth, not slice count.

**This explains the never-observed weak behaviour:** SB(0,0)/MP-weak were never
seen at `.gpu` scope because global traffic funnels through **one** commit point
(single OoO backend) ⇒ multi-copy atomicity + near-SC emerge structurally, not by
luck. The earlier "independent slices ⇒ cross-location reordering" idea assumed
many slices; with ~1 slice that reordering source largely collapses. Correction
applied to `ptx_memory_model_to_sass.md` §11.

**Two separate roles:** *data bandwidth* (plain ld/st) is wide (many
banks/partitions ⇒ TB/s); the *atomic/ordering commit* path is narrow (~1–2 OoO
backends ⇒ ~90 Matom/s, single commit point ⇒ strong ordering).
