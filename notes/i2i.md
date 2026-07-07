# I2I — Integer to Integer Conversion

**Opcode mnemonic:** I2I  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Converts a 32-bit integer to a narrower integer format with optional saturation: `Rd = saturate(truncate(Rb, dstfmt))`. Source is always S32; destination can be U8, S8, U16, or S16.

The SAT modifier enables saturation (clamp to destination range) on overflow. Without saturation, behavior is simple truncation (wrap-around).

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `i2i__RRR_RRR` | `0x238` | `I2I.SAT.U8 Rd, Rb` |
| `i2i__RIR` | `0x838` | `I2I.SAT.U8 Rd, imm32` |
| `i2i__RCR` | `0xa38` | `I2I.SAT.U8 Rd, c[bank][offset]` |
| `i2i__RCxR` | `0x1a38` | `I2I.SAT.U8 Rd, c[URb][offset]` |
| `i2i__RUR` | `0x1c38` | `I2I.SAT.U8 Rd, URb` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| dstfmt | insert | [77:76] | 0=U8, 1=S8, 2=U16, 3=S16 |
| srcfmt | — | — | Always S32 |
| SAT | — | — | Always SAT (saturation enabled) |

## Bit layout (RRR — opcode 0x238)

```
[77:76]              insert   <= dstfmt
[39:32]              Rb       <= Rb
[23:16]              Rd       <= Rd
[91:91],[11:0]       opcode   <= 0b1000111000
```

RIR variant: Rb replaced with 32-bit signed immediate at [63:32].

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. `FXU_OPS` group. Standard integer-pipe latency (1 cycle output typical).
