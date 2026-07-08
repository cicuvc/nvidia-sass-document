# FSEL — FP32 Select (Conditional Move)

**Opcode mnemonic:** FSEL  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Floating-point conditional select: `Rd = Pp ? Ra : Rb`, with float-specific modifiers on source operands (`[-]` negate, `[||]` absolute value). The FTZ (flush-to-zero) modifier treats denormal inputs as zero.

Equivalent to SEL but for floating-point values with denorm handling.

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `fsel__RRR_RRR` | `0x208` | `FSEL Rd, [-] [\|\|] Ra, [-] [\|\|] Rb, [!]Pp` |
| `fsel__RIR_RIR` | `0x808` | `FSEL Rd, [-] [\|\|] Ra, F32Imm, [!]Pp` |
| `fsel__RCR_RCR` | `0xa08` | `FSEL Rd, [-] [\|\|] Ra, c[bank][offset], [!]Pp` |
| `fsel__RCxR_RCxR` | `0x1a08` | `FSEL Rd, [-] [\|\|] Ra, c[UR][offset], [!]Pp` |
| `fsel__RUR_RUR` | `0x1c08` | `FSEL Rd, [-] [\|\|] Ra, [-] [\|\|] URb, [!]Pp` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| FTZ | UPq_not | [80] | 0=noftz, 1=.FTZ |
| Ra absolute | sz | [73] | 1=`[\|\|]` |
| Ra negate | e | [72] | 1=`[-]` |
| Rb negate | Sb_invert | [63] | 1=`[-]` |
| Rb absolute | Sc_absolute | [62] | 1=`[\|\|]` |

## Bit layout (RRR — opcode 0x208)

```
[90:90]              input_reg_sz_32_dist <= Pp@not
[89:87]              Pnz                  <= Pp
[80:80]              UPq_not              <= ftz
[73:73]              sz                   <= Ra@absolute
[72:72]              e                    <= Ra@negate
[63:63]              Sb_invert            <= Rb@negate
[62:62]              Sc_absolute          <= Rb@absolute
[39:32]              Rb                   <= Rb
[31:24]              Ra                   <= Ra
[23:16]              Rd                   <= Rd
[91:91],[11:0]       opcode               <= 0b1000001000
```

## Cross-comparison

| Property | SEL | FSEL |
|----------|-----|------|
| Type | Integer select | Float select |
| Ra/Rb modifiers | None | `[-]`, `[\|\|]`, `.FTZ` |
| Opcode base | `0x207` | `0x208` |

## Latency

`int_pipe`, `FXU_OPS`. Standard integer-pipe latency (1 cycle output typical).
