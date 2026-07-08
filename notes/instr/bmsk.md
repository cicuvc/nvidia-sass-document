# BMSK — Bitmask

**Opcode mnemonic:** BMSK  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Generates a bitmask from a position and width: `Rd = bitmask(Ra, Rb)`. The combination of `Ra` (start position) and `Rb` (width) produces a contiguous mask of set bits. The `cw` modifier selects clamp (C) or wrap (W) behavior when the range exceeds 32 bits.

Equivalent to the PTX `bfi` (bit-field insert) pattern `(1 << width) - 1` shifted by position.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `bmsk__RRR_RRR` | `0x21b` | `BMSK.C Rd, Ra, Rb` |
| `bmsk__RIR` | `0x81b` | `BMSK.C Rd, Ra, imm32` |
| `bmsk__RCR` | `0xa1b` | `BMSK.C Rd, Ra, c[bank][offset]` |
| `bmsk__RCxR` | `0x1a1b` | `BMSK.C Rd, Ra, c[URb][offset]` |
| `bmsk__RUR` | `0x1c1b` | `BMSK.C Rd, Ra, URb` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| cw | sz | [75] | 0=C (clamp), 1=W (wrap) |

## Bit layout (RRR — opcode 0x21b)

```
[75:75]              sz   <= cw (CWMode)
[39:32]              Rb   <= Rb (width/position)
[31:24]              Ra   <= Ra (start position)
[23:16]              Rd   <= Rd
[91:91],[11:0]       opcode <= 0b1000011011
```

## Cross-comparison

| Property | BMSK | UBMSK |
|----------|------|-------|
| Pipe | `int_pipe` | `udp_pipe` |
| Registers | Regular (Rd,Ra,Rb) | Uniform (URd,URa,URb) |
| Opcode | `0x21b` | `0x129b` |
| Same modifiers | CWMode (C/W) | CWMode (C/W) |

## Latency

`int_pipe`, `FXU_OPS` group. Standard integer-pipe latency (1 cycle output typical).
