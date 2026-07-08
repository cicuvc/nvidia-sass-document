# HMNMX2 — Packed FP16x2 Min/Max

**Opcode mnemonic:** HMNMX2  |  **Pipe:** `fp16_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Two-element packed half-precision min/max: `Rd.F16x2 = minmax(Ra.F16x2, Rb.F16x2)`. Operates on pairs of FP16/BF16/E6M9 values packed in 32-bit registers. This is the 2-input counterpart of VHMNMX (which has 3 inputs: Ra, Rb, Rc).

Four modes via modifier combinations:
- **Normal:** Basic min/max with swizzle selectors
- **Fixed:** Fixed-min/max (one operand treated as constant bound)
- **Pred:** Output predicate indicating which element was selected
- **Pred+Fixed:** Combined predicate output with fixed bound

## Variants (20 total)

Matrix: {normal, fixed, pred, pred_fixed} × {RRR, RIR, RCR, RCxR, RUR}

| Mode | Opcode (RRR) |
|------|-------------|
| Normal | `0x240` |
| Fixed (ALT) | `0x240` |
| Pred | `0x240` |
| Pred+Fixed (ALT) | `0x240` |

All share the same base opcode — mode distinction is in modifier field bits.

## Modifiers

| Modifier | Field | Values |
|----------|-------|--------|
| ofmt | — | F16_V2(0), BF16_V2(2), E6M9_V2(3) |
| ftz | — | noftz/.FTZ |
| nan | — | nonan/.NAN |
| xorsign | — | XOR sign mode |
| Swizzle (ABC) | bop/hsel/insert | Element selectors |

## Bit layout (RRR 0x240, 128-bit)

| bits | field | width | source | notes |
|------|-------|-------|--------|-------|
| [124:122],[109:105] | opex | 8 | `TABLES_opex_5(batch_t,usched_info,reuse_src_a,reuse_src_b)` | scheduling + reuse |
| [121:116] | req_bit_set | 6 | — | scoreboard wait mask |
| [115:113] | src_rel_sb | 3 | `*7` | fixed |
| [112:110] | dst_wr_sb | 3 | `*7` | fixed |
| [103:102] | pm_pred | 2 | — | perfmon predicate |
| [91],[11:0] | opcode | 13 | 0x240 | |
| [90] | Pp@not | 1 | Pp@not | predicate output negate |
| [89:87] | Pp | 3 | Predicate | predicate output |
| [85],[78] | ofmt | 2 | OFMT_hmnmx2 | F16_V2=0,BF16_V2=2,E6M9_V2=3 |
| [82] | xorsign | 1 | — | XOR sign mode |
| [81] | nan | 1 | — | `.NAN` |
| [80] | ftz | 1 | — | `.FTZ` |
| [75:74] | iswzA | 2 | bop | swizzle for Ra |
| [73] | Ra@absolute | 1 | Ra@absolute | `\|Ra\|` |
| [72] | Ra@negate | 1 | Ra@negate | `-Ra` |
| [65] | isA | 1 | `*0` | |
| [63] | Rb@negate | 1 | Rb@negate | `-Rb` |
| [62] | Rb@absolute | 1 | Rb@absolute | `\|Rb\|` |
| [61:60] | iswzB | 2 | hsel | swizzle for Rb |
| [39:32] | Rb | 8 | Register | second source |
| [31:24] | Ra | 8 | Register | first source |
| [23:16] | Rd | 8 | Register | destination |
| [15] | Pg_not | 1 | Pg@not | predicate negate |
| [14:12] | Pg | 3 | Predicate | guard predicate |

### Fixed / Pred / Pred+Fixed mode differences
Fixed variants add a fixed-bound register field; Pred variants use `Pp` as predicate output; Pred+Fixed combines both. All share the same base opcode with mode distinction in modifier bits.

## Cross-comparison

| Property | FMNMX | HMNMX2 | VHMNMX |
|----------|-------|--------|--------|
| Pipe | `fe_pipe` | `fp16_pipe` | `fp16_pipe` |
| Format | 32-bit FP | 16-bit FP ×2 | 16-bit FP ×2 |
| Inputs | 2 (Ra, Rb) | 2 (Ra, Rb) | **3** (Ra,Rb,Rc) |
| Swizzle | No | Yes | Yes |

## Latency

`fp16_pipe`, `INST_TYPE_COUPLED_MATH`. Coupled scoreboard.
