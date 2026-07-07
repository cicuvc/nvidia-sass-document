# BMMA — Binary Matrix Multiply-Accumulate (warp-level)

**Opcode mnemonic:** `BMMA`
**Pipe:** `int_pipe`
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_EMULATABLE`
**VIRTUAL_QUEUE:** `$VQ_IMMA`

## Semantics

Warp-level binary (b1) tensor core matrix multiply-accumulate — the single-bit
counterpart of IMMA. Implements PTX `mma.sync.aligned` for `.b1` type with
`.and` operation and `.popc` accumulation.

```
D = POPC(A AND B) + D
```

For binary data, multiplication is logical AND (1×1=1, 0×anything=0), and
accumulation counts the number of set bits (POPC = population count) instead
of arithmetic sum.

All 32 threads participate; each thread holds register fragments of the
matrices. The warpgroup-level counterpart is BGMMA (`notes/bgmma_qgmma.md`).

## Variants

Single encoding variant, opcode `0b1000111101` (0x23d).

### Syntax

```
@P0 BMMA.88128.AND.POPC R2, R4.reuse.ROW, R6.reuse.COL, R8, !UPT
@P0 BMMA.168128.AND.POPC R2, R4.reuse.ROW, R6.COL, R8, !UPT
@P0 BMMA.168256.AND.POPC R2, R4.ROW, R6.COL, R8, !UPT
```

## Modifiers

### Matrix size (`size`) — 2-bit at [76:75]

| Value | Mnemonic | M×N×K | Notes |
|:---:|---|---|---|
| 0 | `88128` | 8×8×128 | Smallest tile |
| 1 | `168128` | 16×8×128 | 2× M dimension |
| 2 | `168256` | 16×8×256 | 2× M, 2× K |
| 3 | INVALID | — | |

### Operation (`op`) — 2-bit at [78:77], enum ANDONLY

Always `AND` = 2. Binary matrix multiply uses logical AND.

### Accumulation (`accum`) — 1-bit at [80], enum POPCONLY

Always `POPC` = 1. Accumulation is population count of AND results.

### Row/Column (`row_A` / `col_B`) — bits [73], [74]

Same as IMMA: ROW=0, COL=1 for warp-level matrix data distribution.

### Reuse — encoded in opex table

`/REUSE` on Ra, Rb. Same constraints as HMMA/IMMA — cannot combine with
DRAIN/WAITn usched tokens.

### Uniform predicate (`UPp`) — bits [90:87], via TABLES_Pnz_0

Same mechanism as HMMA/IMMA.

## Operand register sizes

| Size | ISRC_A_SIZE | ISRC_B_SIZE | IDEST/ISRC_C | Ra regs | Rb regs | Rd/Rc regs |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 88128 | 64 (2) | 64 (2) | 64 (2) | 2 | 1 | 2 |
| 168128 | 128 (4) | 64 (2) | 128 (4) | 4 | 1 | 4 |
| 168256 | 256 (8) | 128 (4) | 128 (4) | 8 | 2 | 4 |

Rd/Rc alignment: 2 for 88128, 4 for 168128/168256.
Ra alignment: 1 for 88128, 2 for 168128, 4 for 168256.
Rb alignment: 1 for 88128/168128, 2 for 168256.

## Bit layout (128-bit)

```
[124:122],[109:105] w8  opex (includes reuse)
[121:116]           w6  req_bit_set
[115:113]           w3  src_rel_sb
[112:110]           w3  dst_wr_sb
[103:102]           w2  pm_pred
[91][11:0]          w13 opcode          (0x23d)
[90:87]             w4  op (UPp table)
[80]                w1  accum (POPC=1)
[78:77]             w2  op (AND=2)
[76:75]             w2  size
[74]                w1  col_B (COL=1)
[73]                w1  row_A (ROW=0)
[71:64]             w8  Rc
[39:32]             w8  Rb
[31:24]             w8  Ra
[23:16]             w8  Rd
[15]                w1  Pg_not
[14:12]             w3  Pg
```

## BMMA vs BGMMA comparison

| Property | BMMA (warp) | BGMMA (warpgroup) |
|---|---|---|
| Pipe | `int_pipe` | `mio_pipe` |
| VQ | `$VQ_IMMA` | `$VQ_UMMA` |
| Opcode | 0x23d | 0x1df2 / 0x15f2 / 0x19f2 |
| Variants | 1 | 3 |
| Matrix data | Registers (Rd, Ra, Rb, Rc) | SMEM via gdesc or regs |
| M dimension | 8 or 16 | 64 (fixed) |
| N dimension | 8 (fixed) | 8–256 |
| K dimension | 128 or 256 | 256 |
| Sync | Scoreboard (wr_sb) | GMMA scoreboard (gsb) |
| Data source | LDSM loads | TMA / LDSM + descriptors |
| INST_TYPE | COUPLED_EMULATABLE | DECOUPLED_BRU_DEPBAR_RD_SCBD |
| AND/POPC op | Yes | Yes |
| Reuse | Yes | No (in BGMMA) |
| ROW/COL | Yes | No (gdesc handles) |

## PTX→SASS mapping

BMMA implements PTX `mma.sync.aligned` for `.b1` type:

| PTX | SASS |
|-----|------|
| `mma.sync.aligned.m8n8k128.b1.b1.s32.and.popc` | `BMMA.88128.AND.POPC` |
| `mma.sync.aligned.m16n8k128.b1.b1.s32.and.popc` | `BMMA.168128.AND.POPC` |
| `mma.sync.aligned.m16n8k256.b1.b1.s32.and.popc` | `BMMA.168256.AND.POPC` |

## BMMA vs IMMA comparison

| Property | BMMA | IMMA |
|---|---|---|
| Data type | b1 (single-bit) | u8/s8 (8-bit integer) |
| Operation | AND | Multiply |
| Accumulation | POPC (population count) | Add |
| Sizes | 88128, 168128, 168256 | 8816, 16816, 16832 |
| K values | 128, 256 | 16, 32 |
| srcFmt fields | None (b1 only) | srcFmtA + srcFmtB (U8/S8) |
| SAT | No (POPC overflow?) | Yes |
| Sparse | No (in spec; may exist on later archs) | Yes (sp version) |
