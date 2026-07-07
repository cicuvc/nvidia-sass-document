# DMUL — FP64 Multiply

**Opcode:** `0x228` (RRR), `0x828` (RsIR), `0xa28` (RCR), `0x1a28` (RCxR), `0x1c28` (RUR)  
**Pipe:** `fma64lite_pipe`, `$VQ_REDIRECTABLE`  
**TYPE:** `INST_TYPE_COUPLED_EMULATABLE`

## Semantics

`Rd = Ra * Rb` in double-precision (FP64). All operands are 64-bit register
pairs (even-aligned). 2-operand FP64 multiply — same structural family as FMUL
(F32) and HMUL2 (F16).

## Format

`@Pg DMUL{.rnd} Rd, [-]|[||]Ra{.reuse}, [-]|[||]Rb{.reuse}`

## Verified encodings

| Disassembly | PTX |
|-------------|-----|
| `DMUL R2, R10, UR4` | `mul.rn.f64` |
| `DMUL.RM R6, R10, UR4` | `mul.rm.f64` |
| `DMUL.RP R8, R10, UR4` | `mul.rp.f64` |
| `DMUL.RZ R10, R10, UR4` | `mul.rz.f64` |

All observed instances use the RUR_RU variant (Rb promoted to uniform register).
Rounding modifier encoding is managed via opex/scoreboard configuration rather
than a simple 2-bit field.

## DMUL vs DFMA vs DADD

| Property | DADD (idx 123) | DMUL (idx 124) | DFMA (idx 122) |
|----------|:---:|:---:|:---:|
| Operands | Rd, Ra | Rd, Ra, Rb | Rd, Ra, Rb, Rc |
| Opcode base | 0x229 | 0x228 | 0x22b |
| Variants | 5 | 5 | 9 |
| ISRC_C_SIZE | 0 | 0 | 64 |

## PTX to SASS

| PTX | SASS |
|-----|------|
| `mul.rn.f64 %rd, %ra, %rb` | `DMUL Rd, Ra, URb` |
| `mul.rm.f64` | `DMUL.RM` |
| `mul.rp.f64` | `DMUL.RP` |
| `mul.rz.f64` | `DMUL.RZ` |
