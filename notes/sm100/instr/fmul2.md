# FMUL2 — packed FP32x2 Multiply  → PTX `mul.f32x2`

**Opcode mnemonic:** `FMUL2` — 3 variants: RRR (0x24a), RRU (0x1c4a), RIR (0x84a)
**Pipe:** `fmalighter_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

New on sm100 (Blackwell). `FMUL2 Rd, Ra, Rb` computes `Rd = Ra * Rb` as a
packed FP32x2 operation on 64-bit register pairs. Each operand (Ra/Rb) carries
an `ISWZA_fadd2` swizzle: `F32x2`(packed pair), `F32x2.LO_HI`(swapped), or
`F32`(scalar broadcast). Per-element negate/absolute on each operand via
`Ra@negate`/`Ra@absolute`, `Rb@negate`/`Rb@absolute`. `INST_TYPE_COUPLED_MATH`
— occupies two coupled issue slots.

## Semantics
`FMUL2 Rd, Ra, Rb` where per-operand width/order is `ISWZA_fadd2`:
- **`F32x2`** = 0: packed pair in a 64-bit register.
- **`F32x2.LO_HI`** = 1: hi/lo swapped.
- **`F32`** = 2: 32-bit scalar broadcast.

`IDEST_SIZE = 64`, `ISRC_A/B_SIZE = 32 + (packed ? 32 : 0)`. `Rd` must be
even-aligned. Rounding via `rnd`[79:78], flush via `fmz`[80]∥[76].

## Variants
| Class | Opcode | Operand config |
|-------|--------|---------------|
| `fmul2_rb__RRR` | 0x24a | Rd, Ra, Rb (all register) |
| `fmul2_urb__RUR` | 0x1c4a | Rd, URa, Rb (uniform A) |
| `fmul2_imm__RIR` | 0x84a | Rd, imm, Rb (immediate A) |

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `rnd` | `Round1` | [79:78] | RN=0, RP=1, RZ=2, RM=3 |
| `fmz` | `FMZ_hfma2` | [80]∥[76] | flush-mul-to-zero |
| `iswzA/B` | `ISWZA_fadd2` | [82:81] / [88:87] | F32x2=0, LO_HI=1, F32=2 |
| `negA` | `NEGA` (PP=0, NP=1) | [83] | negate Ra |
| `Ra@negate` / `@absolute` | — | [72] / [73] | per-element negate/abs on Ra |
| `Rb@negate` / `@absolute` | — | [63] / [62] | per-element negate/abs on Rb |

## Encoding (RRR, opcode 0x24a)
```
[91]∥[11:0]         opcode     = 0x24a
[88:87] iswzB                    [83] negA     [82:81] iswzA
[80]∥[76] fmz        [79:78] rnd
[73] Ra.absolute    [72] Ra.negate
[63] Rb.negate      [62] Rb.absolute
[39:32] Rb           [31:24] Ra       [23:16] Rd
[15] Pg_not         [14:12] Pg
```

## Cross-references
- `notes/sm100/instr/ffma2.md` — the FMA counterpart (same iswz/swizzle model,
  3 operands: A·B+C). FMUL2 uses the Ra+Rb operand slots only (no Rc).
- `notes/sm100/instr/fadd2.md` — the add counterpart (2 operands: Ra+Rc).
