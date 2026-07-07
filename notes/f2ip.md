# F2IP — Float to Integer, Packed

**Opcode mnemonic:** F2IP  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Converts a 32-bit float to an 8-bit integer with rounding/saturation: `Rd = trunc/round((float)Rb, dstfmt)`. Destination format is U8 or S8 (packed into 32-bit Rd). The source is always F32. Rounding mode is ROUND (round-to-nearest-even) or TRUNC (truncate toward zero).

This is the reverse instruction of I2FP — native int_pipe float-to-int with packed output.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `f2ip__RRR` | `0x243` | `F2IP.U8 Rd, Rb` |
| `f2ip__RIR` | `0x843` | `F2IP.U8 Rd, imm32` |
| `f2ip__RRI` | `0x443` | `F2IP.U8 Rd, Ra, imm32` (packed merge) |
| `f2ip__RRC` | `0x643` | `F2IP.U8 Rd, Ra, c[bank][offset]` |
| `f2ip__RRCx` | `0x1643` | `F2IP.U8 Rd, Ra, c[URb][offset]` |
| `f2ip__RCR` | `0xa43` | `F2IP.U8 Rd, c[bank][offset]` |
| `f2ip__RCxR` | `0x1a43` | `F2IP.U8 Rd, c[URb][offset]` |
| `f2ip__RUR` | `0x1c43` | `F2IP.U8 Rd, URb` |
| `f2ip__RRU` | `0x1e43` | `F2IP.U8 Rd, Ra, URb` |

Three-register variants (RRI, RRC, RRCx, RRU) support packing: merge two 8-bit values into the 32-bit destination.

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| dstfmt | — | U8=0, S8=1 |
| srcfmt | — | F32 (always) |
| rnd | — | ROUND (round to nearest), TRUNC (truncate) |

## Bit layout (RRR — opcode 0x243)

```
[79:78]             stride   <= rnd
[77:75]             sz       <= dstfmt (U8=0)
[39:32]             Rb       <= Rb (F32 source)
[23:16]             Rd       <= Rd
[91:91],[11:0]      opcode   <= 0b1001000011
```

## Cross-comparison

| Instruction | Direction | Pipe | Packed? |
|-------------|-----------|------|---------|
| I2FP | int→F32 | int_pipe | No (single) |
| F2IP | F32→int | int_pipe | Yes (merge 2×8→32) |
| I2IP | int→int | int_pipe | Yes |

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. Coupled scoreboard, standard integer-pipe latency.
