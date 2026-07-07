# UCLEA — Uniform Clear Effective Address

**Opcode mnemonic:** UCLEA  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Computes an aligned effective address in uniform registers: `URd.64 = clear_low_bits(URa.64 + URb, constSize)` (or `URa.64 + imm16`). The `constSize` (0–8) controls how many low bits are cleared, aligning the result to a 2<sup>constSize</sup> boundary.

Both URd and URa are 64-bit values (register pairs, even-aligned). UPu is a uniform predicate output (likely flags overflow or special condition).

No empirical examples found in libcublas or ptxas output on sm_90, CUDA 13.1.

## Variant overview

| Variant | Opcode | Format |
|---------|--------|--------|
| `uclea__URb` | `0x1cbc` | `UCLEA URd, UPu, URa, URb, constSize` |
| `uclea__Imm` | `0x18bc` | `UCLEA URd, UPu, URa, imm16, constSize` |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| constSizeU04 | constSizeU04 | [76:73] | 0–8 (2<sup>n</sup> alignment) |

## Bit layout

### URb variant — opcode 0x1cbc

```
[83:81]         Pu             <= UPu
[76:73]         constSizeU04   <= constSize
[37:32]         Ra_URb         <= URb
[29:24]         Sa             <= URa
[21:16]         URd            <= URd
[91:91],[11:0]  opcode         <= 0b1110010111100
```

### Imm variant — opcode 0x18bc

URb replaced with 16-bit immediate at [47:32].

## Latency

`UDP_subset` group. IDEST_SIZE=64 (register pair), ISRC_A_SIZE=64. Latency: 1–7 cycles output, 4–12 cycles true-dependency.

## Open questions

- No empirical examples. Likely used for TMA descriptor base-address alignment in UTMA sequences.
- `constSize` range 0–8 means alignment up to 256 bytes. Typical TMA descriptors require 32-byte (constSize=5) or 128-byte alignment.
- UPu predicate output — overflow? carry? zero?
