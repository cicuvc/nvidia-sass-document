# `ISWZA` / `ISWZB` — packed-half (2×f16) source lane swizzles

**Question:** what do `H1_H0` / `H0_H0` / `H1_H1` mean on half-vector ops (HFMA2, …)?
**Status:** resolved (spec-grounded + empirically confirmed in cublas sm_90 SASS).

## Model
A 32-bit register holds a **packed pair of f16** (`.F16_V2`):
- **H0** = low half-word, bits **[15:0]**
- **H1** = high half-word, bits **[31:16]**

`ISWZ*` is a per-source-operand **lane select/swizzle**. Naming is
**`{high_out}_{low_out}`**: the token left of `_` feeds the result's high f16
lane, the token right feeds the low lane.

| ISWZA | val | high lane <- | low lane <- | effect |
|-------|----:|:--:|:--:|--------|
| H1_H0 | 0 | H1 | H0 | identity / pass-through (**default**, nvdisasm omits it) |
| H0_H0 | 2 | H0 | H0 | broadcast **low** half to both lanes |
| H1_H1 | 3 | H1 | H1 | broadcast **high** half to both lanes |
| (INVALID1 = 1 unused) |

## Where it lives in the spec
- Enums: `ISWZA "H1_H0"=0,"INVALID1"=1,"H0_H0"=2,"H1_H1"=3;`
  `ISWZB "H1_H0"=0,"F32"=1,"H0_H0"=2,"H1_H1"=3,"H0_NH1"=4,INVALID5..7;`
- Used by the FP16-pipe packed ops: **HADD2, HFMA2, HMUL2, HSET2, HSETP2,
  HMNMX2, VHMNMX** (and `*_32I` immediate forms). ISWZA is 2-bit; ISWZB 3-bit.
- Per-source attachment — e.g. `HFMA2 = Ra*Rb + Rc`:
  - `iswzA` on **Ra** — type `ISWZA`, encoded at bits **[75:74]** (field `bop`)
  - `iswzB` on **Rb/Sb** — type `ISWZB`, bits **[86],[61:60]** (field `iswzB`)
  - `iswzC` on **Rc** — type `ISWZA`, bits **[82:81]** (field `iswzC`)
  FORMAT: `... Register:Ra .../ISWZA("H1_H0"):iswzA , ... Register:Rb .../ISWZB("H1_H0"):iswzB , ...`
- Renders in SASS right after the register: `R15.H0_H0`.

## ISWZB extras (multiplier operand B only)
`ISWZB` adds two values beyond the ISWZA set:
- **F32** (=1): treat B as a single **f32**, broadcast to both f16 lanes
  (e.g. multiply a packed-half by an f32 scalar). *Not separately confirmed in
  SASS mining — the text token collides with the `OFMT`/`.F32` output-format
  suffix; taken from the enum.*
- **H0_NH1** (=4): high lane <- H0, low lane <- **negated H1** — a
  swizzle-with-per-lane-negate (useful for complex-style cross terms). Inferred
  ("NH1" = negated H1); not yet seen in mined SASS.

## Empirical confirmation (libcublas.so.13, `cuobjdump -arch sm_90 -sass`, 5.6M lines)
- Counts of rendered suffixes: `.H0_H0` ×3212, `.H1_H1` ×266, `.H1_H0` **×0**
  (default omitted). Suffix attaches per operand:
  `HFMA2 R16, R15.H0_H0, R16.H0_H0, R8.H0_H0`.
- **The clincher — fp16→fp32 widening idiom** (matches the external reference
  `cvt.f32.f16 -> HADD2.F32 Rd,-RZ,x.H0_H0`):
  - `HADD2.F32 R8,  -RZ, R14.H0_H0`  → widen the **low** f16 (H0) to f32
  - `HADD2.F32 R15, -RZ, R12.H1_H1`  → widen the **high** f16 (H1) to f32
  So `H0_H0` selects the low half, `H1_H1` the high half — consistent with the
  `{high}_{low}` broadcast reading. (`.F32` here is `HADD2`'s output format
  `OFMT`, i.e. write an f32 result, *not* the ISWZB `F32` lane mode.)

## Related lane enums (for cross-reference)
- `HSEL "H0"=0,"H1"=1` and `EXTRACT "H0"=0,"H1"=1` — single-lane pick (H0=low,
  H1=high), same H0/H1 convention, used by other half ops.
