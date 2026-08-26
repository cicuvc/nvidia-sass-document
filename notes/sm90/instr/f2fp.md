# F2FP — Float to Float, Packed (int_pipe converter)

**Opcode mnemonic:** F2FP  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Hopper-era packed float-to-float converter dispatched on the **integer pipeline**
(FP8/FP16/TF32 datapath family).  Unlike the legacy mio_pipe `F2F`, F2FP converts
*packed element pairs* in a single 32-bit register operation and is scoreboarded
as a coupled int-pipe math op (no MUFU dispatch).

Six **merge/family modes** (3-bit `merge` field `[90:89],[78:78]`) define what
the operation does with the 32-bit register lanes:

| merge | Family | Operation |
|-------|--------|-----------|
| `0` PACK_AB | base f2fp | two f32 (Ra, Rb) → packed f16x2/bf16x2/E6M9x2 in Rd |
| `1` MERGE_C | merge_c | one f32 (Rb) → f16/bf16/E6M9 in Rd, merge with Rc |
| `2` UNPACK_B | 8b upconvert | packed 8-bit E5M2/E4M3 src → f16x2/bf16x2 in Rd |
| `3` PACK_B | tf32 | one f32 → TF32 in Rd |
| `4` UNPACK_B_MERGE_C | f16→8b | f16x2 src → E4M3/E5M2 pair in Rd, merge with Rc |
| `5` PACK_AB_MERGE_C | f32→8b | two f32 (Ra, Rb) → E4M3/E5M2 pair in Rd, merge with Rc |

All conversions round RN (the only legal rndMode), with optional `.SATFINITE`
(narrowing only, formats E4M3/E5M2 require it), `.RELU` (clamp negatives to 0)
and half-select `.H0`/`.H1` extract (merge modes).

## Variant overview (61 total)

The 13-bit opcode only selects the **operand-position pattern** (9 patterns);
family + formats come from the `merge`, `dstfmt` and `space` fields.

| opcode (13-bit) | pattern | operand positions (per family) |
|-----------------|---------|--------------------------------|
| `0x23e` | RRR | Rd, [Ra,] Rb@[39:32] [, Rc@[71:64]] |
| `0x43e` | RRI | Rd, [Ra,] Rb@[71:64], imm@[63:32] |
| `0x63e` | RRC | Rd, [Ra,] Rb@[71:64], c[bank]@[58:54],[off]@[53:40] |
| `0x83e` | RIR | Rd, [Ra,] imm@[63:32] [, Rc@[71:64]] |
| `0xa3e` | RCR | Rd, [Ra,] c[bank]@[58:54],[off]@[53:40] [, Rc@[71:64]] |
| `0x1a3e` | RCxR | Rd, [Ra,] cx[UR@[37:32] +off]@[53:40] [, Rc@[71:64]] |
| `0x1c3e` | RUR | Rd, [Ra,] UR@[37:32] [, Rc@[71:64]] |
| `0x163e` | RRCx | Rd, [Ra,] Rb@[71:64], cx[UR@[37:32]+off] |
| `0x1e3e` | RRU | Rd, [Ra,] Rb@[71:64], UR@[37:32] |

`Ra` is a real operand only for the base (`PACK_AB`, `Rd,Ra,Rb`) and f32→8b
(`Rd,Ra,Rb,Rc`) families; all other families encode `*255` (RZ-equivalent) there.
Base / 8b-upconvert / tf32 families exist only in the 5 XRR shapes (patterns
with the A-position slot); merge_c / f16→8b / f32→8b exist in all 9.

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| satfinite | ntz | [77] | 0=nosatfinite, 1=SATFINITE (base, merge_c, f16→8b, f32→8b; `*0` on up8/tf32) |
| relu | sz | [75] | 0=norelu, 1=RELU |
| dstfmt | dstfmt | [87:86],[76:76] | 0=F16, 1=BF16 (E8M7), 2=E6M9, 3=TF32, 4=E5M2, 5=E4M3 |
| srcfmt | space | [74:73] | 0=F32 (base/merge_c/tf32/f32→8b), 1=F16 (f16→8b), 2=E5M2, 3=E4M3 (up8) |
| merge | merge | [90:89],[78:78] | family selector (see table above) |
| rnd | rndMode | [81:79] | RN=0 (default), RZ=3 (only legal values) — RNONLY on the 8b families |
| extract | e / spin | [72] (f16→8b, f32→8b, merge_c), [88] (up8) | H0=0, H1=1 |

Legality (from class CONDITIONS): with srcfmt F32, dstfmt ∈ {F16, E6M9, BF16};
the E4M3/E5M2 destinations only pair with the 8b source families; tf32 family
pins dstfmt=TF32(3), merge=PACK_B(3).  `MASK_INSTR_PREDICATE = (dstfmt==E6M9)`
— E6M9 has a predicated path and is spec-only for now (no PTX type exposes it).

## Bit layout (base RRR — opcode 0x23e, `F2FP.F16.F32.PACK_AB Rd, Ra, Rb`)

```
[124:122],[109:105]     opex      <= TABLES_opex_5(batch_t,usched_info,reuse_src_a,reuse_src_b)
[121:116]                req_bit_set
[115:113],[112:110]      src_rel_sb, dst_wr_sb    <= *7 (no var-lat scoreboard)
[103:102]                pm_pred
[91:91],[11:0]           opcode   <= 0b1000111110   (13-bit)
[90:89],[78:78]          merge    <= *PACK_ABONLY   (000)
[87:86],[76:76]          dstfmt   <= dstfmt         (0=F16)
[81:79]                  rndMode  <= rndMode        (RN=0)
[77:77]                  ntz      <= satfinite
[75:75]                  sz       <= relu
[74:73]                  space    <= *srcfmt        (0=F32)
[71:64]                  Rc       <= *255
[39:32]                  Rb       <= Rb
[31:24]                  Ra       <= Ra
[23:16]                  Rd       <= Rd
[15:15],[14:12]          Pg_not, Pg
```

The 9 patterns share this skeleton; family differences are (i) which of
Ra/Rb/Rc are real vs `*255`, (ii) the immediate replaces an operand (`RRI`/`RIR`),
(iii) extra `.H1` extract bit.

## Cross-comparison

| Property | F2F | F2FP | UF2FP | I2FP |
|----------|-----|------|-------|------|
| Pipe | `mio_pipe` | `int_pipe` | `udp_pipe` | `int_pipe` |
| Scoreboard | Decoupled (VarLat) | Coupled | Coupled | Coupled |
| Packed ops | No | **Yes** | Yes | No |
| FP8 (E4M3/E5M2) | No | **Yes** | No | No |
| pTxas emits? | No (legacy) | **Yes (sm_90+)** | Not observed | Yes |

## Latency

`int_pipe` (member of `FXU_OPS = int_pipe + fe_pipe - IMMA_OP - MOVM_OP`).
- `TABLE_TRUE(GPR)` row `FXU_OPS{Rd,Rd2}`: **6** cyc to FXU/FMAI/IMAD/FP16
  consumers, 7 to tensor-core consumers, 8 to MIO_SLOW / GMMA.
- `TABLE_OUTPUT` / `TABLE_ANTI(GPR)` rows `FXU_OPS{Rd,Rd2}`: 1–2 cycles.
- Coupled scoreboard: `Rd` is written to the normal scoreboard (unlike
  HMMA/QMMA); `?`-tokens only affect the fixed `*7` SB fields.

## Verified encodings

All from raw cubin words (ptxas CUDA 13.1; `.reuse` stripped from the SASS text):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x000000090007723e` | `0x0c0fe200000000ff` | `F2FP.F16.F32.PACK_AB R7, R0, R9` (sm_120) |
| `0x00000009000b723e` | `0x010fc400000010ff` | `F2FP.BF16.F32.PACK_AB R11, R0, R9` (sm_120) |
| `0x000000090011723e` | `0x0c0fe400000008ff` | `F2FP.RELU.F16.F32.PACK_AB R17, R0, R9` (sm_120) |
| `0x000000090004723e` | `0x0c0fe200048070ff` | `F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C R4, R0, R9, RZ` |
| `0x000000090005723e` | `0x0c0fe400048060ff` | `F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C R5, R0, R9, RZ` |
| `0x000000090009723e` | `0x000fe200048078ff` | `F2FP.SATFINITE.RELU.E4M3.F32.PACK_AB_MERGE_C R9, R0, R9, RZ` |
| `0x00000004ff09723e` | `0x000fc400020006ff` | `F2FP.F16.E4M3.UNPACK_B R9, R4` |
| `0x00000007ff00723e` | `0x080fe400048032ff` | `F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C R0, R7, RZ` |
| `0x00000007ff04723e` | `0x000fe200048022ff` | `F2FP.SATFINITE.E5M2.F16.UNPACK_B_MERGE_C R4, R7, RZ` |
| `0x00000005ff05723e` | `0x000fe200020004ff` | `F2FP.F16.E5M2.UNPACK_B R5, R5` |
| `0x00000013ff00723e` | `0x000fe200000000ff` | `F2FP.F16.F32.PACK_AB R0, RZ, R19` (cublas) |
| `0x00000013ff00723e` | `0x000fe200000010ff` | `F2FP.BF16.F32.PACK_AB R0, RZ, R19` (cublas) |

sm_90 and sm_120 encodings are bit-identical except scheduling (`opex`) bits.
The `452/452` cublas sm_90 F2FP instances all decode as `F2FP.(F16|BF16).F32.
PACK_AB Rd, RZ, Rb` — cublas converts single halves against RZ.

Decoder: `tools/decode_f2fp.py` — 37/37 unit vectors + 452/452 cublas sweep.

## sm90 vs sm120 (and sm100) differences

Verified against the repo's per-arch dumps (`sm100_instructions.txt`, `sm120_instructions.txt`)
and CUDA 13.1 ptxas (sm_90/sm_120/sm_100/sm_103 cubins).

### Spec-level (sm120 adds 26 new class families, drops 26)

| Aspect | sm90 (61 f2fp + 5 uf2fp classes) | sm120 (71 + 22) | sm100 (81 + 22) |
|--------|----------------------------------|-----------------|-----------------|
| dstfmt field | 3-bit `[87:86],[76:76]` | **4-bit `[87:85],[76:76]`** (superset) | same as sm120 |
| srcfmt field | 2-bit `[74:73]` | **4-bit `[83:82],[74:73]`** | same |
| DSTFMT values | F16=0, BF16=1, E6M9=2, TF32=3, E5M2=4, E4M3=5 | E6M9 gone; 4-bit codes: F16=0, BF16=1, **E0M3=2, E2M1=3**, TF32=5, **E2M3=6, E3M2=7**, E5M2=8, E4M3=9, **E3M4=10, S2_6=11, E8=12** | same |
| new families | — | 4b up/downconvert (E0M3/E2M1), `_scale` families (ue8m0 scale factor), E8 upconvert, MX8 (S2_6) downconvert | same + `f2fp_rs_16b__`/`f2fp_rs_8b4b__` (stochastic rounding, RSONLY) |
| const/cx forms | RCR, RCxR, RRC, RRCx (present) | **removed** (base/tf32/up8 shrink 5→3; f16/f32→8b and merge_c shrink 9→5) | same |
| new fields | — | `selB` (B3B0, 2-bit `[88],[72]`), `iswzC`/UPq (3-bit `[26:24]`), scale operands (Sc imm / UR / Rc reg) | same |
| narrowing modifier | SATFINITE | + `SATNARROW` (mx8) | same |

Shared formats stay *physically compatible*: sm120's 4-bit fields only
extended the code space (new bit 85 / bits 83:82 were don't-cares on sm90), so
`F16.BF16.TF32.E5M2.E4M3` down/upconvert words bit-decode identically on both
archs (verified: identical hi64 modulo opex for the E4M3/E5M2 words).  The
enum *numbers* differ (sm90 E4M3=5 vs sm120 E4M3=9) but land on the same bits.
E6M9 (sm90 value 2) is a Hopper-only format — superseded by the MXFP formats.

### Toolchain-level (CUDA 13.1)

- Identical SASS emission for the fp8/f16 paths on sm_90 and sm_120 — the same
  10 forms in the verified-encodings table, differing only in register
  allocation and scheduling order.
- The **new sm120 families are unreachable from PTX**: `cvt` with `e2m1x2`,
  `e2m3x2`, `s2f6x2`, `ue8m0x2`, `scaled::n2::ue8m0` are rejected by ptxas on
  sm_120 (and sm_90, sm_100, sm_103) in CUDA 13.1; MXFP4 via `cuda_fp4.h`
  intrinsics is **software-emulated** (LOP3/PRMT/FSET sequences, no F2FP) on
  both sm90 and sm120.  The F2FP.E0M3/E2M1/MX8/scale encodings are thus
  exercised by NVIDIA-internal SASS paths only.
- `f2fp_rs_*` (stochastic) exists only in sm100_instructions.txt — absent from
  both sm90 and sm120.

### PTX→SASS mapping

| PTX (inline-asm form) | SASS |
|----------------------|------|
| `cvt.rn.f16x2.f32 d,a,b` | `F2FP.F16.F32.PACK_AB Rd, Ra, Rb` |
| `cvt.rn.bf16x2.f32 d,a,b` | `F2FP.BF16.F32.PACK_AB Rd, Ra, Rb` |
| `cvt.rn.relu.f16x2.f32 d,a,b` | `F2FP.RELU.F16.F32.PACK_AB Rd, Ra, Rb` |
| `cvt.rn.satfinite.e4m3x2.f32 d,a,b` | `F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C Rd, Ra, Rb, RZ` |
| `cvt.rn.satfinite.e5m2x2.f32 d,a,b` | `F2FP.SATFINITE.E5M2.F32.PACK_AB_MERGE_C Rd, Ra, Rb, RZ` |
| `cvt.rn.satfinite.relu.e4m3x2.f32 d,a,b` | `F2FP.SATFINITE.RELU.E4M3.F32.PACK_AB_MERGE_C Rd, Ra, Rb, RZ` |
| `cvt.rn.satfinite.e4m3x2.f16x2 d,a` | `F2FP.SATFINITE.E4M3.F16.UNPACK_B_MERGE_C Rd, Rb, RZ` |
| `cvt.rn.satfinite.e5m2x2.f16x2 d,a` | `F2FP.SATFINITE.E5M2.F16.UNPACK_B_MERGE_C Rd, Rb, RZ` |
| `cvt.rn.f16x2.e4m3x2 d,a` | `F2FP.F16.E4M3.UNPACK_B Rd, Rb` |
| `cvt.rn.f16x2.e5m2x2 d,a` | `F2FP.F16.E5M2.UNPACK_B Rd, Rb` |
| `cvt.rn.f16.f32 d,a` (single) | **F2F.F16.F32** Rd, Rb (mio_pipe!) — ptxas still emits the legacy F2F |
| `cvt.rn.bf16.f32 d,a` (single) | **F2F.BF16.F32** Rd, Rb |
| `cvt.rna.satfinite.tf32.f32 d,a` | folded by ptxas into `LOP3` mask (`& 0xffffe000`); the F2FP.TF32.F32.PACK_B encoding exists in the spec (opcode 0x23e, dstfmt=3, merge=3) |

## Silicon-verified semantics (sm120 / RTX 5090)

`tests/asm_construct/test_f2fp.py` — 41 cases, hand-assembled SASS run on an
RTX 5090, all bit-exact against the reference model.  **42/42 incl. probes.**

| Form | Verified behavior |
|------|-------------------|
| `F2FP.F16.F32.PACK_AB Rd, Ra, Rb` | `Rd = (f16(Ra)<<16) \| f16(Rb)` — **Ra→upper, Rb→lower**; RNE ties-to-even; subnormal f32 input flushed to ±0; overflow → ±inf; NaN → qNaN with all-ones payload (`0x7FFF`) |
| `F2FP.BF16.F32.PACK_AB` | same orientation; RNE at mantissa bit 16; NaN → `0x7FC0` pattern |
| `F2FP.SATFINITE.E4M3/E5M2.F32.PACK_AB_MERGE_C` | RNE ties-to-even; NaN → **`0x7F`** (NaN code, sign ignored); ±inf & overflow → **±maxnorm** (`0x7E/0xFE`, `0x7B/0xFB`); ±0.0 and -0.0 (`0x80`) preserved; subnormal f32 input → ±0; below ½·2^-min → 0, else rounds to 2^-min |
| `.RELU` | negative inputs → **+0.0** (before rounding/packing) |
| `F2FP.SATFINITE.E4M3/E5M2.F16.UNPACK_B_MERGE_C` | high f16 → **high byte**; f16 inf → maxnorm; merge as below |
| `F2FP.F16.E4M3/E5M2.UNPACK_B` | low fp8 byte → **low f16 half**; e5m2 inf code → f16 ±inf; e4m3 `0x7F`/e5m2 `0x7D–0x7F` NaN → f16 qNaN (`0x7FFF`) |
| **merge semantics** (all merge families) | conversion result always lands in `Rd[15:0]`; **`Rd[31:16] = extract==H1 ? Rc[31:16] : Rc[15:0]`** (Rc's selected half becomes the upper partner).  i.e. `.H1` selects which Rc half feeds the upper 16 — verified across MERGE_C, UNPACK_B_MERGE_C, PACK_AB_MERGE_C |
| `F2FP.TF32.F32.PACK_B` | **round-to-nearest** (RNE keeps 10 mantissa bits: `1.0+3·2^-12 → 1.0+2^-10`); NOT truncation (contrast: ptxas folds `cvt.rna.tf32` to a `LOP3 &0xffffe000` truncation) |
| `F2FP.SATFINITE.E2M1.F32.PACK_AB_MERGE_C` (4-bit) | **runs on sm120 hardware**: two f32 → 4-bit nibble pair in `Rd[7:0]` (Ra→high nibble) — MXFP4 not just a paper encoding |
| `F2FP.F16.E2M1.UNPACK_B[.B0..B3]` (4-bit) | `selB` B0–B3 select the **byte**; low nibble of that byte → f16 **low half** (order preserved); code 8–15 decode as negative e2m1 (sign bit = nibble bit3) |

## Hopper-only: E6M9 — silicon-verified on H20

`tests/asm_construct/test_f2fp_hopper.py` — 34/34 pass on an NVIDIA H20
(sm_90, Hopper).  E6M9 (`dstfmt=2`) executes on real Hopper silicon:

| Probe | Result (H20) | Meaning |
|-------|--------------|---------|
| `E6M9.F32.PACK_AB Rd, Ra, Rb` | `Ra→high E6M9, Rb→low` | same lane order as f16x2 |
| 1.0 → `0x3E00`, 0.5 → `0x3C00`, 2.0 → `0x4000` | — | **bias 31** (6-bit exponent), 9-bit mantissa |
| 1.0+2^-10 (half-ulp) → 1.0 | tie → even | **RNE ties-to-even** |
| 1.0+3·2^-11 → 1.0+2^-9 (`0x3E01`) | — | RNE rounds up |
| 65504 → `0x5E00` (2^16), 2^31 → `0x7C00` | carry works | mantissa 9 bits |
| 2^32 → `0x7E00`; ±inf → `0x7E00/0xFE00` | e=63,m=0 | overflow/±inf → **inf pattern** |
| NaN → `0x7FFF` | e=63,m=all-ones | NaN → all-ones payload (like f16) |
| `-0.0` → `0x8000`; subnormal f32 in → ±0 | — | input FTZ; ±0 kept |
| `.SATFINITE` 1e10 → `0x7DFF` (−→ `0xFDFF`) | e=62,m=511 | saturates to (2−2^-9)·2^31 |
| `.RELU` negative → +0 | — | same as other families |
| 2^-25 → `0x0C00` (e=6) | — | sub-2^-24 E6M9 normals fine |

So E6M9 = sign(1)+exp(6,bias31)+mant(9), 16-bit, legacy Hopper-wide f16
replacement; removed on sm120 (value 2 repurposed to MXFP4 E0M3).

## Arch-diff findings (Hopper vs Blackwell)

Every shared behavior tested on both H20 (sm90) and RTX 5090 (sm120) is
**bit-identical**: f32→f16 NaN → `0x7FFF`; fp8 NaN → `0x7F` (NaN code, NOT the
spec-text "maxnorm"); fp8 ±inf/overflow → ±maxnorm under satfinite; TF32 RNE;
merge-family H0/H1 (Rc half-select) mapping; fp8-upconvert NaN → `0x7FFF`;
subnormal-input FTZ; lane orientations; .RELU.  No behavioral divergence
was found in the shared opcode space.

## Open questions

- **E6M9 destination** (`dstfmt=2`): *resolved* — silicon-verified on H20 (see
  the Hopper-only section): bias-31 6-bit-exponent / 9-bit-mantissa 16-bit
  format, RNE, FTZ input, inf/NaN/±0 conventions, `.SATFINITE` → `0x7DFF`
  max.  Hopper-only: sm120's DSTFMT renames value 2 to MXFP4 **E0M3**.
- **TF32 rounding**: *resolved on silicon* — `F2FP.TF32.F32` rounds RN
  (RNE at 10-bit mantissa), not truncation; ptxas's `cvt.rna.tf32` → LOP3 fold is
a different (software) behavior.
- **`.H1` extract printing**: extract placement/merge semantics *resolved on
  silicon* (see silicon-verified table); cuobjdump token is `.H1` after the
  merge suffix (matches the FORMAT).
- **BF16 src** upconvert/downconvert (`SRCFMT_E5M2_E4M3` only covers E5M2/E4M3):
  FP8 pipeline formats are E4M3/E5M2 only, so `F2FP.*.BF16` src forms are just
  the shared dstfmt=BF16(1) alias — consistent with the E8M7/BF16 enum aliasing.