# FLO — Find Leading One

**Opcode mnemonic:** FLO  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Finds the bit position of the most-significant set bit in a register: `Rd = find_leading_one([~]Rb)`. The `[~]` modifier inverts first, giving find_leading_zero. The `SH` modifier optionally shifts the result (presumably by a fixed amount). Result is 0-based (0–31 for a 32-bit input).

Output `Pu` (predicate) flags special conditions (input zero → all bits set? overflow?).

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `flo__RRR_RRR` | `0x300` | `FLO Rd, Pu, [~]Rb` |
| `flo__RIR` | `0x900` | `FLO Rd, Pu, imm32` |
| `flo__RCR` | `0xb00` | `FLO Rd, Pu, [~]c[bank][offset]` |
| `flo__RCxR` | `0x1b00` | `FLO Rd, Pu, [~]c[URb][offset]` |
| `flo__RUR` | `0x1d00` | `FLO Rd, Pu, [~]URb` |

## Bit layout (RRR — opcode 0x300)

```
[83:81]              Pu         <= Pu (flag predicate)
[74:74]              sh         <= sh (0=nosh, 1=SH)
[73:73]              sz         <= fmt (REDUX_SZ=S32=0)
[63:63]              Sb_invert  <= Rb@invert (1 = [~])
[39:32]              Rb         <= Rb
[23:16]              Rd         <= Rd
[91:91],[11:0]       opcode     <= 0b1100000000
```

## Key features

- **mio_pipe**, **VQ_MUFU**, decoupled scoreboard with variable-latency encoding
- Pu predicate output for flag (e.g., input-was-zero)
- SH modifier for result shift

## Latency

`mio_pipe`, MUFU dispatch. Latency comparable to other MUFU ops (higher than int_pipe).
