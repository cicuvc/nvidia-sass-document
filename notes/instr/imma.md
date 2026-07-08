# IMMA — Integer Matrix Multiply-Accumulate

**Opcode mnemonic:** `IMMA`
**Pipe:** `int_pipe` (IMMA_OP subset, `$VQ_IMMA`)
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_EMULATABLE`

## Semantics

Warp-collective integer tensor core matrix multiply-accumulate:

```
D = A × B + C
```

where A (M×K), B (K×N), C/D (M×N), with M=8 (dense) or M=16 (sparse),
N=8, K∈{16,32,64} (varies by variant and data type). All 32 threads
cooperatively compute; each holds a register fragment of the matrices.

All operands are integer: A/B in u8/s8/u4/s4, accumulator C/D in s32.

## Variant overview

IMMA has **2 encoding variants**, single opcode `0x237`:

| Class | Dense/Sparse | Extra operands |
|-------|:---:|---|
| `imma_` | Dense | — |
| `imma_sp_` | Sparse (2:4) | +Re (metadata) + id |

Both share opcode `0b1000110111` (0x237). Sparse is distinguished by the
`sp` slot (SPONLY=1) wired to bit [72] — no separate opcode like HMMA.

No indexedRF variants exist for IMMA (unlike HMMA).

### Syntax

```
// Dense
@P0 IMMA.8816.U8.U8 R2, R4.reuse.ROW, R6.reuse.COL, R8, !UPT

// Sparse
@P0 IMMA.16832.U8.S8.SP.TID R2, R4.reuse.ROW, R6.reuse.COL, R8, !UPT, R10.reuse, 0x1

// With saturation
@P0 IMMA.16816.U8.U8.SAT R2, R4.reuse.ROW, R6.COL, R8, !UPT
```

### Dense vs Sparse differences

| Feature | Dense (`imma_`) | Sparse (`imma_sp_`) |
|---|---|---|
| Size enum | `SIZE_8816_16816_16832` | `SIZE_8832_16832_16864` |
| M×N shapes | 8×8 (default), 16×8 (K≥16) | 8×8, 16×8 (K≥32) |
| K values | 16, 16, 32 | 32, 32, 64 |
| Re operand | none | Re (metadata reg) |
| id operand | none | 2-bit immediate |
| ISRC_E_SIZE | 0 | 32 |
| spformat field | *0 | SPFORMAT (TID=0, REGOFFSET=1) |
| Rb reuse restriction | none | No reuse with .16864 + 8-bit data |

## Modifiers

### Matrix size (`size`) — 3-bit at [86:85,75]

Dense `SIZE_8816_16816_16832`:

| Value | Mnemonic | M×N×K | Notes |
|:---:|---|---|---|
| 0 | `8816` | 8×8×16 | Default, smallest tile |
| 4 | `16816` | 16×8×16 | 2× dense K (16×8 tile) |
| 5 | `16832` | 16×8×32 | 4× dense K |
| 1,2,3,6,7 | INVALID | — | Illegal encoding |

Sparse `SIZE_8832_16832_16864`:

| Value | Mnemonic | M×N×K | Notes |
|:---:|---|---|---|
| 2 | `8832` | 8×8×32 | Smallest sparse tile |
| 5 | `16832` | 16×8×32 | 2× dense K |
| 6 | `16864` | 16×8×64 | 4× dense K |
| 0,1,3,4,7 | INVALID | — | Illegal encoding |

**Key difference vs HMMA:** IMMA size encoding is non-contiguous (0→4→5
for dense, 2→5→6 for sparse) using 3 bits vs HMMA's 2-bit contiguous
encoding. This branches the decode into distinct M×N tile dimensions
(8×8 vs 16×8) at different K values.

### Source formats (`srcFmtA` / `srcFmtB`) — 3-bit each

`srcFmtA` at [83,77:76], `srcFmtB` at [84,79:78]. Same enum for both:

| Value | Mnemonic | Description |
|:---:|---|---|
| 0 | `U8` | Unsigned 8-bit |
| 1 | `S8` | Signed 8-bit |
| 2–7 | INVALID | Illegal encoding |

A and B formats are independent — e.g. `U8`/`S8` mixed signedness is valid.

### Saturation (`SAT`) — bit [82]

| Value | Mnemonic | Description |
|:---:|---|---|
| 0 | (default, omitted) | No saturation — result wraps on overflow |
| 1 | `SAT` | Saturate result to s32 range |

### Row/Column qualifiers (`row_A` / `col_B`) — bits [73,74]

| Qualifier | Bit | Description |
|---|---|---|
| `ROW` (row_A) | [73]=0 | Row-only access pattern for A operand |
| `COL` (col_B) | [74]=1 | Column-only access pattern for B operand |

These are type-pun enums with single valid values — the bits always have
these values (ROW=0, COL=1) in valid encodings. Their presence reflects
the warp-level matrix data distribution pattern.

### Reuse — encoded in opex table

Same mechanism as HMMA: `/REUSE` on Ra, Rb (and Re for sparse). Reuse
cannot be combined with DRAIN/WAITn_END_GROUP usched tokens.

Sparse-specific: `.16864` with 8-bit data **disallows** Rb reuse
(`(srcFmtB==U8\|S8) && size==16864 → reuse_src_b must be noreuse`).

### Sparse format (`spformat`) — bit [81] (sparse only)

Same as HMMA: TID=0, REGOFFSET=1.

### Uniform predicate (`UPp`) — bits [90:87], via TABLES_Pnz_0

Same mechanism as HMMA.

### Sparse ID constraint

| Size | Data type | id constraint |
|---|---|---|
| `.16832` | 8-bit (U8/S8) | id ∈ {0,1} |
| `.16864` | 8-bit (U8/S8) | id = 0 |

## Operand register sizes

| Condition | ISRC_A_SIZE | ISRC_B_SIZE | IDEST/ISRC_C |
|---|---|---|---|
| size=8816 (dense) or 8832 (sparse) | 64 (2 regs) | 64 (2 regs) | 128 (4 regs)* |
| size=16816 (dense), 8-bit | 128 (4 regs) | 64 (2 regs) | 256 (8 regs) |
| size=16832 (dense/sparse), 8-bit | 256 (8 regs) | 64/128 | 256 (8 regs) |
| size=16864 (sparse), 8-bit | 256 (8 regs) | 256 (8 regs) | 256 (8 regs) |

*For 8816/8832 sizes, Rd/Rc alignment is 2 (IDEST min 64). For 16816+,
alignment is 4 (IDEST = 128 or 256 depending on exact size).

## Bit layout (128-bit)

### imma_ (dense, 0x237)

```
[124:122],[109:105] w8  opex (includes reuse)
[121:116]           w6  req_bit_set
[115:113]           w3  src_rel_sb
[112:110]           w3  dst_wr_sb
[103:102]           w2  pm_pred
[91][11:0]          w13 opcode      (=0x237)
[90:87]             w4  op (UPp table)
[86:85],[75]        w3  size
[84],[79:78]        w3  srcFmtB
[83],[77:76]        w3  srcFmtA
[82]                w1  SAT
[81]                w1  loc          (=*0 for dense)
[74]                w1  col_B        (=COL=1)
[73]                w1  row_A        (=ROW=0)
[72]                w1  e            (=0 for dense)
[71:64]             w8  Rc
[50]                w1  Re_reuse_e   (=*0 for dense)
[49:48]             w2  id           (sparse only)
[47:40]             w8  Re           (sparse only)
[39:32]             w8  Rb
[31:24]             w8  Ra
[23:16]             w8  Rd
[15]                w1  Pg_not
[14:12]             w3  Pg
```

### imma_sp_ (sparse)

Same layout with:
- `loc` [81] = spformat (TID=0, REGOFFSET=1)
- `e` [72] = *sp (wired to 1 for sparse)
- Re at [47:40], id at [49:48], reuse_src_e at [50]

## IMMA vs HMMA comparison

| Property | IMMA | HMMA |
|---|---|---|
| Pipe | `int_pipe` | `fp16_pipe` |
| VQ | `$VQ_IMMA` | `$VQ_HMMA` |
| Opcode | `0x237` (single) | `0x23c` / `0x1e79` |
| Variants | 2 (dense/sparse) | 4 (dense/sparse × RF/indexedRF) |
| Data type | u8/s8/u4/s4 | f16/bf16/tf32/e6m9 |
| Accumulator | s32 | f16/f32 |
| M dim (dense) | 8 or 16 | 16 |
| Size encoding | 3-bit non-contiguous | 2-bit contiguous |
| Src fmt fields | 2 independent (A,B) | 1 shared |
| Negate | No | Yes (Ra, Rb) |
| Saturation | Yes (SAT) | No |
| Row/Col attributes | Yes (ROW, COL) | No |
| Sparse Re reuse | Has restriction on .16864 | No equivalent restriction |
| TABLE_TRUE latency | 28 cyc | 28 cyc |

## Latency

Same latency model as HMMA: fixed-latency (`dst_wr_sb` variable but
scoreboard model is coupled), `int_pipe` with IMMA_OP singleton.

From `sm_90_latencies.txt`:
- TABLE_TRUE: IMMA_OP→consumer = 28 cycles (same as HMMA)
- TABLE_OUTPUT: IMMA_OP→IMMA_OP WAW = 1 cycle
- IMMA_OP mapped to same latency tier as HMMA_OP

## PTX→SASS mapping

IMMA implements PTX `mma.sync.aligned` for integer types.

| PTX | SASS |
|-----|------|
| `mma.sync.aligned.m8n8k16.u8.u8.s32` | `IMMA.8816.U8.U8` |
| `mma.sync.aligned.m16n8k16.u8.u8.s32` | `IMMA.16816.U8.U8` |
| `mma.sync.aligned.m16n8k32.u8.u8.s32` | `IMMA.16832.U8.U8` |
| `mma.sync.aligned.m16n8k32.s8.s8.s32` | `IMMA.16832.S8.S8` |
| Sparse `mma.sync.aligned.m16n8k32.u8.u8.s32` | `IMMA.16832.U8.U8.SP.TID` |
| Sparse `mma.sync.aligned.m16n8k64.u8.u8.s32` | `IMMA.16864.U8.U8.SP.TID` |

SAT maps to PTX's `.sat` qualifier on `mma.sync`.

## Open questions

- **u4/s4 sub-byte formats**: The SASS encoding only shows U8/S8 in
  `SRCFMTA_U8_S8`. How are u4/s4 PTX types (e.g. `mma.sync.aligned.m8n8k32.u4.u4.s32`)
  lowered? Possibly through LDSM element conversion or a different SASS
  mnemonic.
- **SRCFMTA_U8_S8 enum**: The enum name suggests A-side only (SRCFMTA),
  but srcFmtB uses the same type. Is srcFmtB always identical to srcFmtA
  in practice, or are mixed-precision (U8×S8) MMAs actually emitted?
- **ROW/COL semantics**: These are single-value enums — what happens if
  they're set to the "wrong" value? Undefined behavior or explicit error?
- **No indexedRF**: Why does IMMA lack indexed register file variants
  while HMMA has them? Possibly because integer accumulator chains are
  shorter or uniform register file not used for integer MMA.
