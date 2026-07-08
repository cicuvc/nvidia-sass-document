# BREV — Bit Reverse

**Opcode mnemonic:** BREV  |  **Pipe:** `mio_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`

## Semantics

Reverses the order of bits in a register: `Rd = bit_reverse(Rb)`. Bit 0 becomes bit 31, bit 1 becomes bit 30, etc. No modifier options — single-function instruction.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `brev__RRR_RRR` | `0x301` | `BREV Rd, Rb` |
| `brev__RIR` | `0x901` | `BREV Rd, imm32` |
| `brev__RCR` | `0xb01` | `BREV Rd, c[bank][offset]` |
| `brev__RCxR` | `0x1b01` | `BREV Rd, c[URb][offset]` |
| `brev__RUR` | `0x1d01` | `BREV Rd, URb` |

## Bit layout (RRR — opcode 0x301)

```
[39:32]              Rb         <= Rb
[23:16]              Rd         <= Rd
[91:91],[11:0]       opcode     <= 0b1100000001
```

## Key features

- **mio_pipe**, **VQ_MUFU**, decoupled scoreboard with variable-latency encoding
- Single source, single destination — simplest of the MUFU bit-manipulation ops

## Cross-comparison

| Instruction | Pipe | Function | Modifier |
|-------------|------|----------|----------|
| POPC | mio_pipe | Count set bits | `[~]` (count zeros) |
| FLO | mio_pipe | Find leading one | `[~]`, SH, fmt |
| BREV | mio_pipe | Bit reverse | None |
| UBREV | udp_pipe | Uniform bit reverse | None |
| UPOPC | udp_pipe | Uniform popcount | `[~]` |
| UFLO | udp_pipe | Uniform find leading one | `[~]`, SH |

## Latency

`mio_pipe`, MUFU dispatch. Decoupled scoreboard with variable-latency encoding.
