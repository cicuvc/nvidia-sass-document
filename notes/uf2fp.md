# UF2FP — Uniform Float to Float, Packed

**Opcode mnemonic:** UF2FP  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Uniform-register float-to-float conversion dispatched on the UDP pipeline. Converts between FP formats (F32↔F16, F32↔BF16) stored in uniform registers, with optional packed-element merging.

Three merge modes:
- **PACK_ABONLY**: Pack two F16 values from two URs into one F32 URd (low/high half)
- **MERGE_CONLY**: Merge conversion result with a separate C register (partial write)
- **Default**: Simple single-format conversion

Rounding mode: RN (round-to-nearest).

## Variants

| Variant | Opcode | Merge Mode | Format |
|---------|--------|------------|--------|
| `uf2fp__URURUR` | `0x12ba` | PACK_AB | `UF2FP.F16.F32 URd, URa, URb` |
| `uf2fp__URIUR` | `0x18ba` | PACK_AB | `UF2FP.F16.F32 URd, URa, imm32` |
| `uf2fp_merge_c__URURUR` | `0x12ba` | MERGE_C | `UF2FP.F16.F32 URd, URa, URb` |
| `uf2fp_merge_c__URIUR` | `0x18ba` | MERGE_C | `UF2FP.F16.F32 URd, URa, imm32` |
| `uf2fp_merge_c__URURI` | `0x14ba` | MERGE_C | `UF2FP.F16.F32 URd, URa, URb, imm32` |

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| dfmt.sfmt | — | F16.F32, BF16.F32, etc. (combined dst+src format) |
| merge | — | PACK_ABONLY, MERGE_CONLY |
| rnd | — | RN (round-to-nearest) |

## Cross-comparison

| Property | F2F | F2FP | UF2FP |
|----------|-----|------|-------|
| Pipe | `mio_pipe` | `udp_pipe` | `udp_pipe` |
| Registers | Regular | Regular | Uniform |
| Packed | No | Yes | Yes (merge modes) |
| pTxas emits? | No | Yes | Not observed |

## Latency

`udp_pipe`, `INST_TYPE_COUPLED_MATH`. Uniform register pipeline latency (UDP_subset group: output 1–7 cycles, true-dependency 4–12 cycles).
