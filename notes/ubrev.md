# UBREV — Uniform Bit Reverse

**Opcode mnemonic:** UBREV  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Reverses the order of bits in a uniform register: `URd = bit_reverse(URb)`. Bit 0 becomes bit 31, bit 1 becomes bit 30, etc. Equivalent to `BREV` for uniform registers.

No empirical examples found.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `ubrev__URURUR_URUR` | `0x12be` | `UBREV URd, URb` |
| `ubrev__URuIUR_URI` | `0x18be` | `UBREV URd, imm32` |

## Bit layout (noimm — opcode 0x12be)

```
[37:32]         Ra_URb    <= URb
[21:16]         URd       <= URd
[91:91],[11:0]  opcode    <= 0b1001010111110
```

Imm variant: URb replaced with 32-bit immediate at [63:32].

## Latency

`UDP_subset` group: output 1–7 cycles, true-dependency 4–12 cycles.
