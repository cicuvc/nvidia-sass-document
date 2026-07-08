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

## Bit layout (URURUR 0x12ba, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_1(batch_t,usched_info)` | scheduling |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `*7` | fixed |
| [112:110] | dst_wr_sb | 3 | `*7` | fixed |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x12ba | |
| [85:84],[76:75] | dfmt.sfmt | 4 | F2Ffmts2 | F16.F32 / BF16.F32, etc. |
| [81:79] | rndMode | 3 | RNDMODE | RN (only value) |
| [78] | mode | 1 | `*merge` | PACK_ABONLY / MERGE_CONLY |
| [69:64] | Ra_URc | 6 | UniformRegister | = `*63` (unused in PACK_AB mode) |
| [37:32] | Ra_URb | 6 | UniformRegister | second source |
| [29:24] | Sa | 6 | UniformRegister | first source (URa) |
| [21:16] | URd | 6 | UniformRegister | destination |
| [15] | Pg_not | 1 | UPg@not | predicate negate |
| [14:12] | UPg | 3 | UniformPredicate | uniform guard (UPT=7 hidden) |

### Merge_C variant differences
- [78] `*merge` = MERGE_CONLY
- `Ra_URc` at [69:64] holds the C merge register (not `*63`)
- URIUR variant replaces URb with 32-bit immediate at [63:32]; URURI variant adds an immediate at [63:32]

## Cross-comparison

| Property | F2F | F2FP | UF2FP |
|----------|-----|------|-------|
| Pipe | `mio_pipe` | `udp_pipe` | `udp_pipe` |
| Registers | Regular | Regular | Uniform |
| Packed | No | Yes | Yes (merge modes) |
| pTxas emits? | No | Yes | Not observed |

## Latency

`udp_pipe`, `INST_TYPE_COUPLED_MATH`. Uniform register pipeline latency (UDP_subset group: output 1–7 cycles, true-dependency 4–12 cycles).
