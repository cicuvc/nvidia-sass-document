# POPC — Population Count

**Opcode mnemonic:** POPC  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Counts the number of set bits (population count) in a register: `Rd = popcount([~]Rb)`. The `[~]` modifier inverts the source first, effectively counting zero bits.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `popc__RRR_RRR` | `0x309` | `POPC Rd, [~]Rb` |
| `popc__RuIR_RIR` | `0x909` | `POPC Rd, imm32` |
| `popc__RCR_RCR` | `0xb09` | `POPC Rd, [~]c[bank][offset]` |
| `popc__RCxR_RCxR` | `0x1b09` | `POPC Rd, [~]c[URb][offset]` |
| `popc__RUR_RUR` | `0x1d09` | `POPC Rd, [~]URb` |

## Bit layout (RRR — opcode 0x309)

```
[63:63]              Sb_invert  <= Rb@invert (1 = [~])
[39:32]              Rb         <= Rb
[23:16]              Rd         <= Rd
[115:113]            src_rel_sb <= VarLatOperandEnc(src_rel_sb)
[112:110]            dst_wr_sb  <= VarLatOperandEnc(dst_wr_sb)
[91:91],[11:0]       opcode     <= 0b1100001001
```

## Key features

- **mio_pipe**, dispatched to **VQ_MUFU** (multi-function unit)
- **Decoupled** scoreboard: separate RD/WR release, variable-latency encoded
- Single source, single destination (32-bit)

## Latency

`mio_pipe`, `MIO_CBU_OPS_WITHOUT_ELECT` group. MUFU dispatch means higher latency than int_pipe ops.
