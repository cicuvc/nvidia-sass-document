# I2IP — Integer to Integer, Packed

**Opcode mnemonic:** I2IP  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Packed integer-to-integer conversion with saturation and ReLU activation: `Rd = saturate(relu(truncate(Rb, dstfmt)))`. Converts from S32 to narrower integer formats, packing multiple destination elements into a single 32-bit register.

Three packing densities:
- **U8/S8/U16/S16**: 4×8b or 2×16b packed per 32-bit Rd
- **U4/S4 (24)**: 8×4b packed per 32-bit Rd (used in INT4 quantization)
- **U2/S2 (28)**: 16×2b packed per 32-bit Rd (used in INT2 quantization)

The `.RELU` ALT variant clamps negative values to 0 before conversion. The `nosatrelu`/`SAT` variant enables saturation (clamping to destination range).

This is the **deeply specialized DL quantization instruction** — directly supporting the narrow integer formats used in model compression (INT4, INT2).

## Variants (30 total)

Matrix: {U8/S8/U16/S16, U4/S4, U2/S2} × {R, I, C, CXb, URb} × {nosatrelu, relu ALT}

| Group | Opcode | Packing |
|-------|--------|---------|
| Base (8/16b) | `0x239` | 4×8b or 2×16b |
| 24 (4-bit) | `0x239` | 8×4b |
| 28 (2-bit) | `0x239` | 16×2b |

All share the same opcode; the dstfmt field distinguishes the packing mode. RELU ALTs share the opcode with different satrelu encoding.

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| dstfmt | — | U8/S8/U16/S16 (base), U4/S4 (24), U2/S2 (28) |
| satrelu | — | nosatrelu, RELU (clamp ≥0 before truncation) |

## Bit layout (RRR base — opcode 0x239)

```
[77:76]             insert   <= dstfmt (2-bit for base width)
[73:73]             sz       <= srcfmt (S32=0)
[39:32]             Rb       <= Rb
[23:16]             Rd       <= Rd
[91:91],[11:0]      opcode   <= 0b1000111001
```

The 2-bit dstfmt selectors plus additional bits distinguish the sub-formats (U4/S4, U2/S2) and the RELU mode.

## Cross-comparison

| Instruction | Pipe | Direction | Destination | Packing |
|-------------|------|-----------|-------------|---------|
| I2I | `int_pipe` | S32→narrower | U8/S8/U16/S16 | No (legacy) |
| I2IP | `int_pipe` | S32→narrower | U8/S8/U16/S16/U+S4/U+S2 | **Yes** (packed) |
| F2IP | `int_pipe` | F32→U8/S8 | U8/S8 | Yes |

I2IP is the modern, actively-used replacement for I2I with packed output and RELU support for DL inference.

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. Coupled scoreboard, standard integer-pipe latency.
