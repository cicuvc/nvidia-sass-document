# REDUX / CREDUX — uniform warp reduction  → PTX `redux.sync`

**Opcode mnemonic:** `REDUX` = 0x3c4 (classic uniform), `CREDUX` = 0x2cc (coupled, sm100-new)
**Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH` (CREDUX only)
**Virtual queue:** None (non-decoupled math op)

`REDUX` is the Hopper-era warp-level uniform reduction (AND/OR/XOR/SUM/MIN/MAX,
U32/S32). **`CREDUX`** (= Coupled REDUX) is the sm100 addition: extends the op
set with **F32** (MIN/MAX + ABS/NaN), occupies the coupled-math dispatch slot,
and simplifies the operand model to a single source register + uniform result.

## REDUX (classic, 0x3c4) — reference
`REDUX URd, Ra, membermask` | ops: AND/OR/XOR/SUM/MIN/MAX | sz: U32/S32.
Already documented in the sm90 notes; unchanged on sm100.

## CREDUX (sm100-new, 0x2cc) — coupled uniform reduction
`CREDUX.op.sz{.NaN} URd, Ra` — no explicit membermask (implicit from warp
predication). Destination is a **uniform register**; source is a single GP
register. `INST_TYPE_COUPLED_MATH` = occupies one coupled issue pair.

### Semantics
Reduces `Ra` across predicated-active threads with the specified `.op` / `.sz`:
- `U32`/`S32`: MIN / MAX.
- **`F32`**: MIN / MAX + optional `.ABS` (absolute value before reduction) and
  `.NaN` (canonical NaN if any input is NaN; without it, non-NaN values are
  preferred and all-NaN returns canonical NaN). `MAXABS`/`MINABS` are `F32`-only
  and require the `.ABS` qualifier.

Writes the scalar reduced value into `URd`.

### Variants (from PTX `redux.sync`)
| CREDUX op | PTX | sz restriction |
|-----------|-----|:---:|
| `MIN`(2) | `.min` | U32/S32/F32 |
| `MAX`(0) | `.max` | U32/S32/F32 |
| `MAXABS`(1) | `.max.abs` | F32 only |
| `MINABS`(3) | `.min.abs` | F32 only |

`NaN`[77] only valid with `F32`. `.abs` is implicit in `MAXABS`/`MINABS`.

### Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `op` | `CREDUX_OP` | [79:78] | MAX=0, MAXABS=1, MIN=2, MINABS=3 |
| `sz` | `CREDUX_SZ` | [74:73] | U32=0, S32=1, F32=2 |
| `NaN` | `NAN` | [77] | `.NaN` qualifier (F32 only) |

### Encoding (128-bit)
```
[91]∥[11:0]         opcode     = 0x2cc
[79:78]             op          [77] NaN     [74:73] sz
[31:24]             Ra          [23:16] URd  (uniform dest)
[15]                Pg_not      [14:12] Pg
```

### Verified encodings (cuobjdump, sm_100a)
| PTX | SASS | op | sz | NaN |
|-----|------|:--:|:--:|:---:|
| `redux.sync.min.s32 URd, Ra, mask` | `CREDUX.MIN.S32 UR6, R6` | 2 | 1 | 0 |
| `redux.sync.min.NaN.f32 URd, Ra, mask` | `CREDUX.MIN.F32.NAN UR6, R6` | 2 | 2 | 1 |
| `redux.sync.max.abs.f32 URd, Ra, mask` | `CREDUX.MAXABS.F32 UR6, R6` | 1 | 2 | 0 |

### Cross-references
- `notes/sm90/instr/redux.md` — the original REDUX (Hopper). CREDUX is the
  coupled-math sm100 extension adding F32 + ABS/NaN.
- `notes/sm100/instr/ffma2.md` — same `INST_TYPE_COUPLED_MATH` dispatch.

## Open questions
- The membermask operand in PTX `redux.sync` — is it dropped in the CREDUX
  encoding (only full-warp masks), or encoded implicitly through the predicate
  word? (The SASS has no mask field.)
- Why `CREDUX` uses `INST_TYPE_COUPLED_MATH` while classic `REDUX` is a plain
  `udp_pipe` op — does the F32 path share the `fmalighter_pipe` or similar
  datapath that justifies the coupled slot?
