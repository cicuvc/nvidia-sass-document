# FADD2 — packed FP32x2 Add  → PTX `add.f32x2`

**Opcode mnemonic:** `FADD2` — 3 variants: RRR (0x24b), RRU (0x1e4b), RRI (0x44b)
**Pipe:** `fmalighter_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

New on sm100 (Blackwell). `FADD2 Rd, Ra, Rc` computes `Rd = Ra + Rc` as a
packed FP32x2 operation on 64-bit register pairs. Each operand (Ra/Rc) carries
an `ISWZA_fadd2` swizzle: `F32x2`(packed pair), `F32x2.LO_HI`(swapped), or
`F32`(scalar broadcast). Per-element negate/absolute via `Ra@negate`, `Ra@absolute`,
`Rc@negate`, `Rc@absolute`. Same `INST_TYPE_COUPLED_MATH` as FFMA2 — occupies two
coupled issue slots.

## Semantics
`FADD2 Rd, Ra, Rc` where each operand's interpretation is governed by `ISWZA_fadd2`:
- **`F32x2`** = 0: packed pair in a 64-bit register.
- **`F32x2.LO_HI`** = 1: packed pair with hi/lo swapped.
- **`F32`** = 2: 32-bit scalar broadcast.

`IDEST_SIZE = 64`, `ISRC_A/C_SIZE = 32 + (packed ? 32 : 0)`. `Rd` must be
even-aligned. Rounding via `rnd`[79:78] (RN=0, RP=1, RZ=2, RM=3), flush-to-zero
via `ftz`[80].

## Variants
| Class | Opcode | Operand config |
|-------|--------|---------------|
| `fadd2_rc__RRR` | 0x24b | Rd, Ra, Rc (all register) |
| `fadd2_urc__RRU` | 0x1e4b | Rd, Ra, URc (uniform C) |
| `fadd2_imm__RRI` | 0x44b | Rd, Ra, imm (immediate C) |

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `rnd` | `Round1` | [79:78] | RN=0, RP=1, RZ=2, RM=3 |
| `ftz` | `FTZ` | [80] | flush-to-zero |
| `iswzA/C` | `ISWZA_fadd2` | [82:81] / [85:84] | F32x2=0, LO_HI=1, F32=2 |
| `negA/C` | `NEGA` (PP=0, NP=1) | [83] / [86] | negate |
| `Ra@negate` / `@absolute` | — | [72] / [73] | per-element negate/abs on Ra |
| `Rc@negate` / `@absolute` | — | [63] / [62] | per-element negate/abs on Rc |

## Encoding (RRR, opcode 0x24b)
```
[91]∥[11:0]         opcode     = 0x24b
[86] negC           [85:84] iswzC    [83] negA     [82:81] iswzA
[80] ftz            [79:78] rnd
[73] Ra.absolute    [72] Ra.negate
[63] Rc.negate      [62] Rc.absolute
[39:32] Rc(≡Rb)     [31:24] Ra       [23:16] Rd
[15] Pg_not         [14:12] Pg
```

## Cross-references
- `notes/sm100/instr/ffma2.md` — same ISWZA/swizzle model, per-element negate/abs,
  `INST_TYPE_COUPLED_MATH`. FFMA2 has 3 operands (A·B+C); FADD2 has 2 (A+C,
  using the Ra+Rc operand slots).
- `notes/sm100/instr/fmul2.md` (below) — the multiply-only counterpart.
