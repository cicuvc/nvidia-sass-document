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

## QMMA (fp8) extension — m16n8k32 e4m3

`tools/hmma_model.py` also models **QMMA.16832.F32.E4M3.E4M3** (SM120), the
fp8 path, reusing the exact FDA machinery with two fp8-specific behaviors
(probed on hardware):

1. **fp8 inputs carry NO special values.**  The e4m3 all-ones exponent is an
   *ordinary* exponent: `0x7C` = 384, `0x7E` = 448.  Only the fully all-ones
   byte `0x7F`/`0xFF` is NaN (canonical `0x7FFFFFFF`).  There is no fp8
   infinity; only the FP32 accumulator C propagates NaN/inf.
2. **Fragment layout** reuses the HMMA register packing — each 16-bit slot is
   split into two 8-bit fp8.  fp8 byte *i* pairs only with byte *i* (no
   cross-byte), each pair folds 4 k:
   ```
   D0/D1: {a0.i,b0.i} {a2.i,b1.i}   i in 0..3   (8 pairs x 4k = 32k)
   D2/D3: {a1.i,b0.i} {a3.i,b1.i}
   ```
   `qmma_frag_pairs()` / `qmma_frag()` implement this.

Verified: D matches nvcc `mma.sync.aligned.m16n8k32.row.col.f32.e4m3.e4m3.f32`
(sm_120; sm_90 ptxas splits it into two HMMA.16816.F32), the model is
bit-exact on random signed fragments (incl. exp-15 patterns), the FDA F=25
align step holds (C bit at 2^-14 preserved → 5.0+2^-14), and output rounding
is RZ (1.5 ulp → 1 ulp).  `decode_qmma.py` covers the 0x27a encoding.

## QMMA.SF — block scaling (MXFP8, sm_120)

`QMMA.SF.16832.F32.{srcFmtA}.{srcFmtB}.E8 Rd, Ra, Rb, Rc, Re, Rh, URi`
(opcode 0x47a) is the block-scaled fp8 MMA; `MXQMMA.SF...` (0x47e) is the
smaller-format (S2_6) sibling.  This is the SASS for PTX
`mma.sync.aligned.m16n8k32.row.col.kind::mxf8f6f4.block_scale.scale_vec::1X
.f32.<atype>.<btype>.f32.ue8m0` (sm_120a).

Semantics (per the OCP MX spec, arXiv:2511.10909 appendix, and PTX docs):
- A and B each carry a per-32-column **E8M0 scale** (`A^SF` is M × K/32,
  `B^SF` is K/32 × N; K=32 → 1 column).  Every product scales by it:
  `d = Σ_k (a·2^(eA−127))·(b·2^(eB−127)) + c`.
- **Re / Rh** are the 32-bit scale-A / scale-B data: 4 candidate E8M0 bytes.
- **URi** is a uniform selector register; its **low 2 bits = byte-id** (which
  of the 4 E8M0 bytes of Re/Rh feeds the block), higher bits = thread-id
  (which lane's scale data).  `URZ` (255) selects byte 0 of the local Re/Rh.

Verified on SM120 (`test_qmma_sf.py`):
- scale 1×/2×/0.5× (E8M0 0x7F/0x80/0x7E) scale A·B exactly; Re×Rh composes
  (2×2→4×, 2×0.5→1×).
- URi byte selector: sel%4 picks Re byte 0..3 (2/1/1/~0× with Re=0x017F7F80).
- SASS encoding matches nvcc's block_scale lowering (data bits, modulo
  operand choices).  Fragment layout is identical to plain QMMA (each 16-bit
  slot = 2 fp8); the scale operands ride in Re/Rh/URi.

Note the QMMA srcFmt enum (probed): **E4M3=0, E3M4=1, E2M3=2, E5M2=4,
E3M2=5, E2M1=6** — grouped by mantissa width, not the SRCFMTA_qmma 0..5 order.

## OMMA.SF — MXFP4 block scaling, m16n8k64 e2m1 (sm_120)

`OMMA.SF.16864.F32.E2M1.E2M1.E8 Rd, Ra, Rb, Rc, Re, Rh, URi` (opcode 0x47f)
is the MXFP4 block-scaled MMA; SASS for PTX
`mma.sync.aligned.m16n8k64.row.col.kind::mxf4.block_scale.f32.e2m1.e2m1
.f32.ue8m0` (sm_120a).  Per the MMA-Sim appendix this is the GDFS path
(group of 16, F=35) — not modeled here, only the observable arithmetic.

Verified SM120 (`test_omma.py`):
- **e2m1 packing** is 4 bits/element (no padding for `kind::mxf4`):
  sign bit 3, exp bits 2-1 (bias 1), mantissa bit 0.  Probed values:
  `0x1 = 0.5` (subnormal), `0x2 = 1.0`, `0x6 = 4.0`.
- **A·B = 64 k** (m16n8k64) at all-1.0: 16 / 64 / 1024 for e2m1 0x1/0x2/0x6.
- **scale 2X** (scale_A is M × K/32 = M × 2): **byte 0 of Re scales k 0..31,
  byte 1 scales k 32..63**.  Re = 0x017F7F80 gives 32·2 + 32·1 = 96; scale
  2x → 128, scale 0 → 0.  (Rh likewise for B's two 32-row groups.)
- **URi**: only sel=0 (byte-id 0) is legal here — other values fault 0x715.
  QMMA.SF's URi accepts sel 0..3; OMMA's appears more restricted.
- Encoding data bits match nvcc's lowering.

`decode_qmma.py` covers the 0x47f encoding (srcFmt mode/op bits 78/79,
scalefmt memdesc bit 82, scaleVectorSz nottid0 bit 83).
