# UBMSK — Uniform Bitmask

**Opcode mnemonic:** UBMSK  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Creates a bitmask from position and size: `URd = bitmask(URa, URb)` or `URd = bitmask(imm32, URb)`. The CWMode modifier selects clamp (C) or wrap (W) behavior for overflow. Equivalent to `BMSK` for uniform registers.

No empirical examples found.

## Variants

| Variant | Opcode | Format |
|---------|--------|--------|
| `ubmsk__URURUR_URUR` | `0x129b` | `UBMSK.C URd, URa, URb` |
| `ubmsk__URuIUR_URI` | `0x189b` | `UBMSK.C URd, URa, imm32` |

## Modifiers

| Modifier | Field | Bit | Values |
|----------|-------|-----|--------|
| cw | sz | [75] | 0=C(clamp), 1=W(wrap) |

## Bit layout (noimm — opcode 0x129b)

```
[75:75]         sz        <= cw
[37:32]         Ra_URb    <= URb
[29:24]         Sa        <= URa
[21:16]         URd       <= URd
[91:91],[11:0]  opcode    <= 0b1001010011011
```

## Latency

`UDP_subset` group: output 1–7 cycles, true-dependency 4–12 cycles.
