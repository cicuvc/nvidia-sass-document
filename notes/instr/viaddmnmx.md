# VIADDMNMX — Vector Integer Add with Min/Max

**Opcode mnemonic:** VIADDMNMX  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Three-input vector integer add-then-min/max: `Rd = minmax(Ra + [-]Rb, Rc [, Pp])`. First adds `Ra + Rb` (with optional `[-]` on Rb for subtract), then applies min or max against `Rc`. The `fmt` field selects unsigned (U32) or signed (S32) comparison for the min/max step. `.RELU` clamps the final result to ≥0.

Output `Pp` indicates which operand was selected (the add result or the third operand Rc).

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `viaddmnmx__RRR_RRR` | `0x246` | `VIADDMNMX Rd, Ra, [-]Rb, Rc, Pp` |
| `viaddmnmx__RIR` | `0x846` | `VIADDMNMX Rd, Ra, imm32, Rc, Pp` |
| `viaddmnmx__RRI` | `0x446` | `VIADDMNMX Rd, Ra, Rb, imm32, Pp` |
| `viaddmnmx__RRC` | `0x646` | `VIADDMNMX Rd, Ra, Rb, c[bank][offset], Pp` |
| `viaddmnmx__RRCx` | `0x1646` | `VIADDMNMX Rd, Ra, Rb, c[UR][offset], Pp` |
| `viaddmnmx__RCR` | `0xa46` | `VIADDMNMX Rd, Ra, c[bank][offset], Rc, Pp` |
| `viaddmnmx__RCxR` | `0x1a46` | `VIADDMNMX Rd, Ra, c[UR][offset], Rc, Pp` |
| `viaddmnmx__RUR` | `0x1c46` | `VIADDMNMX Rd, Ra, URb, Rc, Pp` |
| `viaddmnmx__RRU` | `0x1e46` | `VIADDMNMX Rd, Ra, Rb, URc, Pp` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| fmt | num | [73:72] | 0=U32, 1=S32 |
| relu | memdesc | [76] | 0=norelu, 1=.RELU |
| Rb negate | Sb_invert | [63] | 1=`[-]` |

## Bit layout (RRR — opcode 0x246)

```
[90:90]              input_reg_sz <= Pp@not
[89:87]              Pnz          <= Pp
[76:76]              memdesc      <= relu
[73:72]              num          <= fmt
[71:64]              Rc           <= Rc (third operand, min/max reference)
[63:63]              Sb_invert    <= Rb@negate
[39:32]              Rb           <= Rb
[31:24]              Ra           <= Ra
[23:16]              Rd           <= Rd
[91:91],[11:0]       opcode       <= 0b1001000110
```

## Cross-comparison

| Instruction | Operation | Inputs | Applicability |
|-------------|-----------|--------|---------------|
| IADD3 | `Ra + Rb + Rc` | 3 reg | General 3-way add |
| VIADD | `Ra + [-]Rb` | 2 reg | Simple add/subtract |
| VIMNMX | `minmax(Ra, Rb)` | 2 reg | Min/max selection |
| VIADDMNMX | `minmax(Ra+Rb, Rc)` | 3 reg | Fused add+min/max |
| VIADDMNMX.RELU | `relu(minmax(Ra+Rb, Rc))` | 3 reg | Fused add + min/max + clamp |

VIADDMNMX fuses an addition with a min/max comparison into a single cycle, useful for:
- Activation functions (ReLU after bias add): `relu(x + bias)`
- Clamping to a limit: `min(x + offset, threshold)`
- DL quantization/conversion pipelines

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. `FXU_OPS` group. Coupled scoreboard.
