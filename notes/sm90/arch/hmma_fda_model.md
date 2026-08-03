# Bit-accurate tensor-core fp16/bf16 model (FDA)

A pure-Python reference model that reproduces the SM120 `HMMA.16816.F32` /
`HMMA.16816.F32.BF16` outputs **bit-for-bit**, built and verified against the
hand-assembled HMMA harness.

**Files:** `tools/hmma_model.py` (model + self-test), `tests/asm_construct/test_hmma_model.py`
(random-fragment vs hardware), `tests/asm_construct/test_hmma_precision.py`
(targeted bit-level probes).

## Algorithm (FDA, after MMA-Sim arXiv:2511.10909)

Hopper HMMA (fp16/bf16, F32 accum) follows the **Fused-Dot-Add (FDA)** model:

1. **Specials**: any NaN in -> canonical `0x7FFFFFFF`; `0*inf` -> NaN; only one
   inf kind -> that inf; both `+inf` and `-inf` present (products or c) -> NaN;
   single `+inf * -inf` product -> `-inf` (sign of product).
2. **Products**: exact significand x exponent, no normalization (subnormal
   inputs honored).
3. **Align**: shift products and c to `e_max`, truncate (RZ) to `F=25`
   fractional bits (Hopper).
4. **Sum**: exact fixed-point addition (order-independent).
5. **Normalize**: to FP32 with **RZ at the 23rd fractional bit** (not RNE);
   `|result| >= 2^128` -> inf; subnormal range preserved down to 2^-149.

The distinctive observable behaviors, all verified on SM120:
- Output rounding is **RZ**: `1.0 + 3*2^-24` (=1.5 ulp) truncates to 1 ulp
  (`0x3f800001`), symmetric for negatives (`0xbf7ffffe`); RNE would give 2 ulp.
- NaN canonicalizes to `0x7FFFFFFF` (not quiet/signaling preserved).

## m16n8k16 fragment layout (probed on hardware)

A 16-word fragment `[a0..a3, b0..b1, c0..c3]` (each a/b word = 2 half values,
little-endian lo/hi) feeds 4 D outputs.  D0 and D1 share one set of 16 k-pairs,
D2 and D3 share another; each (a-slot, b-slot) pair is folded 4x (the 4 k
values one bf16 slot covers):

```
D0/D1 = fda(c0, P) ; D1 = fda(c1, P)      P = {a0.lo,b0.lo}x4 {a0.hi,b0.hi}x4
                                          D2/D3 use Q = {a1.lo,b0.lo}x4 ...
```

`hmma_model.frag_pairs()` encodes this mapping; `hmma_model.hmma_frag()` returns
the 4 D values as FP32 bits.  (The same layout serves both bf16 and f16 —
identical 16-bit packing.)

## Verification

- 14 vector self-tests (RZ ±, exact sum, NaN/0·inf/±inf, overflow, f16
  subnormals) — matches the `test_hmma_precision.py` hardware probes.
- 40/40 random signed fragments (incl. NaN/inf/0 in a/b/c) bit-exact vs the
  simulator's HMMA, bf16 and f16 (test_hmma_model.py runs 8+8 in CI).

## Open questions

- The 4x slot repetition is an *observed* equivalence (D == fda with 4 identical
  pairs); it is not derived from the PTX fragment tables, and may hide a
  different internal k-grouping that happens to be FD-equivalent.
- CoFDA (chain-of-FDA) shapes, e.g. the Ampere `HMMA.16816.F32` path, are not
  modeled here — only the Hopper FDA(F=25) behavior is covered.
- 2:4 sparse (`HMMA.SP`) and indexed-RF (`INDF`) variants are out of scope.
