# VABSDIFF — Vector Absolute Difference

**Opcode mnemonic:** VABSDIFF  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Computes the absolute difference of two registers (or register-immediate pairs): `Rd = |Ra - Rc|` or the three-input form `Rd = |Ra - Rb| + Rc` (with optional accumulation). Commonly used in motion estimation (SAD — sum of absolute differences) and image processing kernels.

Output predicate `Pu` (typically PT = unconditional) indicates the operation completed. Three register inputs (Ra, Rb, Rc) plus result register.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `vabsdiff__RRR` | `0x214` | `VABSDIFF Rd, Pu, Ra, Rb, Rc` |
| `vabsdiff__RIR` | `0x814` | `VABSDIFF Rd, Pu, Ra, imm32, Rc` |
| `vabsdiff__RRI` | `0x414` | `VABSDIFF Rd, Pu, Ra, Rb, imm32` |
| `vabsdiff__RRC` | `0x614` | `VABSDIFF Rd, Pu, Ra, Rb, c[bank][offset]` |
| `vabsdiff__RRCx` | `0x1614` | `VABSDIFF Rd, Pu, Ra, Rb, c[UR][offset]` |
| `vabsdiff__RCR` | `0xa14` | `VABSDIFF Rd, Pu, Ra, c[bank][offset], Rc` |
| `vabsdiff__RCxR` | `0x1a14` | `VABSDIFF Rd, Pu, Ra, c[UR][offset], Rc` |
| `vabsdiff__RUR` | `0x1c14` | `VABSDIFF Rd, Pu, Ra, URb, Rc` |
| `vabsdiff__RRU` | `0x1e14` | `VABSDIFF Rd, Pu, Ra, Rb, URc` |

## Bit layout (RRR — opcode 0x214)

```
[83:81]         Pu     <= Pu (predicate output, typically PT)
[73:73]         sz     <= fmt (REDUX_SZ=S32=0)
[71:64]         Rc     <= Rc (third register input)
[39:32]         Rb     <= Rb (subtract operand)
[31:24]         Ra     <= Ra (base operand)
[23:16]         Rd     <= Rd
[91:91],[11:0]  opcode <= 0b1000010100
```

## Cross-comparison

| Instruction | Operation | Inputs | Use case |
|-------------|-----------|--------|----------|
| VIADD | `Ra + [-]Rb` | 2 reg | General add/sub |
| VIADDMNMX | `minmax(Ra+Rb, Rc)` | 3 reg | Fused add+clamp |
| VABSDIFF | `|Ra - Rb| + Rc` | 3 reg | Motion estimation / SAD |
| VABSDIFF4 | 4×8-bit `|Ra - Rb|` | 3 reg | Packed SAD for video codecs |

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. Coupled scoreboard.
