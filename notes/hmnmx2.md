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

## Cross-comparison

| Property | FMNMX | HMNMX2 | VHMNMX |
|----------|-------|--------|--------|
| Pipe | `fe_pipe` | `fp16_pipe` | `fp16_pipe` |
| Format | 32-bit FP | 16-bit FP ×2 | 16-bit FP ×2 |
| Inputs | 2 (Ra, Rb) | 2 (Ra, Rb) | **3** (Ra,Rb,Rc) |
| Swizzle | No | Yes | Yes |

## Latency

`fp16_pipe`, `INST_TYPE_COUPLED_MATH`. Coupled scoreboard.
