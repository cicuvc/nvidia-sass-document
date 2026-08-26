# H800 L2 slice NUMA — empirical confirmation (sm_90)

Remote H800 PCIe (114 SMs visible, CUDA 12.4). Probe: `tests/h800_slice.cu`
(single-line L2 dependent-load latency via `ld.global.cg`, one block per SM,
swept over 16 address offsets at 256 B stride; per-SM latency recorded once).

## Result: 2 L2 slices with per-SM NUMA affinity
For a **fixed** line, per-SM latency is **bimodal**; sweeping the address offset
flips which SMs are fast. Classifying each SM by its fast-offset set gives two
dominant signatures that are **exact bitwise complements**:
```
1010010100001111   54 SMs   (group A: near slice-0 / far slice-1)
0101101011110000   48 SMs   (group B: near slice-1 / far slice-0)
```
So the probed offsets partition into "slice-0 lines" vs "slice-1 lines" (address
interleaving at ~256 B granularity, hashed), and the SMs split into two affinity
groups with **opposite** near/far assignment.

- **Latency gap**: near slice ≈ 245–265 cyc, far slice ≈ 290–305 cyc → **~40–50 cyc
  NUMA penalty** on an L2 hit depending on SM↔slice distance.
- **Group membership is periodic in SM index**, tied to physical GPC/TPC layout:
  group B = SMs {6–11, 20–25, 34–39, 48–53, 62–67, 76–81, 90–95, 102–107}
  (blocks of ~6 SMs, repeating every ~14), group A = the rest. Split 66/48 by the
  enumeration (not exactly half, reflecting SM numbering vs topology).

## Interpretation
H800's L2 is **two slices**, each physically closer to roughly half the SMs — a
NUMA topology (SM → near slice low latency, far slice higher). Each address has
one home slice (address-hashed at ~256 B), so a given line is fast for the SM-half
homed to its slice and slow for the other half. This matches the external claim
(“H800 = 2 slices, half the SMs direct-connected to each, NUMA-like”).

Contrast with **RTX 5090 (sm_120)**: aggregate global-atomic ceiling ≈ 90 Matom/s
(`notes/sm120/l2_slice_probe.md`) is consistent with a **single** L2 atomic/commit backend (1
slice) — no L2 NUMA split expected there. So slice count is arch/SKU-specific:
5090 = 1, H800 = 2.

## Consequences for the memory model
- The single-copy-per-address invariant still holds (one home slice per line) ⇒
  coherence-per-location + single-copy atomicity are unaffected; NUMA only changes
  *latency*, not ordering.
- Cross-slice ordering: with 2 slices, two independent commit points exist, so the
  ISA-level cross-location reordering that `MEMBAR` guards is *more* physically
  plausible on H800 than on a 1-slice part — but still bounded by each address
  having a single home slice. (Not separately re-tested here.)
- Performance note for operator writers: on H800, data placement relative to the
  producing/consuming SM's home slice affects L2 hit latency by ~40–50 cyc; there
  is no software control over slice mapping (address-hashed), so this is a
  statistical effect, not a tuning knob.

## Method notes
- `ld.global.cg` reaches L2 (bypasses L1) → dependent chase measures L2 round-trip
  latency (~250–305 cyc here), not L1 (~30 cyc).
- Single-line chase (self-pointing) keeps the probe on ONE slice; earlier
  multi-line chases (256 KB working set) averaged both slices and washed out the
  signal.
- One block per SM launched concurrently is fine because **reads to shared L2
  lines do not contend** — every SM samples cleanly in a single launch.

## Address → slice hash: attempted, mapping is NONLINEAR
Tests: `tests/h800_hash.cu` (single-bit toggles), `tests/h800_validate.cu`
(random-address validation), `tests/h800_lin.cu` (GF(2) linearity).
Method: a group-A SM is a slice detector (fast=home slice, slow=other); classify
`slice(addr)` by latency.

- **Single-bit toggles from address 0** (averaged over group A, clean 258 vs 285):
  toggling bits **{10,13,17,18,22,27,30,32,33}** flips the slice; bits 7,8,9 do
  not. So the finest interleave granularity is **bit 10 = 1 KB** (aligned 1 KB
  regions are single-slice; the earlier 256 B "alternation" was hash aliasing).
- **But the mapping is not a simple linear XOR of those bits:**
  - random-address validation of `slice = parity{10,13,17,18,22,27,30,32,33}`:
    **56 %** (≈ chance);
  - direct GF(2) test `slice(a^b) =? slice(a)^slice(b)` on random pairs:
    **12/20** (≈ chance);
  - the `11^12` pair already flipped despite neither bit flipping alone.
  So the single-bit-from-zero sensitivities describe *local* behaviour near
  address 0 and do **not** generalise — the address→slice function is a complex
  (nonlinear, or larger-structure) hash, as expected from NVIDIA deliberately
  hashing to spread traffic / defeat partition camping.

**Established:** 2 slices, per-SM NUMA affinity (~40–64 cyc gap), ~1 KB finest
interleave granularity. **Not recovered:** the exact address→slice function — it
is nonlinear and would need the full academic hash-RE methodology (large denoised
GF(2)/nonlinear solve), beyond a quick probe. For operator work this is moot:
slice placement is not software-controllable, so it is a statistical latency
effect only.

## Dataset dump for offline ML + why the hash resists recovery
Tests: `tests/h800_dump.cu`, `tests/h800_page.cu`, `tests/h800_vmm.cu`. Datasets
in `datasets/` (labels via relative latency of two NUMA SM-groups → robust, 0 %
ambiguous, median near/far gap ~27 cyc):
- `h800_slice_dataset.csv` — 200k random **virtual** addresses over 16 GB.
- `h800_page_map.csv` — all 16384 lines of a `cudaMalloc` 2 MB region.
- `h800_vmm_map.csv` — all 16384 lines of a **physically-contiguous** 2 MB VMM
  granule (`cuMemCreate`, granularity 2 MB).

Analyses:
- **Per-VA-bit correlation with label ≈ 0 for all bits.** This is *not* evidence
  against a linear hash — for a linear XOR hash every input bit is marginally
  balanced (corr 0). Wrong tool.
- **GF(2) exact solve: massively inconsistent** on all three sets. But GF(2)
  exact solve is brittle to *any* label noise, so this alone doesn't prove
  nonlinearity.
- **Walsh–Hadamard** on the fully-sampled within-granule map (`h800_vmm_map.csv`,
  label as a function of the 14-bit within-page index): best linear-mask
  correlation only **~0.28** (a clean linear hash → ~1.0). Top masks favour bits
  {10,13,...} weakly.

**Root cause — VA vs PA.** The slice is a function of the **physical** address.
Userspace controls only virtual addresses; `cudaMalloc` regions are physically
fragmented, and even a contiguous 2 MB VMM granule only exposes offset bits 7–20
as PA — the slice is dominated by **physical page-frame bits (≥21)**, constant
within a granule and not independently observable. Hence within-granule offset
explains the slice only weakly (~0.28), and random-VA datasets carry essentially
no learnable feature for the PA-based hash.

**To actually recover the hash** one needs physical addresses: a kernel-side
PA map for device memory, or a large contiguous-physical allocation whose base PA
is known, then sweep PA bits directly. Without that, ML on VA→slice is
fundamentally limited. The datasets are provided for experimentation, but the
`vmm` map (14 controllable PA-offset bits) is the only one with a real, if weak,
learnable signal.
