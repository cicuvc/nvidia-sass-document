# IDP — Integer Dot Product

**Opcode mnemonic:** `IDP`  
**Pipe:** `fmalighter_pipe` (lightweight FMA pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

4-element or 2-element integer dot product with accumulate. Computes
`Ra·Rb + Rc` where the dot product is over packed sub-word elements:

- **4A mode:** `Rd = Ra.u8[0]×Rb.u8[0] + Ra.u8[1]×Rb.u8[1] + Ra.u8[2]×Rb.u8[2] + Ra.u8[3]×Rb.u8[3] + Rc`
- **2A mode (.LO):** `Rd = Ra.u16[0]×Rb.u8[0] + Ra.u16[1]×Rb.u8[1] + Rc`
- **2A mode (.HI):** `Rd = Ra.u16[2]×Rb.u8[2] + Ra.u16[3]×Rb.u8[3] + 0` (accumulate from expansion)

## Format

`IDP.{4A/2A}{.LO/.HI}{.SrcAFmt.SrcBFmt} Rd, Ra{.reuse}, Rb{.reuse}, [-]Rc{.reuse}`

## Modifiers

### Mode — /ONLY4A (4A) or /MODE_2ALO_2AHI (2A)

| Mnemonic | Value | Width per element |
|----------|:---:|:---|
| `.4A` | 0 | 4 × 8-bit |
| `.2A.LO` | 1 | 2 × 16-bit (lower half) |
| `.2A.HI` | 3 | 2 × 16-bit (upper half) |

### SrcAFmt (4A: U8/S8; 2A: U16/S16)

| Value | 4A mnemonic | 2A mnemonic |
|:---:|------|------|
| 0 | `.U8` | `.U16` |
| 1 | `.S8` | `.S16` |

### SrcBFmt (always U8/S8)

| Value | Mnemonic |
|:---:|------|
| 0 | `.U8` |
| 1 | `.S8` |

### `.reuse` — register read reuse hint

When `.reuse` is specified on a source operand, the hardware may keep the
register value in a bypass register for the next instruction. Reuse is
incompatible with DRAIN/WAITn tokens (enforced by CONDITION).

### Rc negate

4A mode supports `[-]Rc` (negated accumulate). Integer negation = two's complement.

## Variant overview

8 variants, 2 sub-groups × 4 register formats:

| Format | Opcode | Registers |
|--------|--------|-----------|
| `_R` (plain register) | `0x226` | Ra, Rb, Rc all from regular registers |
| `_C` (constant) | `0xa26` | One source from constant bank |
| `_URb` (uniform) | `0x1c26` | One source from uniform register |
| `_CXb` (constant+uniform) | `0x1a26` | Constant bank + uniform register |

## Bit layout (4A R 0x226, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_4(batch_t,usched_info,reuse_src_a,reuse_src_b,reuse_src_c)` | scheduling + reuse |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `*7` | fixed |
| [112:110] | dst_wr_sb | 3 | `*7` | fixed |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x226 | |
| [77:76] | insert | 2 | `*mode` | 0=4A,1=2A.LO,3=2A.HI |
| [75] | Rc@negate | 1 | Rc@negate | `-Rc` |
| [74] | SrcBFmt | 1 | — | U8=0,S8=1 |
| [73] | SrcAFmt | 1 | — | 4A: U8=0,S8=1; 2A: U16=0,S16=1 |
| [71:64] | Rc | 8 | Register | accumulate value |
| [39:32] | Rb | 8 | Register | B dot-product source |
| [31:24] | Ra | 8 | Register | A dot-product source |
| [23:16] | Rd | 8 | Register | destination |
| [15] | Pg_not | 1 | Pg@not | predicate negate |
| [14:12] | Pg | 3 | Predicate | guard predicate |

### 2A variant differences
- [77:76] `*mode` = MODE_2ALO_2AHI
- Same opcode, mode distinguishes 4A vs 2A

## Verified encodings

| Lo64 | Disassembly |
|------|-------------|
| `0x0000000908057226` | `IDP.4A.U8.U8 R5, R8.reuse, R9.reuse, R0.reuse` |
| `0x0000000908077226` | `IDP.2A.LO.U16.U8 R7, R8, R9, R0` |
| `0x0000000908097226` | `IDP.2A.HI.U16.U8 R9, R8, R9, R0` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `dp4a.u32.u32 %r, %a, %b, %c` | `IDP.4A.U8.U8 Rd, Ra, Rb, Rc` |
| `dp2a.lo.u32.u32 %r, %a, %b, %c` | `IDP.2A.LO.U16.U8 Rd, Ra, Rb, Rc` |
| `dp2a.hi.u32.u32 %r, %a, %b, %c` | `IDP.2A.HI.U16.U8 Rd, Ra, Rb, Rc` |
