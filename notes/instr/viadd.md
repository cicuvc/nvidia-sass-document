# VIADD — Vector Integer Add

**Opcode mnemonic:** VIADD  |  **Pipe:** `fmalighter_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Vector integer addition dispatched through the floating-point pipeline. Supports two formats:
- **32**: Single 32-bit add — `Rd = Ra + Rb` (or `Ra - Rb` with `[-]` on Rb)
- **16x2**: Dual 16-bit SIMD add — packed 2×16-bit addition in one instruction

The `[-]` modifier on Rb negates the second operand, effectively turning this into a subtract instruction.

## Why fmalighter_pipe?

Issued on the FP pipeline (not the integer pipe) for scheduling balance — allows parallel execution of integer ops alongside FXU-bound arithmetic, improving throughput in mixed integer+float code. This is a key Hopper (sm_90) optimization.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `viadd__RRR_RRR` | `0x236` | `VIADD Rd, Ra, [-]Rb` |
| `viadd__RIR` | `0x836` | `VIADD Rd, Ra, imm32` |
| `viadd__RCR` | `0xa36` | `VIADD Rd, Ra, [-]c[bank][offset]` |
| `viadd__RCxR` | `0x1a36` | `VIADD Rd, Ra, [-]c[URb][offset]` |
| `viadd__RUR` | `0x1c36` | `VIADD Rd, Ra, [-]URb` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| fmt | sz | [73] | 0=32, 1=16x2 |
| Rb negate | Sb_invert | [63] | 1=`[-]` |

## Bit layout (RRR — opcode 0x236)

```
[73:73]              sz        <= fmt
[63:63]              Sb_invert <= Rb@negate
[39:32]              Rb        <= Rb
[31:24]              Ra        <= Ra
[23:16]              Rd        <= Rd
[91:91],[11:0]       opcode    <= 0b1000110110
```

## Cross-comparison

| Property | IADD3 | VIADD |
|----------|-------|-------|
| Pipe | `int_pipe` | `fmalighter_pipe` |
| Three inputs? | Yes (Ra+Rb+Rc) | No (Ra+Rb only) |
| Packed ops | No (single 32-bit) | Yes (16x2) |
| Negate | No | Yes (`[-]` on Rb) |
| Immediate | Via IADD32I | Yes (RIR variant) |

## Latency

`fmalighter_pipe`, `INST_TYPE_COUPLED_MATH`. Dispatched to the lighter FP pipeline for scheduling balance.
