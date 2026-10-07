# MOVM — Warp-level Matrix Transpose (movmatrix)

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** low  
**Last verified:** unknown  
**Probe:** not recorded in this note  
**Open items:** 2 open item(s)  
**Audit:** `tools/notes_audit.py` · basis: lives under notes/sm90/; no part named, so the default measurement site sm120 is assumed

## Conclusion

**Opcode mnemonic:** `MOVM`
**Pipe:** `int_pipe`
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Warp-collective matrix transpose / reshape in registers. Implements PTX `movmatrix`.

```
Rd = transpose_or_reshape(Ra)
```

All 32 threads in the warp participate; each thread holds a fragment of the
input matrix in `Ra` and receives a fragment of the transposed/reshaped matrix
in `Rd`. No memory access — pure register-to-register data rearrangement.

## Variants

Single encoding variant, opcode `0b1000111010` (0x23a).

### Syntax

```
@P0 MOVM.16.MT88 Rd, Ra      # 8×8 transpose, 16-bit elements
    MOVM.U4TO8.M832 Rd, Ra    # 8×32 reshape, 4→8 bit upcast
    MOVM.S4TO8.M832 Rd, Ra    # 8×32 reshape, signed 4→8 bit upcast
    MOVM.U2TO4.M864 Rd, Ra    # 8×64 reshape, 2→4 bit upcast
    MOVM.S2TO4.M864 Rd, Ra    # 8×64 reshape, signed 2→4 bit upcast
```

## Modifiers

### Element size / conversion (`sz`) — bits [77:75], enum `LDSM_SZ` (shared with LDSM)

| Value | Mnemonic | Notes |
|:---:|---|---|
| 0 | `.16` | 16-bit elements, no conversion |
| 1 | `.U4TO8` | Unsigned 4→8 bit upcast |
| 2 | `.S4TO8` | Signed 4→8 bit upcast |
| 3 | `.U2TO4` | Unsigned 2→4 bit upcast |
| 4 | `.S2TO4` | Signed 2→4 bit upcast |
| 5–7 | INVALID | |

### Matrix mode (`mode`) — bits [79:78], enum `MOVM_MODE`

| Value | Mnemonic | Description | Reg count |
|:---:|---|---|:---:|
| 0 | `MT88` | Transposed 8×8 matrix | 1 reg (32b) |
| 1 | `M832` | 8×32 reshape | 2 regs (64b), Rd % 2 == 0 |
| 2 | `M864` | 8×64 reshape | 2 regs (64b), Rd % 2 == 0 |
| 3 | INVALID | | — |

### Legal combos

| Mode | Required sz |
|---|---|
| MT88 | `.16` only |
| M832 | `.U4TO8` or `.S4TO8` |
| M864 | `.U2TO4` or `.S2TO4` |

### IDEST_SIZE

- MT88: 32
- M832: 64
- M864: 64

ISRC_A_SIZE is always 32 (1 source register).

## Bit layout (128-bit)

```
[124:122],[109:105] w8  opex
[121:116]           w6  req_bit_set
[115:113]           w3  src_rel_sb       (VarLatOperandEnc)
[112:110]           w3  dst_wr_sb        (VarLatOperandEnc)
[103:102]           w2  pm_pred
[91][11:0]          w13 opcode           (0x23a)
[79:78]             w2  stride/mode
[77:75]             w3  sz
[31:24]             w8  Ra
[23:16]             w8  Rd
[15]                w1  Pg_not
[14:12]             w3  Pg
```

Extremely compact encoding — only Rd, Ra, mode, and sz. No address fields,
no offset, no uniform registers.

## PTX→SASS mapping

MOVM implements PTX `movmatrix.sync.aligned.m8n8.trans.b16` (sm_75+).

| PTX | SASS |
|-----|------|
| `movmatrix.sync.aligned.m8n8.trans.b16 d, a` | `MOVM.16.MT88 Rd, Ra` |

The PTX spec only defines `.m8n8.trans.b16` (8×8 transpose, 16-bit elements),
matching MOVM's MT88 + sz=16 combo.

The M832/M864 modes with U4TO8/S4TO8/U2TO4/S2TO4 conversions are **SASS-level
extensions** — not directly expressible in PTX `movmatrix`. They provide
register-to-register element-size upcast during matrix reshape, used internally
by the compiler when lowering certain `mma` data paths.

## Comparison with LDSM

| Property | MOVM | LDSM |
|---|---|---|
| Operation | Register → Register | Shared memory → Register |
| Pipe | `int_pipe` | `mio_pipe` |
| VQ | `$VQ_AGU` | `$VQ_AGU` |
| Size enum | LDSM_SZ (same) | LDSM_SZ |
| Modes | MT88, M832, M864 | M88, MT88, M816, M832 |
| Address fields | None | Ra + URb + offset |
| Dest regs | 1–2 | 1–4 |
| Opcode | 0x23a | 0x183b / 0x83b |
| Shader constraint | None (all shaders) | CS only |

MOVM is essentially the register-to-register counterpart of LDSM's matrix
layout conversion: LDSM loads from SMEM with layout transform, MOVM transposes
in registers. Both use the same element-size upcast mechanism (LDSM_SZ).

## History / retracted hypotheses

> Claims below were **superseded, refuted, or never settled** by later work; they are kept
> for provenance. Do not cite them as current.

## Open questions

- **M832/M864 triggering**: What PTX construct causes ptxas to emit these
  modes? Possibly related to int8/int4 `mma` data paths where the compiler
  needs to reshape register fragments between LDSM loads and MMA consumption.
- **ISRC_A_SIZE = 32 for M832/M864**: Despite the dest being 64 bits, the
  source is always 32. This implies the element upcast expands 32 bits of
  source data into 64 bits of destination data.

