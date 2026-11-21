# AS shared-B fetch tomography using identity A

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-18
**Probe:** `tests/asm_construct/probe_sm100_as_b_fetch.py` on Modal NVIDIA B200
**Open items:** 1
**Audit:** full coarse/fine/tagged B200 readbacks validated; physical fetch granularity remains unresolved

## Conclusion

The B200 coarse, fine, and distinct-element-tag sweeps completed 912, 5856,
and 3072 launches with no output or timing validation failure. B input-version sensitivity advances with N.
The fine sweep observes mixed old/new results for 256/512-byte stores, always
as whole 128-byte **K8 × N8** regions in the sampled cases. This is an observed
mask grouping, **not an identified physical B-fetch transaction size**.

Reversing the assignment of lanes to shared-memory chunks reverses which
regions are new at the same measured phase. For example, a 256-byte update at
N192 and phase +37 gives K0–7 new with ascending lanes, but K8–15 new with
reversed lanes. Thus the writer materially determines the masks; interpreting
their 128-byte units as an intrinsic atomic tensor-input read is unjustified.
Distinct exact BF16 tags independently validate the K/N mapping and reproduce
the prefix/suffix masks; the effect is not an ambiguity of constant-valued B.

## Evidence

Follow-up [sparse B-staging tests](tcgen05_as_b_staging.md) reduce the update
to a single N column and retain the N8 cutoff grouping. Separately modified
K8 halves follow cutoff curves one cycle apart; a same-launch LDS→LDTM
control observes new shared bytes before a still-sentinel D read, while final
D uses old B. These constrain staging behavior without identifying a physical
K16×N8 buffer.

The [ordered-control run](data/tcgen05_as_b_fetch_sync_20261118/result.json.gz)
completed with zero output/control errors, outside-region changes, unexpected
values, or disagreements between the eight repeated identity rows. All five
timestamps and the clock-wait arithmetic checks passed.

The [complete coarse run](data/tcgen05_as_b_fetch_coarse_sync_retry_20261118/result.json.gz)
also has zero control errors, outside-region changes, unexpected values, or
repeated-M disagreements. There are 3 repeats per configuration. The nominal
16-cycle delay steps collapsed to only five measured phases; each sampled
region was uniformly old or uniformly new in all eight M repetitions:

| N start | phase −64 | phase −7 | phase +50 | phase +107 | phase +164 |
|---:|---|---|---|---|---|
| 0 | new | old | old | old | old |
| 64 | new | new | old | old | old |
| 128 | new | new | old | old | old |
| 192 | new | new | old | old | old |

This table holds for STS/STS.64/STS.128 and, for STS, both K0–7 and K8–15
regions. Phase is pre-store timestamp minus the first post-MMA timestamp;
it is not a timestamp of either the physical store transaction or the B read.
The measured writer interval is 11 cycles and post-MMA-to-done is 223 cycles
throughout this run. Width-independent fence timing does not establish atomic
writer visibility. The common responses of the two K halves are only at the
coarse sampled phases, not evidence of simultaneous reads.

### Fine results: writer-dependent mixed masks

The [complete fine run](data/tcgen05_as_b_fetch_fine_20261118/result.json.gz)
contains 288 controls and 5568 racing samples. All full D payloads were checked
again offline, including outside-region values, eight M repetitions, exact
control values, and clock-wait arithmetic. Every error counter is zero.

There are **87 mixed samples**: 18 with ascending lanes and 69 with reversed
lanes. None of the tested 128-byte stores produced a mixed output. Every
mixed sample is a union of whole aligned 128-byte K8 × N8 tiles; none splits
such a tile. For a 512-byte patch at N=n, number its contiguous 128-byte tiles:

| tile | K | N |
|---:|---|---|
| 0 | 0–7 | n..n+7 |
| 1 | 8–15 | n..n+7 |
| 2 | 0–7 | n+8..n+15 |
| 3 | 8–15 | n+8..n+15 |

Ascending-lane mixed masks select a prefix of those tiles; reversed-lane
mixed masks select a suffix. Examples below compare the **same measured
phase**, not merely the same nominal delay:

| update | N | phase | ascending lanes: new region | reversed lanes: new region |
|---|---:|---:|---|---|
| 256 B, K16 × N8 | 192 | +37 | K0–7 × N192–199 | K8–15 × N192–199 |
| 512 B, K16 × N16 | 0 | −16 | tiles 0,1 | tiles 2,3 |
| 512 B, K16 × N16 | 64 | +1 | tile 0 | tiles 2,3 |
| 512 B, K16 × N16 | 192 | +33 | tile 0 | tiles 2,3 |

The reverse 512-byte writer also produces three-new-tile masks (tiles 1,2,3),
two-new-tile masks (2,3), and one-new-tile masks (3). This is consistent with
different chunks of one wide STS becoming visible at different times. It
does not by itself locate or timestamp a physical shared-memory transaction.

For single-128-byte updates, these are the latest sampled all-new and earliest
sampled all-old phases. Both lane assignments agree; gaps contain unsampled
times and must not be replaced by exact thresholds:

| N | K0–7: latest new / earliest old | K8–15: latest new / earliest old |
|---:|---:|---:|
| 0 | −12 / −7 | −12 / −7 |
| 64 | +6 / +10 | +6 / +10 |
| 128 | +18 / +24 | +24 / +26 |
| 192 | +39 / +41 | +39 / +41 |

At N128, phase +24 distinguishes the two K halves: K0–7 is old and K8–15 is
new in separate equal-width updates. This is finer positional sensitivity
than the coarse scan exposed, without uniquely determining read granularity.

[Phase plots, SVG](data/tcgen05_as_b_fetch_fine_20261118/phases.svg) ·
[PNG](data/tcgen05_as_b_fetch_fine_20261118/phases.png) ·
[full mask analysis](data/tcgen05_as_b_fetch_fine_20261118/analysis.txt).

### Distinct-element validation

The [tagged run](data/tcgen05_as_b_fetch_tagged_20261118/result.json.gz) completes
all 3072 launches (288 controls, 2784 racing samples). Each updated BF16
element is distinct within its patch; shared-memory readback is stored in
canonical address order even when lanes are reversed. The full output matches
either the old value or that coordinate's exact new tag, with zero outside
changes, wrong tags, control errors, or repeated-M disagreements.

There are 57 mixed samples. Every one again consists of whole K8 × N8 tiles:
ascending-lane 512-byte stores produce `1000` or `1100`, and reversed stores
produce `01` (256 B) or `0001` / `0011` / `0111` (512 B). Here bits enumerate
128-byte tiles in ascending physical address order. No mixed tile is split
internally, and no 128-byte update is mixed. The exact observed phase grids
differ after adding tag-generation instructions, so the two binaries are not
treated as samples of one exact numerical threshold.

[Tagged analysis](data/tcgen05_as_b_fetch_tagged_20261118/analysis.txt) ·
[tagged phase plot](data/tcgen05_as_b_fetch_tagged_20261118/phases.svg).

## Fine sweep design

`--suite fine` selects one of 29 straight-line delay arms (nominal padding
0..56 by 2) before the clock wait. Every arm waits on the future epoch, executes
its NOP padding, then branches to the same timestamp/store sequence. Runtime
coarse offsets −64 and 0 cover adjacent polling buckets. Interpretation still
uses measured phase, not the nominal NOP count. This avoids relying on an
indirect branch or shortening the now-validated CS2R dependency gap.

Both lane mappings are tested: `lane_xor=0` assigns ascending chunks, and
`lane_xor=31` reverses the assignment of lanes to those same contiguous chunks.
The latter is a writer-side perturbation, not a claim that physical SRAM
transactions must reverse. All 16 regions × 2 mappings × 3 controls run first;
then 16 × 2 × 2 offsets × 29 padding settings are scanned. At 3 repeats this
is 288 controls + 5568 racing samples = 5856 launches. All 48 kernel variants
pass full sm100a assembly and strict dependency checking before submission.

2026-11-18. The user abandoned the ATEXIT fault-snapshot approach after their
separate work with DeepSeek established that the exception path does not invoke
that handler. This experiment uses successful MMA completion and an intentional
input race; it does not depend on exception handling.

Probe: `tests/asm_construct/probe_sm100_as_b_fetch.py`.
Runner: `tools/modal_as_b_fetch.py`.
Analyzer: `tools/analyze_tcgen05_as_b_fetch.py`.

## Construction

One M128 N256 K16 BF16 AS overwrite UTCHMMA, no A reuse. TMEM A is eight
repetitions of I16, so mathematically D[m,n]=B[m mod16,n]. This exposes individual
K contributions and eight copies of the same B elements across the M axis.
The entire128x256 D is exported using the newer scalar LDTM observer only
after final MMA completion and the modifier's CTA rendezvous.

B begins as BF16 ones at shared0x2000. Warp0 submits the single MMA; warp1
changes one contiguous, aligned B region to BF16 twos with ONE STS instruction.
Both follow a shared future clock epoch, with runtime modifier delay. The
clock poll uses signed modular differences to handle clock-low wraparound.
Warps2/3 participate in initialization, TMEM row setup/readback and rendezvous.

The no-swizzle K-major B mapping, in bytes from B base, is:

```
2 * ((n//8)*128 + (k//8)*64 + (n%8)*8 + k%8)
```

| Written bytes per warp | Instruction | Logical B footprint |
|---:|---|---|
| 128 | STS (32 bits/lane) | K8 x N8 |
| 256 | STS.64 | K16 x N8 |
| 512 | STS.128 | K16 x N16 |

Test N starts0/64/128/192, including both K halves for128-byte stores:16
patch configurations. Host checks verify the8192-byte mapping is bijective
and all patch sizes/shapes match the table. Full sm100a assembly and strict
dependency checking pass for all16 kernels, with only existing sb_capacity
advisories accepted.

The entire 16-patch control matrix runs before any timed mutation: no
modification, modification before MMA, modification after MMA completion.
The before control uses a separate CTA barrier after the writer fence and
before the producer submits MMA; the after control uses that barrier after
MMA completion and before the writer. Idle warps also participate. Racing
kernels contain neither of these extra barriers. The control D must match every
element, including the first columns. Every run also reads back the modified
shared region after rendezvous to verify the store actually wrote the intended
values. Outside-patch D values must remain1. Unexpected in-patch values and
disagreement between repeated identity rows are retained in diagnostics.

The coarse suite uses modifier offsets -80..160 in steps of16, three repeats,
plus the three controls:304 configurations /912 planned launches. These are
nominal offsets; analysis groups by measured times instead.

Five clock64 timestamps are saved: pre-MMA, first instruction after MMA
(admission upper bound), completion-wait finished, pre-store, and post-fence.
The full D raw bytes are losslessly compressed per sample; remote stdout is
also compressed for result transport to avoid the previous Modal large-return
failure. Runtime parameters allow each patch's cubin to be reused across delays.

The epoch is now read unconditionally, with conservative padding before its
dependent arithmetic; only thread zero publishes it. Clock polls also pad
the CS2R-to-subtract dependency. Host checks verify the saved target equals
epoch+512+delta, the saved subtraction equals observed-target modulo 2^32,
and the wait exits on a nonnegative signed difference. This fixes the observed
stale-operand symptoms without claiming a minimum CS2R latency measurement.

## Interpretation limits

This is deliberately racing an input of an asynchronous operation, not a
portable PTX correctness test. A final D pattern labels which input versions
were consumed, not the time at which each TMEM column retired.

In particular, one STS instruction is NOT assumed to be an atomic128/256/512-byte
update. A mixed pattern can arise when a fetch samples a partially completed
writer, even if that fetch itself is atomic. Conversely, uniformly old/new
results do not prove a particular atomic fetch size. Compare store widths,
K halves, N positions, measured writer durations, and repeated M rows before
attributing a boundary to the tensor input path. Timing around the proxy fence
also does not directly timestamp an internal SRAM-port transaction.

Unique element tags provide an independent mapping control: the updated
BF16 word at byte offset b within the patch has bits `0x4000 + b/2`.
`--suite tagged` retains the fine delay arms and both lane mappings, with one
coarse offset per region (−64 for N0; 0 for N64/128/192). This gives 288
controls + 2784 racing samples = 3072 launches. The same canonical shared
readback and every D element are checked against those distinct exact values.

## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains the current findings and primary evidence.

## Open questions

- Determine a physical fetch granularity independently of the writer's
  chunk visibility. The present 128-byte mask grouping cannot settle it.
  <!-- open-question: open blocked-by "needs an independently characterized finer writer or another read-side observable" -->
