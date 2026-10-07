# DMMA — Double-precision (FP64) Matrix Multiply-Accumulate

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** low  
**Last verified:** unknown  
**Probe:** not recorded in this note  
**Open items:** 2 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: lives under notes/sm90/; no part named, so the default measurement site sm120 is assumed

## Conclusion

**Opcode mnemonic:** `DMMA`
**Pipe:** `fma64lite_pipe` (FP64 hardware, not fp16 or int)
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_EMULATABLE`
**VIRTUAL_QUEUE:** `$VQ_DMMA`

## Semantics

Warp-level FP64 tensor core matrix multiply-accumulate. Implements PTX
`mma.sync.aligned` for `.f64` type.

```
D = A × B + C
```

where all operands are IEEE double-precision (64-bit). The only tensor core
instruction using the `fma64lite_pipe` — the FP64 tensor core datapath.

Because FP64 elements are 4× wider than FP16, tile sizes are proportionally
smaller and register usage per operand is much higher.

## Variants

Single encoding variant, opcode `0b1000111111` (0x23f).

### Syntax

```
@P0 DMMA.884.RN       R2, -|R4|, -|R6|, -|R8|, !UPT
@P0 DMMA.16x8x4.RN     R2, R4.reuse, R6.reuse, R8, !UPT
@P0 DMMA.16x8x8.RM     R2, R4, R6, R8, !UPT
@P0 DMMA.16x8x16.RP    R2, R4, R6, R8, !UPT
```

## Modifiers

### Matrix size (`size`) — 2-bit at [77:76], enum `SIZE_DMMA`

| Value | Mnemonic | Alias | M×N×K | Notes |
|:---:|---|---|---|---|
| 0 | `884` | `8x8x4` | 8×8×4 | Smallest tile |
| 1 | `16x8x4` | — | 16×8×4 | |
| 2 | `16x8x8` | — | 16×8×8 | |
| 3 | `16x8x16` | — | 16×8×16 | Largest tile |

`884` is an alias for `8x8x4` — both encode to 0.

### Rounding mode (`rnd`) — 2-bit at [79:78], enum `Round1`

Uses the standard `Round1` enum (shared with FP64 math instructions):

| Value | Mnemonic | Description |
|:---:|---|---|
| 0 | `RN` | Round to nearest even (default) |
| 1 | `RM` | Round toward minus infinity |
| 2 | `RP` | Round toward plus infinity |
| 3 | `RZ` | Round toward zero |

### Negate — 1-bit each

All three operands support negation, unlike HMMA (which only has Ra and Rb negate):

| Operand | Bit | Slot attribute |
|---|---|---|
| Ra | [72] | `Ra@negate` |
| Rb | [63] | `Rb@negate` |
| Rc | [75] | `Rc@negate` |

### Absolute value — 1-bit each

All three operands support `[||]` absolute value — unique among tensor core instructions:

| Operand | Bit | Slot attribute |
|---|---|---|
| Ra | [73] | `Ra@absolute` |
| Rb | [62] | `Rb@absolute` |
| Rc | [74] | `Rc@absolute` |

### Reuse — encoded in opex table

`/REUSE` on Ra, Rb. **Restricted for larger sizes:**

| Size | Ra reuse | Rb reuse |
|------|:---:|:---:|
| 8x8x4, 16x8x4 | Allowed | Allowed |
| 16x8x8 | **Disallowed** (256-bit Ra) | **Disallowed** (128-bit Rb) |
| 16x8x16 | **Disallowed** (512-bit Ra) | **Disallowed** (256-bit Rb) |

This is likely because the operand reuse cache is limited in size and
cannot hold the larger FP64 register fragments.

### Uniform predicate (`UPp`) — bits [90:87], via TABLES_Pnz_0

Same mechanism as HMMA/IMMA/BMMA.

## Operand register sizes

| Size | ISRC_A | ISRC_B | IDEST/ISRC_C | Ra regs | Rb regs | Rd/Rc regs |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 8x8x4 | 128 (4) | 128 (4) | 256 (8) | 4 (align 2) | 4 (align 2) | 8 (align 4) |
| 16x8x4 | 256 (8) | 128 (4) | 384 (12) | 8 (align 4) | 4 (align 2) | 12 (align 8) |
| 16x8x8 | 448 (14) | 256 (8) | 384 (12) | 14 (align 8) | 8 (align 4) | 12 (align 8) |
| 16x8x16 | 832 (26) | 448 (14) | 384 (12) | 26 (align 16) | 14 (align 8) | 12 (align 8) |

Note: ISRC_A grows dramatically for larger K values because each FP64
element is a full 64-bit register pair per fragment element.

## Bit layout (128-bit)

```
[124:122],[109:105] w8  opex (includes reuse)
[121:116]           w6  req_bit_set
[115:113]           w3  src_rel_sb
[112:110]           w3  dst_wr_sb
[103:102]           w2  pm_pred
[91][11:0]          w13 opcode          (0x23f)
[90:87]             w4  op (UPp table)
[79:78]             w2  rnd (rounding)
[77:76]             w2  size
[75]                w1  Rc@negate
[74]                w1  Rc@absolute
[73]                w1  Ra@absolute
[72]                w1  Ra@negate
[71:64]             w8  Rc
[63]                w1  Rb@negate
[62]                w1  Rb@absolute
[39:32]             w8  Rb
[31:24]             w8  Ra
[23:16]             w8  Rd
[15]                w1  Pg_not
[14:12]             w3  Pg
```

## Comparison with other warp-level MMAs

| Property | DMMA | HMMA | IMMA | BMMA |
|---|---|---|---|---|
| Pipe | `fma64lite_pipe` | `fp16_pipe` | `int_pipe` | `int_pipe` |
| VQ | `$VQ_DMMA` | `$VQ_HMMA` | `$VQ_IMMA` | `$VQ_IMMA` |
| Opcode | 0x23f | 0x23c | 0x237 | 0x23d |
| Data type | f64 | f16/bf16/tf32/e6m9 | u8/s8 | b1 |
| Accumulator | f64 | f16/f32 | s32 | s32 |
| Max K | 16 | 32 (sparse) | 32 (dense) | 256 |
| Negate | Ra, Rb, **Rc** | Ra, Rb | — | — |
| Abs value | Ra, Rb, **Rc** | — | — | — |
| Rounding mode | Yes (RN/RM/RP/RZ) | — | — | — |
| Reuse restrictions | For 16x8x8/16x8x16 | Only usched rules | Only usched rules | Only usched rules |
| Sparse | No | Yes | Yes | No |
| ROW/COL qualifiers | No | No | Yes | Yes |
| Variants | 1 | 4 | 2 | 1 |

## PTX→SASS mapping

DMMA implements PTX `mma.sync.aligned` for `.f64` type:

| PTX | SASS |
|-----|------|
| `mma.sync.aligned.m8n8k4.f64.f64.f64` | `DMMA.884.RN` |
| `mma.sync.aligned.m16n8k4.f64.f64.f64` | `DMMA.16x8x4.RN` |
| `mma.sync.aligned.m16n8k8.f64.f64.f64` | `DMMA.16x8x8.RN` |
| `mma.sync.aligned.m16n8k16.f64.f64.f64` | `DMMA.16x8x16.RN` |

With other rounding modes: `.RN` default, `.RM`, `.RP`, `.RZ`.

## Hopper vs Ampere DMMA

The sm_90 spec shows the Hopper DMMA encoding (opcode 0x23f). The TODO lists
two entries — Ampere (idx 180, category 434) and Hopper (idx 215, category
515). The Hopper DMMA uses the `fma64lite_pipe` and `$VQ_DMMA`, while the
Ampere version likely used a different pipe path. Both implement the same
PTX `mma.sync.f64` semantics.

## History / retracted hypotheses

> Claims below were **superseded, refuted, or never settled** by later work; they are kept
> for provenance. Do not cite them as current.

## Open questions

- **Ampere DMMA encoding**: The sm_90 spec only shows one CLASS block. Does  <!-- open-question: open blocked-by "blocker (inferred): needs a Hopper session (sm_90) -- no local part" -->
  the Ampere DMMA share the same encoding or use a different opcode?
- **Why no abs on C in HMMA?**: DMMA supports `[||]Rc` but HMMA does not.  <!-- open-question: open blocked-by "blocker (inferred): needs a Hopper session (sm_90) -- no local part" -->
  Is this a fundamental difference in the FP64 tensor core datapath, or
  missing from HMMA's encoding for another reason?

